# Copyright (c) 2026, Neotec Integrated Solutions
"""Row-level visibility: a Van Salesman sees only their own documents."""

import frappe


def _own_salesman():
	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	if not employee:
		return None
	return frappe.db.get_value("Sales Person", {"employee": employee}, "name")


def _restricted():
	roles = frappe.get_roles()
	return "Van Salesman" in roles and not {"System Manager", "Van Supervisor", "NeoAqua Manager"} & set(roles)


def _condition(doctype):
	if not _restricted():
		return ""
	salesman = _own_salesman()
	if not salesman:
		return f"`tab{doctype}`.name = '__none__'"
	return f"`tab{doctype}`.salesman = {frappe.db.escape(salesman)}"


def van_trip_query(user):
	return _condition("Van Trip")


def day_close_query(user):
	return _condition("Salesman Day Close")


def check_in_query(user):
	return _condition("Salesman Check In")


def van_trip_has_permission(doc, ptype, user):
	if not _restricted():
		return True
	return doc.salesman == _own_salesman()
