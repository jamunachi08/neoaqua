# Copyright (c) 2026, Neotec Integrated Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_datetime


class VanTrip(Document):
	# ------------------------------------------------------------ lifecycle
	def validate(self):
		self.set_defaults()
		self.validate_open_trip()
		self.pull_route_stops()
		self.calculate_load_value()
		self.calculate_variance()
		self.calculate_coverage()

	def before_submit(self):
		if not self.items:
			frappe.throw(_("Load at least one item before submitting the trip."))
		self.status = "Loaded"
		if not self.start_time:
			self.start_time = get_datetime()

	def on_submit(self):
		self.create_load_stock_entry()

	def on_cancel(self):
		self.ignore_linked_doctypes = ["GL Entry", "Stock Ledger Entry"]
		for field in ("load_stock_entry", "return_stock_entry"):
			se = self.get(field)
			if se and frappe.db.get_value("Stock Entry", se, "docstatus") == 1:
				frappe.throw(_("Cancel Stock Entry {0} before cancelling this trip.").format(se))
		self.db_set("status", "Cancelled")

	# ------------------------------------------------------------ helpers
	def set_defaults(self):
		if not self.company:
			self.company = frappe.defaults.get_user_default("Company")
		if self.van:
			van = frappe.get_cached_doc("Van", self.van)
			self.van_warehouse = van.warehouse
			self.salesman = self.salesman or van.salesman
			self.driver = self.driver or van.driver
			self.route = self.route or van.default_route
		if self.odometer_start and self.odometer_end:
			self.distance_km = flt(self.odometer_end) - flt(self.odometer_start)

	def validate_open_trip(self):
		"""One open trip per van; previous trip must be day-closed when the
		setting demands it."""
		if self.docstatus > 1:
			return
		existing = frappe.db.get_value(
			"Van Trip",
			{
				"van": self.van,
				"docstatus": 1,
				"status": ["in", ["Loaded", "In Progress"]],
				"name": ["!=", self.name],
			},
			"name",
		)
		if existing:
			frappe.throw(
				_("Van {0} already has an open trip {1}. Close it first.").format(
					self.van, frappe.bold(existing)
				)
			)

		if frappe.db.get_single_value("NeoAqua Settings", "require_day_close"):
			prev = frappe.db.get_value(
				"Van Trip",
				{"van": self.van, "docstatus": 1, "status": "Returned", "name": ["!=", self.name]},
				"name",
			)
			if prev and not frappe.db.exists("Salesman Day Close", {"van_trip": prev, "docstatus": 1}):
				frappe.throw(_("Previous trip {0} has no submitted Day Close.").format(frappe.bold(prev)))

	def pull_route_stops(self):
		if self.stops or not self.route:
			return
		for s in frappe.get_all(
			"Van Route Stop",
			filters={"parent": self.route},
			fields=["customer", "customer_name", "sequence"],
			order_by="sequence asc",
		):
			self.append("stops", {**s, "status": "Pending"})

	def calculate_load_value(self):
		total = 0
		for row in self.items:
			if not row.valuation_rate:
				row.valuation_rate = get_valuation_rate(row.item_code, self.van_warehouse)
			total += flt(row.loaded_qty) * flt(row.valuation_rate)
		self.total_loaded_value = total

	def calculate_variance(self):
		for row in self.items:
			row.variance_qty = (
				flt(row.loaded_qty) - flt(row.sold_qty) - flt(row.returned_qty) - flt(row.damaged_qty)
			)
			row.variance_value = flt(row.variance_qty) * flt(row.valuation_rate)

	def calculate_coverage(self):
		self.planned_stops = len(self.stops)
		self.visited_stops = len([s for s in self.stops if s.status == "Visited"])
		self.coverage_pct = (self.visited_stops / self.planned_stops * 100) if self.planned_stops else 0
		self.total_invoiced = sum(flt(s.invoice_amount) for s in self.stops)
		self.total_collected = sum(flt(s.collected_amount) for s in self.stops)

	# ------------------------------------------------------------ stock
	def create_load_stock_entry(self):
		if self.load_stock_entry:
			return
		settings = frappe.get_cached_doc("NeoAqua Settings")
		source = settings.default_plant_warehouse or frappe.db.get_value(
			"Warehouse", {"company": self.company, "is_group": 0}, "name"
		)
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Material Transfer"
		se.company = self.company
		se.posting_date = self.trip_date
		se.set_posting_time = 1
		se.neoaqua_van_trip = self.name
		se.remarks = _("Van load for trip {0} - {1}").format(self.name, self.van)
		for row in self.items:
			se.append(
				"items",
				{
					"item_code": row.item_code,
					"qty": row.loaded_qty,
					"uom": row.uom,
					"s_warehouse": source,
					"t_warehouse": self.van_warehouse,
				},
			)
		se.insert(ignore_permissions=True)
		if settings.auto_create_load_stock_entry:
			se.submit()
		self.db_set("load_stock_entry", se.name)
		frappe.msgprint(
			_("Load Stock Entry {0} created.").format(
				frappe.utils.get_link_to_form("Stock Entry", se.name)
			),
			indicator="green",
			alert=True,
		)

	@frappe.whitelist()
	def create_return_stock_entry(self):
		"""Transfer unsold stock back from the van to the plant."""
		if self.return_stock_entry:
			frappe.throw(_("Return Stock Entry already exists."))
		settings = frappe.get_cached_doc("NeoAqua Settings")
		rows = [r for r in self.items if flt(r.returned_qty) > 0]
		if not rows:
			frappe.throw(_("No returned quantity captured."))

		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Material Transfer"
		se.company = self.company
		se.posting_date = self.trip_date
		se.set_posting_time = 1
		se.neoaqua_van_trip = self.name
		se.remarks = _("Van return for trip {0}").format(self.name)
		for row in rows:
			se.append(
				"items",
				{
					"item_code": row.item_code,
					"qty": row.returned_qty,
					"uom": row.uom,
					"s_warehouse": self.van_warehouse,
					"t_warehouse": settings.default_plant_warehouse,
				},
			)
		se.insert(ignore_permissions=True)
		se.submit()
		self.db_set("return_stock_entry", se.name)
		self.db_set("status", "Returned")
		return se.name

	@frappe.whitelist()
	def pull_pending_orders(self):
		"""Add a stop for every open Sales Order on this route.

		Orders taken at the office are the salesman's obligations for the day.
		Without this he only sees the standing route and has to be told
		separately what to deliver, which is how deliveries get missed."""
		existing = {s.customer for s in self.stops}
		customers = []
		if self.route:
			customers = frappe.get_all("Van Route Stop", filters={"parent": self.route}, pluck="customer")

		filters = {
			"docstatus": 1,
			"company": self.company,
			"status": ["not in", ["Closed", "Completed", "Cancelled"]],
		}
		if customers:
			filters["customer"] = ["in", customers]

		added = 0
		for so in frappe.get_all(
			"Sales Order",
			filters=filters,
			fields=["name", "customer", "customer_name", "grand_total", "per_delivered"],
			order_by="transaction_date asc",
			limit=100,
		):
			if flt(so.per_delivered) >= 100:
				continue
			row = next((s for s in self.stops if s.customer == so.customer), None)
			if row:
				if not row.sales_order:
					row.sales_order = so.name
					row.stop_type = "Order Delivery"
					added += 1
				continue
			self.append(
				"stops",
				{
					"customer": so.customer,
					"customer_name": so.customer_name,
					"sequence": len(self.stops) + 1,
					"status": "Pending",
					"stop_type": "Order Delivery",
					"sales_order": so.name,
				},
			)
			added += 1

		for stop in self.stops:
			if not stop.stop_type:
				stop.stop_type = "Van Sale"

		self.save()
		return {"added": added, "stops": len(self.stops), "already_planned": len(existing)}

	@frappe.whitelist()
	def pull_sold_quantities(self):
		"""Read back invoiced quantity per item for this trip."""
		sold = frappe.db.sql(
			"""
			select sii.item_code, sum(sii.stock_qty) as qty
			from `tabSales Invoice Item` sii
			join `tabSales Invoice` si on si.name = sii.parent
			where si.docstatus = 1 and si.neoaqua_van_trip = %s
			group by sii.item_code
			""",
			self.name,
			as_dict=True,
		)
		mapping = {d.item_code: flt(d.qty) for d in sold}
		for row in self.items:
			row.sold_qty = mapping.get(row.item_code, 0)
		self.calculate_variance()
		self.save()
		return mapping


def get_valuation_rate(item_code, warehouse):
	rate = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "valuation_rate")
	if not rate:
		rate = frappe.db.get_value("Item", item_code, "valuation_rate")
	return flt(rate)


@frappe.whitelist()
def get_van_stock(van_warehouse):
	"""Live van stock - consumed by the mobile van sales screen."""
	return frappe.get_all(
		"Bin",
		filters={"warehouse": van_warehouse, "actual_qty": [">", 0]},
		fields=["item_code", "actual_qty", "valuation_rate", "stock_uom"],
		order_by="item_code",
	)
