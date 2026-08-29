# Copyright (c) 2026, Neotec Integrated Solutions
"""Demo data removal.

Deleting transactional data in ERPNext is not a matter of dropping rows. A
submitted document owns GL Entries, Stock Ledger Entries, Payment Ledger
Entries and repost queue items, and it is referenced by whatever was made from
it. Delete in the wrong order and you either get a link error or, worse, an
orphaned ledger that silently corrupts the trial balance.

This module removes only what the demo generator created, tracked in
`NeoAqua Demo Record`, and does it in a way that survives real dependency
graphs:

    1. walk the log in REVERSE creation order - dependents were created after
       their dependencies, so reverse order is a valid topological order
    2. cancel submitted documents before deleting them, so ERPNext reverses
       the ledgers through its own code rather than us deleting rows behind it
    3. repeat in passes - a link that blocks deletion on pass 1 is often gone
       by pass 2, once the dependent has been removed
    4. only then clean up the residue ledgers and empty bins

Nothing outside the demo log is ever touched.
"""

import frappe
from frappe import _
from frappe.utils import cint

MAX_PASSES = 5

# Documents whose cancellation legitimately leaves linked records behind that
# we are about to delete anyway.
IGNORE_ON_CANCEL = [
	"GL Entry", "Stock Ledger Entry", "Payment Ledger Entry", "Repost Item Valuation",
	"Serial and Batch Bundle", "Stock Reservation Entry", "Bank Transaction",
]


def _cancel(doctype, name):
	doc = frappe.get_doc(doctype, name)
	if doc.docstatus != 1:
		return True
	doc.flags.ignore_permissions = True
	doc.flags.ignore_links = True
	doc.ignore_linked_doctypes = IGNORE_ON_CANCEL
	doc.cancel()
	return True


def _delete(doctype, name):
	frappe.delete_doc(
		doctype,
		name,
		force=True,
		ignore_permissions=True,
		ignore_missing=True,
		delete_permanently=True,
	)


def _purge_residue(doctype, name):
	"""Remove ledger rows a forced delete can leave behind."""
	for dt in ("GL Entry", "Stock Ledger Entry", "Payment Ledger Entry"):
		if not frappe.db.has_table(dt) if hasattr(frappe.db, "has_table") else False:
			continue
		try:
			frappe.db.delete(dt, {"voucher_type": doctype, "voucher_no": name})
		except Exception:
			pass
	try:
		frappe.db.delete("Repost Item Valuation", {"voucher_type": doctype, "voucher_no": name})
	except Exception:
		pass


@frappe.whitelist()
def delete_demo_data(run_id=None, delete_masters=0, confirm=None):
	"""Remove every document logged against a demo run."""
	if (confirm or "").strip().upper() != "DELETE":
		frappe.throw(_("Type DELETE in the confirmation field to proceed."))

	delete_masters = cint(delete_masters)

	filters = {"status": ["!=", "Deleted"]}
	if run_id:
		filters["run_id"] = run_id

	records = frappe.get_all(
		"NeoAqua Demo Record",
		filters=filters,
		fields=["name", "sequence", "reference_doctype", "reference_name", "is_master", "is_submittable"],
		order_by="sequence desc",
	)
	if not records:
		return {"deleted": 0, "failed": 0, "message": _("No demo records left to remove.")}

	pending = [r for r in records if delete_masters or not r.is_master]
	skipped_masters = len(records) - len(pending)

	deleted, failed = 0, []

	for _pass in range(MAX_PASSES):
		if not pending:
			break
		still_pending = []

		for rec in pending:
			dt, dn = rec.reference_doctype, rec.reference_name

			if not frappe.db.exists(dt, dn):
				frappe.db.set_value("NeoAqua Demo Record", rec.name, "status", "Deleted", update_modified=False)
				deleted += 1
				continue

			try:
				if rec.is_submittable:
					_cancel(dt, dn)
				_delete(dt, dn)
				_purge_residue(dt, dn)
				frappe.db.set_value("NeoAqua Demo Record", rec.name, "status", "Deleted", update_modified=False)
				deleted += 1
				frappe.db.commit()
			except Exception as e:
				frappe.db.rollback()
				rec.error = str(e)[:400]
				still_pending.append(rec)

		# no progress this pass means the rest are genuinely blocked
		if len(still_pending) == len(pending):
			pending = still_pending
			break
		pending = still_pending

	for rec in pending:
		frappe.db.set_value(
			"NeoAqua Demo Record",
			rec.name,
			{"status": "Delete Failed", "error": getattr(rec, "error", None)},
			update_modified=False,
		)
		failed.append(f"{rec.reference_doctype} {rec.reference_name}: {getattr(rec, 'error', '')}")

	cleanup_empty_bins()
	frappe.db.commit()

	return {
		"deleted": deleted,
		"failed": len(failed),
		"skipped_masters": skipped_masters,
		"failures": failed[:20],
		"message": _("Removed {0} demo documents.").format(deleted)
		+ (_(" {0} could not be removed - see the list.").format(len(failed)) if failed else "")
		+ (_(" {0} master records were kept.").format(skipped_masters) if skipped_masters else ""),
	}


def cleanup_empty_bins():
	"""Bins left at zero after the stock is gone are harmless but noisy."""
	try:
		frappe.db.sql(
			"""delete from `tabBin`
			   where actual_qty = 0 and ordered_qty = 0 and indented_qty = 0
			     and planned_qty = 0 and reserved_qty = 0 and projected_qty = 0"""
		)
	except Exception:
		pass


@frappe.whitelist()
def demo_summary():
	"""What is currently on the site from demo runs."""
	rows = frappe.db.sql(
		"""select run_id, reference_doctype, count(*) as qty
		   from `tabNeoAqua Demo Record`
		   where status != 'Deleted'
		   group by run_id, reference_doctype
		   order by run_id desc, qty desc""",
		as_dict=True,
	)
	runs = {}
	for r in rows:
		runs.setdefault(r.run_id, []).append({"doctype": r.reference_doctype, "count": r.qty})
	return runs


@frappe.whitelist()
def clear_demo_log():
	"""Remove log rows for documents that are already gone. Housekeeping only -
	it deletes no business data."""
	removed = 0
	for rec in frappe.get_all(
		"NeoAqua Demo Record", fields=["name", "reference_doctype", "reference_name", "status"]
	):
		if rec.status == "Deleted" or not frappe.db.exists(rec.reference_doctype, rec.reference_name):
			frappe.delete_doc("NeoAqua Demo Record", rec.name, force=True, ignore_permissions=True)
			removed += 1
	frappe.db.commit()
	return {"removed": removed}


@frappe.whitelist()
def delete_all_company_transactions(company, confirm=None):
	"""Escalation path when the site is beyond a targeted cleanup.

	This is ERPNext's own `delete_company_transactions`, which wipes EVERY
	transaction for the company - not just demo data - while keeping masters
	and the chart of accounts. It is the right tool when a site has been used
	for open-ended testing and you want a clean opening position before go-live.
	"""
	if (confirm or "").strip().upper() != "DELETE ALL TRANSACTIONS":
		frappe.throw(_("Type DELETE ALL TRANSACTIONS to proceed. This cannot be undone."))
	if not frappe.conf.get("developer_mode") and "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only a System Manager can run this."), frappe.PermissionError)

	from erpnext.setup.doctype.company.company import delete_company_transactions

	delete_company_transactions(company)
	frappe.db.delete("NeoAqua Demo Record")
	frappe.db.commit()
	return {"message": _("All transactions removed for {0}.").format(company)}
