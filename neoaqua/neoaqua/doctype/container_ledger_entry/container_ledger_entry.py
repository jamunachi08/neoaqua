# Copyright (c) 2026, Neotec Integrated Solutions and contributors
# For license information, please see license.txt

"""Returnable 5-gallon (18.9 L) container ledger.

Saudi home-and-office delivery works on a container-exchange model: the
customer pays a refundable deposit for the polycarbonate bottle and thereafter
swaps empty for full. The bottle itself is never revenue - it sits as a
liability until refunded, and the physical balance per customer must be
auditable. This doctype is that sub-ledger.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

IN_TYPES = ("Return (Empty In)",)
OUT_TYPES = ("Issue (Full Out)", "Lost / Damaged")


class ContainerLedgerEntry(Document):
	def validate(self):
		self.set_deposit()
		self.compute_balance()

	def on_submit(self):
		self.post_deposit_journal()

	def on_cancel(self):
		if self.journal_entry and frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus") == 1:
			frappe.get_doc("Journal Entry", self.journal_entry).cancel()

	def set_deposit(self):
		settings = frappe.get_cached_doc("NeoAqua Settings")
		if not self.item_code:
			self.item_code = settings.container_item
		if not self.deposit_rate and self.entry_type in ("Deposit Received", "Deposit Refunded"):
			self.deposit_rate = settings.container_deposit_amount
		self.deposit_amount = flt(self.qty) * flt(self.deposit_rate)

	def compute_balance(self):
		self.balance_qty = get_customer_balance(self.customer, exclude=self.name) + self.signed_qty()

	def signed_qty(self):
		if self.entry_type in OUT_TYPES or self.entry_type == "Opening Balance":
			return flt(self.qty)
		if self.entry_type in IN_TYPES:
			return -flt(self.qty)
		return 0

	def post_deposit_journal(self):
		"""Deposit received -> Dr Cash, Cr Container Deposit Liability.
		Deposit refunded -> the reverse."""
		if self.entry_type not in ("Deposit Received", "Deposit Refunded"):
			return
		settings = frappe.get_cached_doc("NeoAqua Settings")
		liability = settings.container_deposit_account
		cash = settings.cash_account
		if not (liability and cash and flt(self.deposit_amount)):
			return

		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.company = self.company
		je.posting_date = self.posting_date
		je.user_remark = _("{0} - {1} ({2} containers)").format(self.entry_type, self.customer, self.qty)

		if self.entry_type == "Deposit Received":
			debit, credit = cash, liability
		else:
			debit, credit = liability, cash

		je.append(
			"accounts",
			{
				"account": debit,
				"debit_in_account_currency": flt(self.deposit_amount),
				"party_type": "Customer" if debit == liability else None,
				"party": self.customer if debit == liability else None,
			},
		)
		je.append(
			"accounts",
			{
				"account": credit,
				"credit_in_account_currency": flt(self.deposit_amount),
				"party_type": "Customer" if credit == liability else None,
				"party": self.customer if credit == liability else None,
			},
		)
		je.insert(ignore_permissions=True)
		je.submit()
		self.db_set("journal_entry", je.name)


def get_customer_balance(customer, exclude=None):
	"""Net containers currently held by the customer."""
	if not customer:
		return 0
	filters = {"customer": customer, "docstatus": 1}
	rows = frappe.get_all(
		"Container Ledger Entry", filters=filters, fields=["entry_type", "qty", "name"]
	)
	bal = 0
	for r in rows:
		if exclude and r.name == exclude:
			continue
		if r.entry_type in OUT_TYPES or r.entry_type == "Opening Balance":
			bal += flt(r.qty)
		elif r.entry_type in IN_TYPES:
			bal -= flt(r.qty)
	return bal


@frappe.whitelist()
def customer_container_summary(customer):
	settings = frappe.get_cached_doc("NeoAqua Settings")
	held = get_customer_balance(customer)
	return {
		"containers_held": held,
		"deposit_rate": flt(settings.container_deposit_amount),
		"deposit_liability": held * flt(settings.container_deposit_amount),
	}
