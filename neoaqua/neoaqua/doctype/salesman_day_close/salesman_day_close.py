# Copyright (c) 2026, Neotec Integrated Solutions and contributors
# For license information, please see license.txt

"""Salesman Day Close / Cash Return.

The document is the single settlement point at the end of a van trip. It pulls
every invoice, credit note, payment entry and expense raised against the trip,
reconciles three independent balances, and posts the resulting entries:

    1. CASH       expected vs declared -> variance -> recovery / write-off
    2. STOCK      loaded vs sold vs returned vs damaged -> short / excess
    3. CONTAINERS full issued vs empties returned -> container variance

On submit it creates:
    * Stock Entry (van -> plant) for the returned quantity
    * Stock Entry (van -> scrap) for the damaged quantity
    * Journal Entry for the cash deposit and any variance treatment
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class SalesmanDayClose(Document):
	# ------------------------------------------------------------ lifecycle
	def validate(self):
		self.set_defaults()
		self.validate_duplicate()
		self.compute_sales_totals()
		self.compute_collection_totals()
		self.compute_expense_totals()
		self.compute_cash_reconciliation()
		self.compute_stock_variance()
		self.compute_container_variance()
		self.set_status()

	def before_submit(self):
		self.validate_variance_treatment()
		if self.status == "Draft":
			self.status = "Approved"
		self.approved_by = frappe.session.user

	def on_submit(self):
		self.post_returns()
		self.post_damages()
		self.post_cash_journal()
		self.close_trip()

	def on_cancel(self):
		self.ignore_linked_doctypes = ["GL Entry", "Stock Ledger Entry"]
		for field in ("return_stock_entry", "damaged_stock_entry", "journal_entry"):
			ref = self.get(field)
			if not ref:
				continue
			dt = "Journal Entry" if field == "journal_entry" else "Stock Entry"
			if frappe.db.get_value(dt, ref, "docstatus") == 1:
				frappe.get_doc(dt, ref).cancel()
		if self.van_trip:
			frappe.db.set_value("Van Trip", self.van_trip, {"status": "Returned", "day_close": None})

	# ------------------------------------------------------------ defaults
	def set_defaults(self):
		if not self.company:
			self.company = frappe.defaults.get_user_default("Company")
		if self.van_trip:
			trip = frappe.get_cached_doc("Van Trip", self.van_trip)
			self.van = self.van or trip.van
			self.salesman = self.salesman or trip.salesman
			self.route = trip.route
			self.posting_date = self.posting_date or trip.trip_date
		settings = frappe.get_cached_doc("NeoAqua Settings")
		if not self.deposit_account:
			self.deposit_account = settings.cash_account
		if not self.variance_account:
			# a shortage is an expense, an overage is income - pick by sign
			self.variance_account = (
				settings.cash_overage_account
				if flt(self.cash_variance) > 0
				else settings.cash_variance_account
			) or frappe.db.get_value("Company", self.company, "write_off_account")

	def validate_duplicate(self):
		if not self.van_trip:
			return
		dup = frappe.db.get_value(
			"Salesman Day Close",
			{"van_trip": self.van_trip, "docstatus": ["<", 2], "name": ["!=", self.name]},
			"name",
		)
		if dup:
			frappe.throw(_("Day Close {0} already exists for trip {1}.").format(dup, self.van_trip))

	# ------------------------------------------------------------ pull
	@frappe.whitelist()
	def fetch_trip_activity(self):
		"""Pull invoices, collections and the load sheet from the linked trip."""
		if not self.van_trip:
			frappe.throw(_("Select a Van Trip first."))

		self.set("sales_invoices", [])
		self.set("collections", [])
		self.set("stock_items", [])

		invoices = frappe.get_all(
			"Sales Invoice",
			filters={"neoaqua_van_trip": self.van_trip, "docstatus": 1},
			fields=[
				"name", "customer", "grand_total", "paid_amount",
				"outstanding_amount", "is_pos", "is_return",
			],
		)
		for inv in invoices:
			self.append(
				"sales_invoices",
				{
					"sales_invoice": inv.name,
					"customer": inv.customer,
					"grand_total": inv.grand_total,
					"paid_amount": inv.paid_amount,
					"outstanding_amount": inv.outstanding_amount,
					"is_pos": inv.is_pos,
				},
			)

		payments = frappe.get_all(
			"Payment Entry",
			filters={"neoaqua_van_trip": self.van_trip, "docstatus": 1},
			fields=["name", "party", "mode_of_payment", "reference_no", "paid_amount"],
		)
		for pe in payments:
			self.append(
				"collections",
				{
					"payment_entry": pe.name,
					"customer": pe.party,
					"mode_of_payment": pe.mode_of_payment,
					"reference_no": pe.reference_no,
					"amount": pe.paid_amount,
				},
			)

		trip = frappe.get_doc("Van Trip", self.van_trip)
		trip.pull_sold_quantities()
		for row in trip.items:
			self.append(
				"stock_items",
				{
					"item_code": row.item_code,
					"item_name": row.item_name,
					"loaded_qty": row.loaded_qty,
					"sold_qty": row.sold_qty,
					"returned_qty": row.returned_qty,
					"damaged_qty": row.damaged_qty,
					"valuation_rate": row.valuation_rate,
				},
			)
		self.containers_issued = trip.containers_delivered
		self.containers_returned_empty = trip.empties_collected
		self.save()
		return True

	# ------------------------------------------------------------ compute
	def compute_sales_totals(self):
		self.total_sales = sum(flt(r.grand_total) for r in self.sales_invoices if flt(r.grand_total) > 0)
		self.total_returns = abs(
			sum(flt(r.grand_total) for r in self.sales_invoices if flt(r.grand_total) < 0)
		)
		self.total_cash_sales = sum(flt(r.grand_total) for r in self.sales_invoices if r.is_pos)
		self.total_credit_sales = sum(
			flt(r.outstanding_amount) for r in self.sales_invoices if not r.is_pos
		)
		self.net_sales = flt(self.total_sales) - flt(self.total_returns)

	def compute_collection_totals(self):
		self.total_collections = sum(flt(r.amount) for r in self.collections)
		self.cash_collected = self._by_mode(("Cash",))
		self.card_collected = self._by_mode(("Credit Card", "Debit Card", "Mada", "Card"))
		self.transfer_collected = self._by_mode(("Bank Draft", "Wire Transfer", "Bank Transfer"))

	def _by_mode(self, modes):
		return sum(flt(r.amount) for r in self.collections if (r.mode_of_payment or "") in modes)

	def compute_expense_totals(self):
		self.default_expense_accounts()
		self.total_expenses = sum(flt(r.amount) for r in self.expenses)

	def default_expense_accounts(self):
		"""Fill the account on each expense row from the mapping in NeoAqua
		Settings, so a salesman never has to pick a GL account."""
		if not self.expenses:
			return
		settings = frappe.get_cached_doc("NeoAqua Settings")
		mapping = {r.expense_type: r.expense_account for r in (settings.route_expense_accounts or [])}
		for row in self.expenses:
			if not row.expense_account and row.expense_type:
				row.expense_account = mapping.get(row.expense_type)

	def compute_cash_reconciliation(self):
		self.expected_cash = (
			flt(self.opening_float)
			+ flt(self.total_cash_sales)
			+ flt(self.cash_collected)
			- flt(self.total_expenses)
		)
		self.cash_variance = flt(self.declared_cash) - flt(self.expected_cash)

	def compute_stock_variance(self):
		total = 0
		for row in self.stock_items:
			row.variance_qty = (
				flt(row.loaded_qty) - flt(row.sold_qty) - flt(row.returned_qty) - flt(row.damaged_qty)
			)
			row.variance_value = flt(row.variance_qty) * flt(row.valuation_rate)
			total += row.variance_value
		self.stock_variance_value = total

	def compute_container_variance(self):
		self.container_variance = flt(self.containers_issued) - flt(self.containers_returned_empty)

	def set_status(self):
		if self.docstatus == 0:
			tolerance = flt(frappe.db.get_single_value("NeoAqua Settings", "cash_variance_tolerance"))
			self.status = (
				"Pending Approval" if abs(flt(self.cash_variance)) > tolerance else "Draft"
			)

	def validate_variance_treatment(self):
		tolerance = flt(frappe.db.get_single_value("NeoAqua Settings", "cash_variance_tolerance"))
		if abs(flt(self.cash_variance)) > tolerance:
			if not self.variance_reason:
				frappe.throw(
					_("Cash variance of {0} exceeds tolerance. A Variance Reason is mandatory.").format(
						frappe.bold(frappe.utils.fmt_money(self.cash_variance, currency="SAR"))
					)
				)
			if not self.variance_treatment:
				frappe.throw(_("Select a Variance Treatment."))
			approver = frappe.db.get_single_value("NeoAqua Settings", "day_close_approver_role")
			if approver and approver not in frappe.get_roles():
				frappe.throw(
					_("Only users with the {0} role can settle a day close with a variance.").format(
						frappe.bold(approver)
					)
				)

	# ------------------------------------------------------------ postings
	def post_returns(self):
		rows = [r for r in self.stock_items if flt(r.returned_qty) > 0]
		if not rows or self.return_stock_entry:
			return
		settings = frappe.get_cached_doc("NeoAqua Settings")
		se = self._new_stock_entry(
			rows, "returned_qty",
			frappe.db.get_value("Van", self.van, "warehouse"),
			settings.default_plant_warehouse,
			_("Day close return - {0}").format(self.name),
		)
		self.db_set("return_stock_entry", se)

	def post_damages(self):
		rows = [r for r in self.stock_items if flt(r.damaged_qty) > 0]
		if not rows or self.damaged_stock_entry:
			return
		settings = frappe.get_cached_doc("NeoAqua Settings")
		se = self._new_stock_entry(
			rows, "damaged_qty",
			frappe.db.get_value("Van", self.van, "warehouse"),
			settings.scrap_warehouse or settings.default_plant_warehouse,
			_("Day close damage write-off - {0}").format(self.name),
			expense_account=settings.stock_damage_account,
		)
		self.db_set("damaged_stock_entry", se)

	def _new_stock_entry(self, rows, qty_field, source, target, remarks, expense_account=None):
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Material Transfer"
		se.company = self.company
		se.posting_date = self.posting_date
		se.set_posting_time = 1
		se.neoaqua_van_trip = self.van_trip
		se.remarks = remarks
		for row in rows:
			item = {
				"item_code": row.item_code,
				"qty": flt(row.get(qty_field)),
				"s_warehouse": source,
				"t_warehouse": target,
			}
			if expense_account:
				item["expense_account"] = expense_account
			se.append("items", item)
		se.insert(ignore_permissions=True)
		se.submit()
		return se.name

	def post_cash_journal(self):
		"""Debit the deposit account, credit the salesman cash-in-hand account,
		and route any variance to the variance account."""
		if self.journal_entry or not flt(self.deposit_amount):
			return
		settings = frappe.get_cached_doc("NeoAqua Settings")
		salesman_account = settings.cash_account
		if not (self.deposit_account and salesman_account):
			frappe.msgprint(
				_("Cash accounts are not configured in NeoAqua Settings; deposit entry skipped."),
				indicator="orange",
			)
			return

		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Cash Entry"
		je.company = self.company
		je.posting_date = self.posting_date
		je.user_remark = _("Van cash return - {0} / {1}").format(self.salesman, self.name)
		je.cheque_no = self.deposit_reference
		je.cheque_date = self.posting_date

		je.append("accounts", {"account": self.deposit_account, "debit_in_account_currency": flt(self.deposit_amount)})

		credit = flt(self.deposit_amount)
		variance = flt(self.cash_variance)
		if variance and self.variance_treatment in ("Ignore (within tolerance)", "Write Off"):
			# short cash -> expense debit; excess cash -> income credit
			if variance < 0:
				je.append(
					"accounts",
					{"account": self.variance_account, "debit_in_account_currency": abs(variance)},
				)
				credit += abs(variance)
			else:
				je.append(
					"accounts",
					{"account": self.variance_account, "credit_in_account_currency": variance},
				)
				credit -= variance

		je.append("accounts", {"account": salesman_account, "credit_in_account_currency": credit})
		je.insert(ignore_permissions=True)
		je.submit()
		self.db_set("journal_entry", je.name)
		self.db_set("status", "Settled")

	def close_trip(self):
		if self.van_trip:
			frappe.db.set_value(
				"Van Trip", self.van_trip, {"status": "Closed", "day_close": self.name}
			)


# ---------------------------------------------------------------- scheduled
def notify_pending_day_close():
	"""Daily reminder for trips returned without a settlement."""
	open_trips = frappe.db.sql(
		"""
		select vt.name, vt.van, vt.salesman, vt.trip_date
		from `tabVan Trip` vt
		left join `tabSalesman Day Close` dc
		       on dc.van_trip = vt.name and dc.docstatus = 1
		where vt.docstatus = 1 and vt.status in ('Loaded','In Progress','Returned')
		  and dc.name is null and vt.trip_date < %s
		""",
		getdate(),
		as_dict=True,
	)
	if not open_trips:
		return
	rows = "".join(
		f"<tr><td>{t.name}</td><td>{t.van}</td><td>{t.salesman}</td><td>{t.trip_date}</td></tr>"
		for t in open_trips
	)
	msg = (
		"<p>The following van trips have no submitted Day Close:</p>"
		"<table class='table table-bordered'><thead><tr><th>Trip</th><th>Van</th>"
		f"<th>Salesman</th><th>Date</th></tr></thead><tbody>{rows}</tbody></table>"
	)
	for user in frappe.get_all(
		"Has Role", filters={"role": "Van Supervisor", "parenttype": "User"}, pluck="parent"
	):
		frappe.sendmail(recipients=user, subject=_("Pending Van Day Close"), message=msg)
