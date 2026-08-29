# Copyright (c) 2026, Neotec Integrated Solutions

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Trip"), "fieldname": "name", "fieldtype": "Link", "options": "Van Trip", "width": 140},
		{"label": _("Date"), "fieldname": "trip_date", "fieldtype": "Date", "width": 95},
		{"label": _("Van"), "fieldname": "van", "fieldtype": "Link", "options": "Van", "width": 110},
		{"label": _("Salesman"), "fieldname": "salesman", "fieldtype": "Link", "options": "Sales Person", "width": 140},
		{"label": _("Route"), "fieldname": "route", "fieldtype": "Link", "options": "Van Route", "width": 150},
		{"label": _("Loaded Value"), "fieldname": "total_loaded_value", "fieldtype": "Currency", "width": 120},
		{"label": _("Invoiced"), "fieldname": "total_invoiced", "fieldtype": "Currency", "width": 120},
		{"label": _("Collected"), "fieldname": "total_collected", "fieldtype": "Currency", "width": 120},
		{"label": _("Credit Given"), "fieldname": "credit_given", "fieldtype": "Currency", "width": 120},
		{"label": _("Sell Through %"), "fieldname": "sell_through", "fieldtype": "Percent", "width": 110},
		{"label": _("Stops"), "fieldname": "planned_stops", "fieldtype": "Int", "width": 70},
		{"label": _("Visited"), "fieldname": "visited_stops", "fieldtype": "Int", "width": 70},
		{"label": _("Coverage %"), "fieldname": "coverage_pct", "fieldtype": "Percent", "width": 100},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
	]


def get_data(filters):
	conditions = ["vt.docstatus = 1"]
	values = {}
	if filters.get("from_date"):
		conditions.append("vt.trip_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("vt.trip_date <= %(to_date)s")
		values["to_date"] = filters.to_date
	for f in ("van", "salesman", "route", "company"):
		if filters.get(f):
			conditions.append(f"vt.{f} = %({f})s")
			values[f] = filters.get(f)

	rows = frappe.db.sql(
		"""
		select vt.name, vt.trip_date, vt.van, vt.salesman, vt.route, vt.status,
		       vt.total_loaded_value, vt.total_invoiced, vt.total_collected,
		       vt.planned_stops, vt.visited_stops, vt.coverage_pct
		from `tabVan Trip` vt
		where {conditions}
		order by vt.trip_date desc, vt.name desc
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)

	for r in rows:
		r["credit_given"] = flt(r.total_invoiced) - flt(r.total_collected)
		r["sell_through"] = (
			flt(r.total_invoiced) / flt(r.total_loaded_value) * 100 if flt(r.total_loaded_value) else 0
		)
	return rows
