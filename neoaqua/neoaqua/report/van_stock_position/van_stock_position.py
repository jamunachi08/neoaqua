# Copyright (c) 2026, Neotec Integrated Solutions
"""Live stock across every van warehouse, valued and aged."""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, None, None, get_summary(data)


def get_columns():
	return [
		{"label": _("Van"), "fieldname": "van", "fieldtype": "Link", "options": "Van", "width": 120},
		{"label": _("Salesman"), "fieldname": "salesman", "fieldtype": "Link", "options": "Sales Person", "width": 150},
		{"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 180},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 240},
		{"label": _("Qty"), "fieldname": "actual_qty", "fieldtype": "Float", "width": 90},
		{"label": _("UOM"), "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 80},
		{"label": _("Valuation Rate"), "fieldname": "valuation_rate", "fieldtype": "Currency", "width": 125},
		{"label": _("Stock Value"), "fieldname": "stock_value", "fieldtype": "Currency", "width": 125},
	]


def get_data(filters):
	van_filters = {"status": "Active"}
	if filters.get("van"):
		van_filters["name"] = filters.van
	if filters.get("company"):
		van_filters["company"] = filters.company

	vans = frappe.get_all("Van", filters=van_filters, fields=["name", "warehouse", "salesman"])
	wh_map = {v.warehouse: v for v in vans if v.warehouse}
	if not wh_map:
		return []

	rows = frappe.db.sql(
		"""
		select b.warehouse, b.item_code, i.item_name, i.stock_uom,
		       b.actual_qty, b.valuation_rate, b.stock_value
		from `tabBin` b
		join `tabItem` i on i.name = b.item_code
		where b.warehouse in %(warehouses)s and b.actual_qty != 0
		order by b.warehouse, b.item_code
		""",
		{"warehouses": list(wh_map)},
		as_dict=True,
	)
	for r in rows:
		v = wh_map.get(r.warehouse)
		r["van"] = v.name if v else None
		r["salesman"] = v.salesman if v else None
	return rows


def get_summary(data):
	return [
		{"label": _("Total Stock Value on Vans"), "value": sum(flt(d.stock_value) for d in data), "datatype": "Currency"},
		{"label": _("SKUs on Vans"), "value": len({d.item_code for d in data}), "datatype": "Int"},
	]
