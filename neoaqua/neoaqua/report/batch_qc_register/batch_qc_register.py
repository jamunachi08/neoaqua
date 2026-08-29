# Copyright (c) 2026, Neotec Integrated Solutions
"""SFDA-ready batch release register."""

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("QC Ref"), "fieldname": "name", "fieldtype": "Link", "options": "Water Quality Check", "width": 140},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": _("Check Type"), "fieldname": "check_type", "fieldtype": "Data", "width": 150},
		{"label": _("Line"), "fieldname": "production_line", "fieldtype": "Data", "width": 140},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
		{"label": _("Batch"), "fieldname": "batch_no", "fieldtype": "Link", "options": "Batch", "width": 160},
		{"label": _("Work Order"), "fieldname": "work_order", "fieldtype": "Link", "options": "Work Order", "width": 130},
		{"label": _("Coliform"), "fieldname": "coliform", "fieldtype": "Data", "width": 90},
		{"label": _("TPC"), "fieldname": "total_plate_count", "fieldtype": "Float", "width": 80},
		{"label": _("Result"), "fieldname": "overall_result", "fieldtype": "Data", "width": 130},
		{"label": _("Inspected By"), "fieldname": "inspected_by", "fieldtype": "Link", "options": "Employee", "width": 140},
		{"label": _("SFDA Reportable"), "fieldname": "sfda_reportable", "fieldtype": "Check", "width": 130},
	]


def get_data(filters):
	conditions = ["docstatus = 1"]
	values = {}
	if filters.get("from_date"):
		conditions.append("posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date
	for f in ("check_type", "overall_result", "item_code", "batch_no", "company"):
		if filters.get(f):
			conditions.append(f"{f} = %({f})s")
			values[f] = filters.get(f)

	return frappe.db.sql(
		"""
		select name, posting_date, check_type, production_line, item_code, batch_no,
		       work_order, coliform, total_plate_count, overall_result,
		       inspected_by, sfda_reportable
		from `tabWater Quality Check`
		where {conditions}
		order by posting_date desc, creation desc
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)
