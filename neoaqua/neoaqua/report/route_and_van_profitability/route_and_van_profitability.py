# Copyright (c) 2026, Neotec Integrated Solutions

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, getdate, nowdate

def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, None, get_chart(data), get_summary(data)


def get_columns():
	return [
		{"label": _("Route"), "fieldname": "route", "fieldtype": "Link", "options": "Van Route", "width": 165},
		{"label": _("Van"), "fieldname": "van", "fieldtype": "Link", "options": "Van", "width": 95},
		{"label": _("Salesman"), "fieldname": "salesman", "fieldtype": "Link", "options": "Sales Person", "width": 145},
		{"label": _("Trips"), "fieldname": "trips", "fieldtype": "Int", "width": 65},
		{"label": _("Revenue"), "fieldname": "revenue", "fieldtype": "Currency", "width": 120},
		{"label": _("Cost of Sales"), "fieldname": "cogs", "fieldtype": "Currency", "width": 125},
		{"label": _("Gross Margin"), "fieldname": "gross", "fieldtype": "Currency", "width": 125},
		{"label": _("Route Expenses"), "fieldname": "expenses", "fieldtype": "Currency", "width": 130},
		{"label": _("Stock Losses"), "fieldname": "losses", "fieldtype": "Currency", "width": 120},
		{"label": _("Contribution"), "fieldname": "contribution", "fieldtype": "Currency", "width": 130},
		{"label": _("Contribution %"), "fieldname": "contribution_pct", "fieldtype": "Percent", "width": 125},
		{"label": _("Rev / Trip"), "fieldname": "rev_per_trip", "fieldtype": "Currency", "width": 115},
		{"label": _("Cost / Drop"), "fieldname": "cost_per_drop", "fieldtype": "Currency", "width": 115},
	]


def get_data(filters):
	"""Revenue less cost of sales, route expenses and stock losses, per route.

	This is the number that decides whether a route is worth running. Revenue
	alone flatters a long route that burns fuel and loses stock; two routes can
	sell the same and contribute very differently."""
	values = {
		"company": filters.get("company") or frappe.defaults.get_user_default("company"),
		"from_date": filters.get("from_date") or add_months(nowdate(), -1),
		"to_date": filters.get("to_date") or nowdate(),
	}

	trips = frappe.db.sql(
		"""select vt.route, vt.van, vt.salesman, count(*) as trips,
		          sum(vt.visited_stops) as drops
		   from `tabVan Trip` vt
		   where vt.docstatus = 1 and vt.company = %(company)s
		     and vt.trip_date between %(from_date)s and %(to_date)s
		   group by vt.route, vt.van, vt.salesman""",
		values, as_dict=True,
	)

	revenue = frappe.db.sql(
		"""select si.neoaqua_van as van, sum(si.base_net_total) as revenue
		   from `tabSales Invoice` si
		   where si.docstatus = 1 and si.company = %(company)s
		     and si.posting_date between %(from_date)s and %(to_date)s
		     and si.neoaqua_van is not null
		   group by si.neoaqua_van""",
		values, as_dict=True,
	)

	cogs = frappe.db.sql(
		"""select si.neoaqua_van as van, sum(-1 * sle.stock_value_difference) as cogs
		   from `tabStock Ledger Entry` sle
		   join `tabSales Invoice` si on si.name = sle.voucher_no
		   where sle.voucher_type = 'Sales Invoice' and sle.is_cancelled = 0
		     and si.docstatus = 1 and si.company = %(company)s
		     and si.posting_date between %(from_date)s and %(to_date)s
		     and si.neoaqua_van is not null
		   group by si.neoaqua_van""",
		values, as_dict=True,
	)

	closes = frappe.db.sql(
		"""select dc.van, sum(dc.total_expenses) as expenses,
		          sum(abs(dc.stock_variance_value)) as losses
		   from `tabSalesman Day Close` dc
		   where dc.docstatus = 1 and dc.company = %(company)s
		     and dc.posting_date between %(from_date)s and %(to_date)s
		   group by dc.van""",
		values, as_dict=True,
	)

	rev = {r.van: flt(r.revenue) for r in revenue}
	cost = {r.van: flt(r.cogs) for r in cogs}
	exp = {r.van: (flt(r.expenses), flt(r.losses)) for r in closes}

	rows = []
	for t in trips:
		r = rev.get(t.van, 0)
		c = cost.get(t.van, 0)
		e, l = exp.get(t.van, (0, 0))
		contribution = r - c - e - l
		rows.append(
			{
				"route": t.route, "van": t.van, "salesman": t.salesman, "trips": t.trips,
				"revenue": r, "cogs": c, "gross": r - c, "expenses": e, "losses": l,
				"contribution": contribution,
				"contribution_pct": (contribution / r * 100) if r else 0,
				"rev_per_trip": (r / t.trips) if t.trips else 0,
				"cost_per_drop": ((e + l) / flt(t.drops)) if flt(t.drops) else 0,
			}
		)
	rows.sort(key=lambda x: x["contribution"], reverse=True)
	return rows


def get_chart(data):
	return {
		"data": {
			"labels": [d["van"] or d["route"] for d in data],
			"datasets": [
				{"name": _("Gross Margin"), "values": [flt(d["gross"]) for d in data]},
				{"name": _("Contribution"), "values": [flt(d["contribution"]) for d in data]},
			],
		},
		"type": "bar",
	}


def get_summary(data):
	rev = sum(flt(d["revenue"]) for d in data)
	con = sum(flt(d["contribution"]) for d in data)
	loss_making = [d for d in data if d["contribution"] < 0]
	return [
		{"label": _("Revenue"), "value": rev, "datatype": "Currency"},
		{"label": _("Contribution"), "value": con, "datatype": "Currency"},
		{"label": _("Contribution %"), "value": (con / rev * 100) if rev else 0, "datatype": "Percent",
		 "indicator": "Green" if rev and con / rev > 0.15 else "Orange"},
		{"label": _("Loss-making routes"), "value": len(loss_making), "datatype": "Int",
		 "indicator": "Red" if loss_making else "Green"},
	]
