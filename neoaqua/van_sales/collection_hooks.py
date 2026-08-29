# Copyright (c) 2026, Neotec Integrated Solutions
"""Payment Entry hooks - tag collections to the open van trip."""

import frappe


def tag_trip_collection(doc, method=None):
	if doc.payment_type != "Receive" or doc.party_type != "Customer":
		return
	if doc.get("neoaqua_van_trip"):
		return

	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	salesman = frappe.db.get_value("Sales Person", {"employee": employee}, "name") if employee else None
	if not salesman:
		return

	trip = frappe.db.get_value(
		"Van Trip",
		{"salesman": salesman, "docstatus": 1, "status": ["in", ["Loaded", "In Progress"]]},
		"name",
	)
	if trip:
		doc.db_set("neoaqua_van_trip", trip)
