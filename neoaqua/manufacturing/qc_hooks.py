# Copyright (c) 2026, Neotec Integrated Solutions
"""Quality gate between production and the finished-goods warehouse."""

import frappe
from frappe import _


def block_fg_transfer_without_qc(doc, method=None):
	"""Refuse a Manufacture / FG transfer entry when the batch has no passed
	Finished Goods quality check."""
	if not frappe.db.get_single_value("NeoAqua Settings", "enforce_qc_before_fg_transfer"):
		return
	if doc.purpose not in ("Manufacture", "Material Transfer"):
		return

	fg_warehouse = frappe.db.get_single_value("NeoAqua Settings", "default_plant_warehouse")
	if not fg_warehouse:
		return

	for row in doc.items:
		if row.t_warehouse != fg_warehouse or not row.is_finished_item:
			continue
		if not frappe.get_cached_value("Item", row.item_code, "neoaqua_requires_qc"):
			continue
		if not row.batch_no:
			frappe.throw(
				_("Row {0}: a batch number is required for {1} before FG transfer.").format(
					row.idx, row.item_code
				)
			)
		passed = frappe.db.exists(
			"Water Quality Check",
			{
				"batch_no": row.batch_no,
				"check_type": "Finished Goods",
				"overall_result": ["in", ["Pass", "Conditional Release"]],
				"docstatus": 1,
			},
		)
		if not passed:
			frappe.throw(
				_("Batch {0} of {1} has no passed Finished Goods quality check.").format(
					frappe.bold(row.batch_no), row.item_code
				),
				title=_("QC Gate"),
			)
