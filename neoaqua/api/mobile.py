# Copyright (c) 2026, Neotec Integrated Solutions
"""Whitelisted endpoints consumed by the van salesman mobile client.

Every method resolves the caller's own Sales Person record from the session
user, so a salesman can never read or post against another van.
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate

from neoaqua.van_sales import geofence


def _me():
	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	salesman = frappe.db.get_value("Sales Person", {"employee": employee}, "name") if employee else None
	if not salesman:
		frappe.throw(_("The logged-in user is not linked to a Sales Person."), frappe.PermissionError)
	return salesman


@frappe.whitelist()
def my_trip():
	"""Current open trip with live van stock and remaining stops."""
	salesman = _me()
	trip_name = frappe.db.get_value(
		"Van Trip",
		{"salesman": salesman, "docstatus": 1, "status": ["in", ["Loaded", "In Progress"]]},
		"name",
	)
	if not trip_name:
		return {"trip": None}

	trip = frappe.get_doc("Van Trip", trip_name)
	stock = frappe.get_all(
		"Bin",
		filters={"warehouse": trip.van_warehouse, "actual_qty": [">", 0]},
		fields=["item_code", "actual_qty", "stock_uom"],
	)
	for row in stock:
		row["item_name"] = frappe.get_cached_value("Item", row.item_code, "item_name")
		row["rate"] = flt(
			frappe.db.get_value(
				"Item Price",
				{"item_code": row.item_code, "price_list": "NeoAqua Retail"},
				"price_list_rate",
			)
		)
	return {
		"trip": trip.name,
		"van": trip.van,
		"route": trip.route,
		"status": trip.status,
		"coverage_pct": trip.coverage_pct,
		"stops": [
			{
				"customer": s.customer,
				"customer_name": s.customer_name,
				"sequence": s.sequence,
				"status": s.status,
			}
			for s in trip.stops
		],
		"stock": stock,
	}


@frappe.whitelist()
def customer_snapshot(customer):
	"""Everything the salesman needs at the door."""
	from neoaqua.neoaqua.doctype.container_ledger_entry.container_ledger_entry import (
		customer_container_summary,
	)

	outstanding = flt(
		frappe.db.sql(
			"""select sum(outstanding_amount) from `tabSales Invoice`
			   where customer = %s and docstatus = 1""",
			customer,
		)[0][0]
	)
	last = frappe.db.get_value(
		"Sales Invoice",
		{"customer": customer, "docstatus": 1},
		["name", "posting_date", "grand_total"],
		order_by="posting_date desc",
		as_dict=True,
	)
	zone = frappe.db.get_value("Customer", customer, "neoaqua_geofence_zone")
	return {
		"customer": customer,
		"customer_name": frappe.db.get_value("Customer", customer, "customer_name"),
		"outstanding": outstanding,
		"credit_limit": flt(frappe.db.get_value("Customer", customer, "credit_limit")),
		"last_invoice": last,
		"containers": customer_container_summary(customer),
		"geofence_zone": zone,
	}


@frappe.whitelist()
def check_geofence(customer, latitude, longitude):
	zone = frappe.db.get_value("Customer", customer, "neoaqua_geofence_zone") or geofence.resolve_zone(customer)
	return geofence.evaluate(float(latitude), float(longitude), zone)


@frappe.whitelist()
def day_close_preview():
	"""Read-only settlement figures before the salesman declares cash."""
	salesman = _me()
	trip = frappe.db.get_value(
		"Van Trip",
		{"salesman": salesman, "docstatus": 1, "status": ["in", ["Loaded", "In Progress", "Returned"]]},
		"name",
	)
	if not trip:
		return {}

	sales = frappe.db.sql(
		"""select sum(grand_total) as total,
		          sum(case when is_pos = 1 then grand_total else 0 end) as cash,
		          sum(outstanding_amount) as credit
		   from `tabSales Invoice` where neoaqua_van_trip = %s and docstatus = 1""",
		trip,
		as_dict=True,
	)[0]
	collections = flt(
		frappe.db.sql(
			"""select sum(paid_amount) from `tabPayment Entry`
			   where neoaqua_van_trip = %s and docstatus = 1""",
			trip,
		)[0][0]
	)
	return {
		"trip": trip,
		"date": nowdate(),
		"total_sales": flt(sales.total),
		"cash_sales": flt(sales.cash),
		"credit_sales": flt(sales.credit),
		"collections": collections,
		"expected_cash": flt(sales.cash) + collections,
	}
