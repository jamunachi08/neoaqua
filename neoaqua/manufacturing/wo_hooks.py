# Copyright (c) 2026, Neotec Integrated Solutions
"""Work Order hooks - production line inference and dashboard cache."""

import frappe
from frappe.utils import flt, nowdate

LINE_BY_GROUP = {
	"Bottled Water - Small PET": "Line 1 - Small PET",
	"Bottled Water - Large PET": "Line 2 - Large PET",
	"Bottled Water - 5 Gallon": "Line 3 - 5 Gallon",
	"Treated Water": "RO Plant",
}


def set_production_line(doc, method=None):
	if doc.get("neoaqua_production_line"):
		return
	group = frappe.get_cached_value("Item", doc.production_item, "item_group")
	doc.neoaqua_production_line = LINE_BY_GROUP.get(group)


def on_work_order_submit(doc, method=None):
	"""Auto-raise a Water Quality Check placeholder for the FG batch."""
	if not frappe.get_cached_value("Item", doc.production_item, "neoaqua_requires_qc"):
		return
	qc = frappe.new_doc("Water Quality Check")
	qc.update(
		{
			"check_type": "In-Process (Filler)",
			"posting_date": doc.planned_start_date or nowdate(),
			"company": doc.company,
			"work_order": doc.name,
			"item_code": doc.production_item,
			"production_line": doc.get("neoaqua_production_line"),
		}
	)
	qc.insert(ignore_permissions=True)


def refresh_production_dashboard_cache():
	"""Hourly OEE-lite snapshot cached for the Manufacturing workspace."""
	rows = frappe.db.sql(
		"""
		select neoaqua_production_line as line,
		       sum(qty) as planned,
		       sum(produced_qty) as produced
		from `tabWork Order`
		where docstatus = 1 and status not in ('Stopped','Closed')
		  and creation >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
		group by neoaqua_production_line
		""",
		as_dict=True,
	)
	snapshot = {
		r.line: {
			"planned": flt(r.planned),
			"produced": flt(r.produced),
			"attainment": round(flt(r.produced) / flt(r.planned) * 100, 1) if flt(r.planned) else 0,
		}
		for r in rows
		if r.line
	}
	frappe.cache().set_value("neoaqua_line_attainment", snapshot)
	return snapshot
