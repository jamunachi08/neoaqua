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
		{"label": _("Salesman"), "fieldname": "salesman", "fieldtype": "Link", "options": "Sales Person", "width": 160},
		{"label": _("Trips"), "fieldname": "trips", "fieldtype": "Int", "width": 70},
		{"label": _("Net Sales"), "fieldname": "sales", "fieldtype": "Currency", "width": 125},
		{"label": _("Collected"), "fieldname": "collected", "fieldtype": "Currency", "width": 125},
		{"label": _("Collection %"), "fieldname": "collection_pct", "fieldtype": "Percent", "width": 110},
		{"label": _("Invoices"), "fieldname": "invoices", "fieldtype": "Int", "width": 85},
		{"label": _("Avg Drop"), "fieldname": "avg_drop", "fieldtype": "Currency", "width": 110},
		{"label": _("Coverage %"), "fieldname": "coverage", "fieldtype": "Percent", "width": 105},
		{"label": _("Strike Rate %"), "fieldname": "strike_rate", "fieldtype": "Percent", "width": 115},
		{"label": _("In Geofence %"), "fieldname": "geofence_pct", "fieldtype": "Percent", "width": 120},
		{"label": _("Cash Variance"), "fieldname": "cash_variance", "fieldtype": "Currency", "width": 120},
		{"label": _("Damage Value"), "fieldname": "damage", "fieldtype": "Currency", "width": 115},
	]


def get_data(filters):
	values = {
		"company": filters.get("company") or frappe.defaults.get_user_default("company"),
		"from_date": filters.get("from_date") or add_months(nowdate(), -1),
		"to_date": filters.get("to_date") or nowdate(),
	}
	man = ""
	if filters.get("salesman"):
		man = " and vt.salesman = %(salesman)s"
		values["salesman"] = filters.salesman

	trips = frappe.db.sql(
		"""select vt.salesman, count(*) as trips,
		          sum(vt.planned_stops) as planned, sum(vt.visited_stops) as visited
		   from `tabVan Trip` vt
		   where vt.docstatus = 1 and vt.trip_date between %(from_date)s and %(to_date)s {man}
		   group by vt.salesman""".format(man=man),
		values, as_dict=True,
	)

	sales = frappe.db.sql(
		"""select si.neoaqua_salesman as salesman, count(*) as invoices,
		          sum(si.base_net_total) as sales,
		          sum(si.base_grand_total - si.outstanding_amount) as collected
		   from `tabSales Invoice` si
		   where si.docstatus = 1 and si.company = %(company)s
		     and si.posting_date between %(from_date)s and %(to_date)s
		     and si.neoaqua_salesman is not null
		   group by si.neoaqua_salesman""",
		values, as_dict=True,
	)

	visits = frappe.db.sql(
		"""select ci.salesman, count(*) as checkins,
		          sum(ci.within_geofence) as in_fence,
		          sum(case when ci.visit_status = 'Successful' then 1 else 0 end) as productive
		   from `tabSalesman Check In` ci
		   where ci.docstatus = 1
		     and date(ci.checkin_datetime) between %(from_date)s and %(to_date)s
		   group by ci.salesman""",
		values, as_dict=True,
	)

	closes = frappe.db.sql(
		"""select dc.salesman, sum(dc.cash_variance) as cash_variance,
		          sum(dc.stock_variance_value) as damage
		   from `tabSalesman Day Close` dc
		   where dc.docstatus = 1 and dc.posting_date between %(from_date)s and %(to_date)s
		   group by dc.salesman""",
		values, as_dict=True,
	)

	idx = {}
	def bucket(name):
		return idx.setdefault(name, {"salesman": name})

	for t in trips:
		b = bucket(t.salesman)
		b.update({"trips": t.trips,
		          "coverage": (flt(t.visited) / flt(t.planned) * 100) if flt(t.planned) else 0})
	for s in sales:
		b = bucket(s.salesman)
		b.update({"invoices": s.invoices, "sales": flt(s.sales), "collected": flt(s.collected)})
	for v in visits:
		b = bucket(v.salesman)
		b.update({
			"geofence_pct": (flt(v.in_fence) / flt(v.checkins) * 100) if flt(v.checkins) else 0,
			"strike_rate": (flt(v.productive) / flt(v.checkins) * 100) if flt(v.checkins) else 0,
		})
	for c in closes:
		b = bucket(c.salesman)
		b.update({"cash_variance": flt(c.cash_variance), "damage": flt(c.damage)})

	rows = list(idx.values())
	for r in rows:
		r["collection_pct"] = (flt(r.get("collected")) / flt(r.get("sales")) * 100) if flt(r.get("sales")) else 0
		r["avg_drop"] = (flt(r.get("sales")) / flt(r.get("invoices"))) if flt(r.get("invoices")) else 0
	rows.sort(key=lambda r: flt(r.get("sales")), reverse=True)
	return rows


def get_chart(data):
	return {
		"data": {
			"labels": [d["salesman"] for d in data],
			"datasets": [
				{"name": _("Net Sales"), "values": [flt(d.get("sales")) for d in data]},
				{"name": _("Collected"), "values": [flt(d.get("collected")) for d in data]},
			],
		},
		"type": "bar",
	}


def get_summary(data):
	sales = sum(flt(d.get("sales")) for d in data)
	collected = sum(flt(d.get("collected")) for d in data)
	variance = sum(flt(d.get("cash_variance")) for d in data)
	return [
		{"label": _("Net Sales"), "value": sales, "datatype": "Currency"},
		{"label": _("Collected"), "value": collected, "datatype": "Currency"},
		{"label": _("Collection %"), "value": (collected / sales * 100) if sales else 0, "datatype": "Percent"},
		{"label": _("Cash Variance"), "value": variance, "datatype": "Currency",
		 "indicator": "Red" if variance < 0 else "Green"},
	]
