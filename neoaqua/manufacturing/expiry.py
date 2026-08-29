# Copyright (c) 2026, Neotec Integrated Solutions
"""Shelf-life monitoring for bottled water batches."""

import frappe
from frappe import _
from frappe.utils import add_days, nowdate


def flag_near_expiry_batches(days=60):
	batches = frappe.db.sql(
		"""
		select b.name, b.item, b.expiry_date, sum(sle.actual_qty) as qty
		from `tabBatch` b
		join `tabStock Ledger Entry` sle on sle.batch_no = b.name and sle.is_cancelled = 0
		where b.expiry_date between %(today)s and %(horizon)s
		group by b.name, b.item, b.expiry_date
		having sum(sle.actual_qty) > 0
		""",
		{"today": nowdate(), "horizon": add_days(nowdate(), days)},
		as_dict=True,
	)
	if not batches:
		return
	rows = "".join(
		f"<tr><td>{b.name}</td><td>{b.item}</td><td>{b.expiry_date}</td><td>{b.qty}</td></tr>"
		for b in batches
	)
	msg = (
		"<p>Batches approaching shelf-life expiry:</p>"
		"<table class='table table-bordered'><thead><tr><th>Batch</th><th>Item</th>"
		f"<th>Expiry</th><th>Qty</th></tr></thead><tbody>{rows}</tbody></table>"
	)
	for user in frappe.get_all(
		"Has Role", filters={"role": "QC Inspector", "parenttype": "User"}, pluck="parent"
	):
		frappe.sendmail(recipients=user, subject=_("NeoAqua - Batches Near Expiry"), message=msg)
