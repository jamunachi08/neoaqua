# Copyright (c) 2026, Neotec Integrated Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class VanLoadRequest(Document):
	def validate(self):
		self.set_warehouses()
		self.enrich_items()
		self.validate_availability()
		self.calculate_totals()

	def on_submit(self):
		self.create_stock_entry()

	def on_cancel(self):
		if self.stock_entry and frappe.db.get_value("Stock Entry", self.stock_entry, "docstatus") == 1:
			frappe.get_doc("Stock Entry", self.stock_entry).cancel()

	# ---------------------------------------------------------------- helpers
	def set_warehouses(self):
		settings = frappe.get_cached_doc("NeoAqua Settings")
		van_wh = frappe.db.get_value("Van", self.van, "warehouse") if self.van else None
		if self.load_type == "Return to Plant":
			self.source_warehouse = self.source_warehouse or van_wh
			self.target_warehouse = self.target_warehouse or settings.default_plant_warehouse
		else:
			self.source_warehouse = self.source_warehouse or settings.default_plant_warehouse
			self.target_warehouse = self.target_warehouse or van_wh
		if not self.salesman and self.van:
			self.salesman = frappe.db.get_value("Van", self.van, "salesman")

	def enrich_items(self):
		van_wh = frappe.db.get_value("Van", self.van, "warehouse") if self.van else None
		for row in self.items:
			row.available_qty = get_qty(row.item_code, self.source_warehouse)
			row.van_stock_qty = get_qty(row.item_code, van_wh)
			if not row.valuation_rate:
				row.valuation_rate = flt(
					frappe.db.get_value(
						"Bin", {"item_code": row.item_code, "warehouse": self.source_warehouse}, "valuation_rate"
					)
				) or flt(frappe.db.get_value("Item", row.item_code, "valuation_rate"))
			row.amount = flt(row.qty) * flt(row.valuation_rate)

	def validate_availability(self):
		if frappe.db.get_single_value("NeoAqua Settings", "allow_negative_van_stock"):
			return
		for row in self.items:
			if flt(row.qty) > flt(row.available_qty):
				frappe.throw(
					_("Row {0}: only {1} of {2} available in {3}.").format(
						row.idx, flt(row.available_qty), row.item_code, self.source_warehouse
					)
				)

	def calculate_totals(self):
		self.total_qty = sum(flt(r.qty) for r in self.items)
		self.total_value = sum(flt(r.amount) for r in self.items)

	def create_stock_entry(self):
		if self.stock_entry:
			return
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Material Transfer"
		se.company = self.company
		se.posting_date = self.posting_date
		se.set_posting_time = 1
		se.neoaqua_van_trip = self.van_trip
		se.remarks = _("{0} for van {1} ({2})").format(self.load_type, self.van, self.name)
		for row in self.items:
			se.append(
				"items",
				{
					"item_code": row.item_code,
					"qty": row.qty,
					"uom": row.uom,
					"s_warehouse": self.source_warehouse,
					"t_warehouse": self.target_warehouse,
				},
			)
		se.insert(ignore_permissions=True)
		se.submit()
		self.db_set("stock_entry", se.name)


def get_qty(item_code, warehouse):
	if not (item_code and warehouse):
		return 0
	return flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"))


@frappe.whitelist()
def get_suggested_load(van, route=None, coverage_days=1):
	"""Suggest a load sheet from the average daily sales of the route over the
	trailing 30 days, less current van stock."""
	van_wh = frappe.db.get_value("Van", van, "warehouse")
	route = route or frappe.db.get_value("Van", van, "default_route")
	customers = frappe.get_all("Van Route Stop", filters={"parent": route}, pluck="customer") if route else []
	if not customers:
		return []

	rows = frappe.db.sql(
		"""
		select sii.item_code, sum(sii.stock_qty)/30 as avg_daily
		from `tabSales Invoice Item` sii
		join `tabSales Invoice` si on si.name = sii.parent
		where si.docstatus = 1
		  and si.posting_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
		  and si.customer in %(customers)s
		group by sii.item_code
		""",
		{"customers": customers},
		as_dict=True,
	)
	suggestion = []
	for r in rows:
		target = flt(r.avg_daily) * flt(coverage_days)
		on_van = get_qty(r.item_code, van_wh)
		qty = max(target - on_van, 0)
		if qty > 0:
			suggestion.append({"item_code": r.item_code, "qty": round(qty)})
	return suggestion
