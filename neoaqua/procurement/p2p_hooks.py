# Copyright (c) 2026, Neotec Integrated Solutions
"""Procure-to-pay controls for a KSA food-grade packaging supply chain."""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate


def validate_supplier_compliance(doc, method=None):
	"""A purchase order for food-contact material requires the supplier to hold
	a current SFDA registration and a valid CR."""
	needs_check = any(
		frappe.get_cached_value("Item", r.item_code, "neoaqua_food_contact") for r in doc.items
	)
	if not needs_check:
		return

	sfda = frappe.db.get_value("Supplier", doc.supplier, "neoaqua_sfda_registration")
	expiry = frappe.db.get_value("Supplier", doc.supplier, "neoaqua_cr_expiry")

	if not sfda:
		frappe.throw(
			_("Supplier {0} has no SFDA registration on file; food-contact material cannot be ordered.").format(
				frappe.bold(doc.supplier)
			)
		)
	if expiry and getdate(expiry) < getdate(nowdate()):
		frappe.throw(
			_("The Commercial Registration of {0} expired on {1}.").format(
				frappe.bold(doc.supplier), expiry
			)
		)


def validate_coa_on_receipt(doc, method=None):
	"""Block receipt of food-contact material without a Certificate of Analysis."""
	for row in doc.items:
		if not frappe.get_cached_value("Item", row.item_code, "neoaqua_food_contact"):
			continue
		if not doc.get("neoaqua_coa_reference"):
			frappe.throw(
				_("A Certificate of Analysis reference is required to receive {0}.").format(
					frappe.bold(row.item_code)
				)
			)
