# Copyright (c) 2026, Neotec Integrated Solutions

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, getdate, nowdate

AGE_BUCKETS = [(0, 30, "b_0_30"), (31, 60, "b_31_60"), (61, 90, "b_61_90"), (91, 99999, "b_90_plus")]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, None, get_chart(data), get_summary(data)


def get_columns():
	return [
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 170},
		{"label": _("Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 190},
		{"label": _("Route"), "fieldname": "route", "fieldtype": "Link", "options": "Van Route", "width": 140},
		{"label": _("Salesman"), "fieldname": "salesman", "fieldtype": "Link", "options": "Sales Person", "width": 140},
		{"label": _("0-30"), "fieldname": "b_0_30", "fieldtype": "Currency", "width": 105},
		{"label": _("31-60"), "fieldname": "b_31_60", "fieldtype": "Currency", "width": 105},
		{"label": _("61-90"), "fieldname": "b_61_90", "fieldtype": "Currency", "width": 105},
		{"label": _("90+"), "fieldname": "b_90_plus", "fieldtype": "Currency", "width": 105},
		{"label": _("Total Due"), "fieldname": "total", "fieldtype": "Currency", "width": 120},
		{"label": _("Oldest"), "fieldname": "oldest", "fieldtype": "Date", "width": 100},
		{"label": _("Credit Limit"), "fieldname": "credit_limit", "fieldtype": "Currency", "width": 115},
		{"label": _("Over Limit"), "fieldname": "over_limit", "fieldtype": "Currency", "width": 110},
	]


def get_data(filters):
	as_on = getdate(filters.get("as_on_date") or nowdate())
	conditions = ["si.docstatus = 1", "si.outstanding_amount > 0.005"]
	values = {"as_on": as_on}
	if filters.get("company"):
		conditions.append("si.company = %(company)s")
		values["company"] = filters.company
	conditions.append("si.posting_date <= %(as_on)s")

	invoices = frappe.db.sql(
		"""select si.customer, si.customer_name, si.posting_date, si.outstanding_amount
		   from `tabSales Invoice` si
		   where {conditions}""".format(conditions=" and ".join(conditions)),
		values, as_dict=True,
	)
	if not invoices:
		return []

	customers = list({i.customer for i in invoices})
	meta = {
		c.name: c
		for c in frappe.get_all(
			"Customer", filters={"name": ["in", customers]},
			fields=["name", "customer_name", "neoaqua_route"],
		)
	}
	route_salesman = {
		r.name: r.salesman for r in frappe.get_all("Van Route", fields=["name", "salesman"])
	}
	limits = {
		r.parent: flt(r.credit_limit)
		for r in frappe.get_all(
			"Customer Credit Limit", filters={"parent": ["in", customers]},
			fields=["parent", "credit_limit"],
		)
	}

	idx = {}
	for inv in invoices:
		row = idx.setdefault(
			inv.customer,
			{
				"customer": inv.customer,
				"customer_name": inv.customer_name,
				"route": (meta.get(inv.customer) or {}).get("neoaqua_route"),
				"b_0_30": 0, "b_31_60": 0, "b_61_90": 0, "b_90_plus": 0,
				"total": 0, "oldest": inv.posting_date,
			},
		)
		age = (as_on - getdate(inv.posting_date)).days
		for lo, hi, key in AGE_BUCKETS:
			if lo <= age <= hi:
				row[key] += flt(inv.outstanding_amount)
				break
		row["total"] += flt(inv.outstanding_amount)
		if getdate(inv.posting_date) < getdate(row["oldest"]):
			row["oldest"] = inv.posting_date

	rows = list(idx.values())
	for r in rows:
		r["salesman"] = route_salesman.get(r["route"])
		r["credit_limit"] = limits.get(r["customer"], 0)
		r["over_limit"] = max(flt(r["total"]) - flt(r["credit_limit"]), 0) if r["credit_limit"] else 0

	if filters.get("route"):
		rows = [r for r in rows if r["route"] == filters.route]
	if filters.get("salesman"):
		rows = [r for r in rows if r["salesman"] == filters.salesman]
	if filters.get("only_overdue"):
		rows = [r for r in rows if flt(r["b_31_60"]) or flt(r["b_61_90"]) or flt(r["b_90_plus"])]

	rows.sort(key=lambda r: r["total"], reverse=True)
	return rows


def get_chart(data):
	return {
		"data": {
			"labels": [_("0-30"), _("31-60"), _("61-90"), _("90+")],
			"datasets": [{
				"name": _("Outstanding"),
				"values": [
					sum(flt(d["b_0_30"]) for d in data),
					sum(flt(d["b_31_60"]) for d in data),
					sum(flt(d["b_61_90"]) for d in data),
					sum(flt(d["b_90_plus"]) for d in data),
				],
			}],
		},
		"type": "bar",
	}


def get_summary(data):
	total = sum(flt(d["total"]) for d in data)
	over90 = sum(flt(d["b_90_plus"]) for d in data)
	return [
		{"label": _("Total Receivable"), "value": total, "datatype": "Currency"},
		{"label": _("Over 90 Days"), "value": over90, "datatype": "Currency",
		 "indicator": "Red" if over90 else "Green"},
		{"label": _("% Over 90"), "value": (over90 / total * 100) if total else 0, "datatype": "Percent"},
		{"label": _("Over Credit Limit"), "value": sum(flt(d["over_limit"]) for d in data),
		 "datatype": "Currency", "indicator": "Orange"},
	]
