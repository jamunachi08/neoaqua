# Copyright (c) 2026, Neotec Integrated Solutions
"""Planned vs actual visits, with geofence adherence per salesman."""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Salesman"), "fieldname": "salesman", "fieldtype": "Link", "options": "Sales Person", "width": 150},
		{"label": _("Route"), "fieldname": "route", "fieldtype": "Link", "options": "Van Route", "width": 160},
		{"label": _("Planned Stops"), "fieldname": "planned", "fieldtype": "Int", "width": 110},
		{"label": _("Visited"), "fieldname": "visited", "fieldtype": "Int", "width": 90},
		{"label": _("Coverage %"), "fieldname": "coverage", "fieldtype": "Percent", "width": 105},
		{"label": _("Check-ins"), "fieldname": "checkins", "fieldtype": "Int", "width": 95},
		{"label": _("In Geofence"), "fieldname": "in_fence", "fieldtype": "Int", "width": 105},
		{"label": _("Geofence Adherence %"), "fieldname": "adherence", "fieldtype": "Percent", "width": 165},
		{"label": _("Productive Calls"), "fieldname": "productive", "fieldtype": "Int", "width": 130},
		{"label": _("Strike Rate %"), "fieldname": "strike_rate", "fieldtype": "Percent", "width": 120},
		{"label": _("Avg Visit (min)"), "fieldname": "avg_duration", "fieldtype": "Float", "width": 120},
	]


def get_data(filters):
	values = {"from_date": filters.get("from_date"), "to_date": filters.get("to_date")}
	date_clause = ""
	if filters.get("from_date"):
		date_clause += " and date(ci.checkin_datetime) >= %(from_date)s"
	if filters.get("to_date"):
		date_clause += " and date(ci.checkin_datetime) <= %(to_date)s"

	checkins = frappe.db.sql(
		"""
		select ci.salesman,
		       count(*) as checkins,
		       sum(ci.within_geofence) as in_fence,
		       sum(case when ci.visit_status = 'Successful' then 1 else 0 end) as productive,
		       avg(ci.duration_minutes) as avg_duration
		from `tabSalesman Check In` ci
		where ci.docstatus = 1 {date_clause}
		group by ci.salesman
		""".format(date_clause=date_clause),
		values,
		as_dict=True,
	)

	trip_clause = ""
	if filters.get("from_date"):
		trip_clause += " and vt.trip_date >= %(from_date)s"
	if filters.get("to_date"):
		trip_clause += " and vt.trip_date <= %(to_date)s"

	trips = frappe.db.sql(
		"""
		select vt.salesman, vt.route,
		       sum(vt.planned_stops) as planned,
		       sum(vt.visited_stops) as visited
		from `tabVan Trip` vt
		where vt.docstatus = 1 {trip_clause}
		group by vt.salesman, vt.route
		""".format(trip_clause=trip_clause),
		values,
		as_dict=True,
	)

	ci_map = {c.salesman: c for c in checkins}
	rows = []
	for t in trips:
		c = ci_map.get(t.salesman, frappe._dict())
		rows.append(
			{
				"salesman": t.salesman,
				"route": t.route,
				"planned": t.planned or 0,
				"visited": t.visited or 0,
				"coverage": (flt(t.visited) / flt(t.planned) * 100) if flt(t.planned) else 0,
				"checkins": c.get("checkins") or 0,
				"in_fence": c.get("in_fence") or 0,
				"adherence": (flt(c.get("in_fence")) / flt(c.get("checkins")) * 100) if flt(c.get("checkins")) else 0,
				"productive": c.get("productive") or 0,
				"strike_rate": (flt(c.get("productive")) / flt(c.get("checkins")) * 100) if flt(c.get("checkins")) else 0,
				"avg_duration": round(flt(c.get("avg_duration")), 1),
			}
		)
	return rows
