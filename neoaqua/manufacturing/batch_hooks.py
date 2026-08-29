# Copyright (c) 2026, Neotec Integrated Solutions
"""Automatic batch creation and naming across the manufacturing cycle.

Three integration points:

  1. `Batch.autoname` - whenever anything creates a Batch (a Manufacture stock
     entry, a purchase receipt, a manual insert), the applicable Batch Naming
     Rule composes the code. Falls back silently to the ERPNext batch series
     when no rule matches, so installing the app never breaks existing naming.

  2. `Work Order.on_submit` - optionally reserves the batch up front. This is
     what makes the QC gate workable: quality needs a batch to test against
     before the finished goods are transferred, and a batch that only comes
     into existence at the moment of transfer is too late.

  3. `Stock Entry.validate` - stamps the reserved batch onto the finished item
     row, and carries work order, line and shift onto the batch record so the
     code can be decoded back to its origin later.
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate, nowdate

from neoaqua.manufacturing import batch_naming


# ------------------------------------------------------------------ 1. naming
def batch_autoname(doc, method=None):
	"""Compose the batch code from the applicable rule.

	Runs as a doc_event on `autoname`, which fires before Frappe's own naming,
	so setting `doc.name` here wins. If the user typed a batch id manually and
	the rule allows overrides, we leave it alone.
	"""
	if doc.get("batch_id") and doc.get("neoaqua_naming_rule"):
		return  # already composed, e.g. reserved at work order submit

	ctx = batch_naming.build_context(
		item_code=doc.item,
		work_order=doc.get("neoaqua_work_order"),
		production_line=doc.get("neoaqua_production_line"),
		shift=doc.get("neoaqua_shift"),
		posting_date=doc.get("manufacturing_date") or nowdate(),
	)
	rule = batch_naming.resolve_rule(ctx)
	if not rule:
		return  # fall through to the ERPNext batch_number_series

	if doc.get("batch_id") and rule.allow_manual_override:
		return

	code = batch_naming._ensure_unique(batch_naming.build_code(rule, ctx, preview=False))
	doc.batch_id = code
	doc.name = code
	doc.neoaqua_naming_rule = rule.name

	if rule.set_expiry_from_shelf_life and not doc.get("expiry_date"):
		expiry = batch_naming.compute_expiry(rule, ctx)
		if expiry:
			doc.expiry_date = expiry

	if not doc.get("neoaqua_production_line"):
		doc.neoaqua_production_line = ctx.get("production_line")


def batch_validate(doc, method=None):
	"""Keep the QC status column on Batch in step with submitted checks."""
	if not doc.get("neoaqua_qc_status"):
		doc.neoaqua_qc_status = "Pending"


# ------------------------------------------------------------------ 2. reserve
def reserve_batch_for_work_order(doc, method=None):
	"""Create the batch at work order submit so QC has something to test."""
	settings = frappe.get_cached_doc("NeoAqua Settings")
	if not settings.auto_create_batch_on_work_order:
		return
	if doc.get("neoaqua_batch_no"):
		return

	item = frappe.get_cached_doc("Item", doc.production_item)
	if not item.has_batch_no:
		return

	batch = frappe.new_doc("Batch")
	batch.update(
		{
			"item": doc.production_item,
			"neoaqua_work_order": doc.name,
			"neoaqua_production_line": doc.get("neoaqua_production_line"),
			"neoaqua_shift": doc.get("neoaqua_shift"),
			"neoaqua_qc_status": "Pending",
			"manufacturing_date": doc.planned_start_date or nowdate(),
			"batch_qty": 0,
			"reference_doctype": "Work Order",
			"reference_name": doc.name,
		}
	)
	batch.flags.ignore_permissions = True
	batch.insert()

	doc.db_set("neoaqua_batch_no", batch.name)
	frappe.msgprint(
		_("Batch {0} reserved for this work order.").format(frappe.bold(batch.name)),
		indicator="blue",
		alert=True,
	)
	return batch.name


def release_reserved_batch(doc, method=None):
	"""On cancel, delete an untouched reserved batch rather than leaving an
	orphan with zero quantity cluttering the batch master."""
	batch = doc.get("neoaqua_batch_no")
	if not batch or not frappe.db.exists("Batch", batch):
		return
	has_movement = frappe.db.exists("Stock Ledger Entry", {"batch_no": batch, "is_cancelled": 0})
	if has_movement:
		return
	frappe.delete_doc("Batch", batch, force=True, ignore_permissions=True)
	doc.db_set("neoaqua_batch_no", None)


# ------------------------------------------------------------------ 3. stamp
def apply_batch_to_stock_entry(doc, method=None):
	"""Push the work order's reserved batch onto the finished item row and
	carry manufacturing context onto the batch."""
	if doc.purpose != "Manufacture" or not doc.work_order:
		return

	wo = frappe.db.get_value(
		"Work Order",
		doc.work_order,
		["neoaqua_batch_no", "neoaqua_production_line", "neoaqua_shift", "production_item"],
		as_dict=True,
	)
	if not wo:
		return

	for row in doc.items:
		if not row.is_finished_item or row.item_code != wo.production_item:
			continue
		if not row.batch_no and wo.neoaqua_batch_no:
			row.batch_no = wo.neoaqua_batch_no

	if not wo.neoaqua_batch_no:
		return

	updates = {}
	if wo.neoaqua_production_line:
		updates["neoaqua_production_line"] = wo.neoaqua_production_line
	if wo.neoaqua_shift:
		updates["neoaqua_shift"] = wo.neoaqua_shift
	if doc.posting_date:
		updates["manufacturing_date"] = getdate(doc.posting_date)
	if updates:
		frappe.db.set_value("Batch", wo.neoaqua_batch_no, updates, update_modified=False)


def sync_qc_status_to_batch(doc, method=None):
	"""Called from Water Quality Check on submit."""
	if not doc.batch_no:
		return
	frappe.db.set_value(
		"Batch", doc.batch_no, "neoaqua_qc_status", doc.overall_result, update_modified=False
	)


# ------------------------------------------------------------------ utilities
@frappe.whitelist()
def create_batch_now(work_order):
	"""Manual trigger from the Work Order form."""
	doc = frappe.get_doc("Work Order", work_order)
	if doc.docstatus != 1:
		frappe.throw(_("Submit the work order first."))
	if doc.get("neoaqua_batch_no"):
		return doc.neoaqua_batch_no

	settings = frappe.get_cached_doc("NeoAqua Settings")
	original = settings.auto_create_batch_on_work_order
	settings.auto_create_batch_on_work_order = 1
	try:
		return reserve_batch_for_work_order(doc)
	finally:
		settings.auto_create_batch_on_work_order = original


@frappe.whitelist()
def backfill_naming_rule_on_batches(limit=500):
	"""One-off helper: stamp the applicable rule onto batches created before
	the rule existed, so decode_batch works retrospectively."""
	batches = frappe.get_all(
		"Batch",
		filters={"neoaqua_naming_rule": ["in", ["", None]]},
		fields=["name", "item", "neoaqua_production_line"],
		limit=cint(limit),
	)
	updated = 0
	for b in batches:
		ctx = batch_naming.build_context(
			item_code=b.item, production_line=b.neoaqua_production_line
		)
		rule = batch_naming.resolve_rule(ctx)
		if rule:
			frappe.db.set_value("Batch", b.name, "neoaqua_naming_rule", rule.name, update_modified=False)
			updated += 1
	frappe.db.commit()
	return {"scanned": len(batches), "updated": updated}
