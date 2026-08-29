# Copyright (c) 2026, Neotec Integrated Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime, time_diff_in_seconds

from neoaqua.van_sales import geofence


class SalesmanCheckIn(Document):
	def validate(self):
		if not self.checkin_datetime:
			self.checkin_datetime = now_datetime()
		self.resolve_trip()
		geofence.enforce(self)
		self.validate_photo()
		self.compute_duration()

	def on_submit(self):
		self.update_trip_stop()

	# ---------------------------------------------------------------- helpers
	def resolve_trip(self):
		if self.van_trip or not self.salesman:
			return
		self.van_trip = frappe.db.get_value(
			"Van Trip",
			{
				"salesman": self.salesman,
				"docstatus": 1,
				"status": ["in", ["Loaded", "In Progress"]],
			},
			"name",
		)

	def validate_photo(self):
		if frappe.db.get_single_value("NeoAqua Settings", "require_visit_photo") and not self.visit_photo:
			if self.visit_status in ("Successful", "No Order"):
				frappe.throw(_("A visit photo is mandatory for this outcome."))

	def compute_duration(self):
		if self.checkin_datetime and self.checkout_datetime:
			self.duration_minutes = round(
				time_diff_in_seconds(get_datetime(self.checkout_datetime), get_datetime(self.checkin_datetime)) / 60.0,
				2,
			)

	def update_trip_stop(self):
		if not self.van_trip:
			return
		trip = frappe.get_doc("Van Trip", self.van_trip)
		changed = False
		for stop in trip.stops:
			if stop.customer == self.customer and stop.status == "Pending":
				stop.status = "Visited" if self.visit_status == "Successful" else "Failed"
				stop.check_in = self.name
				stop.sales_invoice = self.sales_invoice
				stop.invoice_amount = frappe.db.get_value("Sales Invoice", self.sales_invoice, "grand_total") if self.sales_invoice else 0
				stop.collected_amount = self.collected_amount
				changed = True
				break
		if changed:
			if trip.status == "Loaded":
				trip.db_set("status", "In Progress")
			trip.calculate_coverage()
			trip.save(ignore_permissions=True)


@frappe.whitelist()
def quick_check_in(customer, latitude, longitude, purpose="Sale", accuracy=None):
	"""Mobile endpoint - creates and submits a check-in in one call."""
	salesman = frappe.db.get_value("Sales Person", {"employee": get_current_employee()}, "name")
	doc = frappe.new_doc("Salesman Check In")
	doc.update(
		{
			"salesman": salesman,
			"customer": customer,
			"latitude": float(latitude),
			"longitude": float(longitude),
			"accuracy_m": float(accuracy) if accuracy else None,
			"visit_purpose": purpose,
			"visit_status": "Draft",
			"checkin_datetime": now_datetime(),
		}
	)
	doc.insert(ignore_permissions=True)
	doc.submit()
	return {"name": doc.name, "within_geofence": doc.within_geofence, "distance_m": doc.distance_from_zone_m}


def get_current_employee():
	return frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
