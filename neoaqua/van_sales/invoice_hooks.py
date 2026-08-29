# Copyright (c) 2026, Neotec Integrated Solutions
"""Sales Invoice / POS Invoice hooks for van sales."""

import frappe
from frappe import _
from frappe.utils import flt

from neoaqua.van_sales import geofence


def validate_van_invoice(doc, method=None):
	"""Bind the invoice to the open trip, force the van warehouse, and apply
	route / geofence controls."""
	if doc.get("is_return"):
		return

	trip = doc.get("neoaqua_van_trip") or _resolve_open_trip(doc)
	if not trip:
		return
	doc.neoaqua_van_trip = trip

	trip_doc = frappe.get_cached_doc("Van Trip", trip)
	doc.neoaqua_van = trip_doc.van
	if not doc.get("sales_partner"):
		doc.neoaqua_salesman = trip_doc.salesman

	_force_van_warehouse(doc, trip_doc.van_warehouse)
	_validate_route(doc, trip_doc)
	_validate_geofence(doc, trip_doc)


def _resolve_open_trip(doc):
	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	if not employee:
		return None
	salesman = frappe.db.get_value("Sales Person", {"employee": employee}, "name")
	if not salesman:
		return None
	return frappe.db.get_value(
		"Van Trip",
		{"salesman": salesman, "docstatus": 1, "status": ["in", ["Loaded", "In Progress"]]},
		"name",
	)


def _force_van_warehouse(doc, warehouse):
	if not warehouse:
		return
	for row in doc.items:
		if not frappe.get_cached_value("Item", row.item_code, "is_stock_item"):
			continue
		row.warehouse = warehouse


def _validate_route(doc, trip):
	if not frappe.db.get_single_value("NeoAqua Settings", "block_sale_outside_route"):
		return
	if not trip.route:
		return
	on_route = frappe.db.exists(
		"Van Route Stop", {"parent": trip.route, "customer": doc.customer}
	)
	if not on_route:
		frappe.throw(
			_("Customer {0} is not on route {1}. Off-route sales are blocked.").format(
				frappe.bold(doc.customer), frappe.bold(trip.route)
			)
		)


def _validate_geofence(doc, trip):
	if not geofence.geofencing_enabled():
		return
	if frappe.db.get_single_value("NeoAqua Settings", "geofence_enforcement") != "Block Invoice":
		return
	if not geofence.has_valid_checkin(doc.customer, trip.salesman, doc.posting_date):
		frappe.throw(
			_("No in-geofence check-in recorded today for {0}. Check in at the customer location first.").format(
				frappe.bold(doc.customer)
			)
		)


def apply_container_deposit(doc, method=None):
	"""Add a non-taxable deposit line when returnable containers are sold to a
	customer who does not yet hold them."""
	settings = frappe.get_cached_doc("NeoAqua Settings")
	if not settings.track_containers or not settings.container_item:
		return
	doc.neoaqua_containers_out = sum(
		flt(r.qty) for r in doc.items if _is_returnable(r.item_code)
	)


def _is_returnable(item_code):
	return bool(frappe.get_cached_value("Item", item_code, "neoaqua_is_returnable"))


def on_submit_van_invoice(doc, method=None):
	"""Post container movement and roll the totals into the trip."""
	if not doc.get("neoaqua_van_trip"):
		return

	settings = frappe.get_cached_doc("NeoAqua Settings")
	if settings.track_containers and flt(doc.get("neoaqua_containers_out")):
		cle = frappe.new_doc("Container Ledger Entry")
		cle.update(
			{
				"posting_date": doc.posting_date,
				"company": doc.company,
				"customer": doc.customer,
				"entry_type": "Issue (Full Out)",
				"item_code": settings.container_item,
				"qty": flt(doc.neoaqua_containers_out),
				"van_trip": doc.neoaqua_van_trip,
				"reference_doctype": doc.doctype,
				"reference_name": doc.name,
			}
		)
		cle.insert(ignore_permissions=True)
		cle.submit()

	if flt(doc.get("neoaqua_empties_collected")):
		cle = frappe.new_doc("Container Ledger Entry")
		cle.update(
			{
				"posting_date": doc.posting_date,
				"company": doc.company,
				"customer": doc.customer,
				"entry_type": "Return (Empty In)",
				"item_code": settings.container_item,
				"qty": flt(doc.neoaqua_empties_collected),
				"van_trip": doc.neoaqua_van_trip,
				"reference_doctype": doc.doctype,
				"reference_name": doc.name,
			}
		)
		cle.insert(ignore_permissions=True)
		cle.submit()

	_touch_trip(doc.neoaqua_van_trip)


def on_cancel_van_invoice(doc, method=None):
	if not doc.get("neoaqua_van_trip"):
		return
	for cle in frappe.get_all(
		"Container Ledger Entry",
		filters={"reference_name": doc.name, "docstatus": 1},
		pluck="name",
	):
		frappe.get_doc("Container Ledger Entry", cle).cancel()
	_touch_trip(doc.neoaqua_van_trip)


def _touch_trip(trip):
	doc = frappe.get_doc("Van Trip", trip)
	if doc.docstatus == 1 and doc.status == "Loaded":
		doc.db_set("status", "In Progress")
