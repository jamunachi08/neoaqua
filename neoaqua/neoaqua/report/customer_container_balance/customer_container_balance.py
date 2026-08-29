# Copyright (c) 2026, Neotec Integrated Solutions
"""Returnable 18.9 L container position and deposit liability by customer."""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, None, None, get_summary(data)


def get_columns():
	return [
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 200},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 200},
		{"label": _("Territory"), "fieldname": "territory", "fieldtype": "Link", "options": "Territory", "width": 130},
		{"label": _("Issued"), "fieldname": "issued", "fieldtype": "Float", "width": 90},
		{"label": _("Returned"), "fieldname": "returned", "fieldtype": "Float", "width": 90},
		{"label": _("Lost / Damaged"), "fieldname": "lost", "fieldtype": "Float", "width": 120},
		{"label": _("Balance Held"), "fieldname": "balance", "fieldtype": "Float", "width": 115},
		{"label": _("Deposit Held"), "fieldname": "deposit_held", "fieldtype": "Currency", "width": 125},
		{"label": _("Deposit Liability"), "fieldname": "liability", "fieldtype": "Currency", "width": 135},
		{"label": _("Exposure"), "fieldname": "exposure", "fieldtype": "Currency", "width": 120},
	]


def get_data(filters):
	conditions = ["cle.docstatus = 1"]
	values = {}
	if filters.get("customer"):
		conditions.append("cle.customer = %(customer)s")
		values["customer"] = filters.customer
	if filters.get("company"):
		conditions.append("cle.company = %(company)s")
		values["company"] = filters.company
	if filters.get("as_on_date"):
		conditions.append("cle.posting_date <= %(as_on_date)s")
		values["as_on_date"] = filters.as_on_date

	rows = frappe.db.sql(
		"""
		select cle.customer, cle.customer_name, c.territory,
		       sum(case when cle.entry_type in ('Issue (Full Out)','Opening Balance') then cle.qty else 0 end) as issued,
		       sum(case when cle.entry_type = 'Return (Empty In)' then cle.qty else 0 end) as returned,
		       sum(case when cle.entry_type = 'Lost / Damaged' then cle.qty else 0 end) as lost,
		       sum(case when cle.entry_type = 'Deposit Received' then cle.deposit_amount else 0 end) -
		       sum(case when cle.entry_type = 'Deposit Refunded' then cle.deposit_amount else 0 end) as deposit_held
		from `tabContainer Ledger Entry` cle
		left join `tabCustomer` c on c.name = cle.customer
		where {conditions}
		group by cle.customer, cle.customer_name, c.territory
		order by 7 desc
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)

	rate = flt(frappe.db.get_single_value("NeoAqua Settings", "container_deposit_amount"))
	for r in rows:
		r["balance"] = flt(r.issued) - flt(r.returned)
		r["liability"] = flt(r.balance) * rate
		r["exposure"] = flt(r.liability) - flt(r.deposit_held)
	if filters.get("only_exposure"):
		rows = [r for r in rows if flt(r["exposure"]) > 0]
	return rows


def get_summary(data):
	return [
		{"label": _("Containers in Market"), "value": sum(flt(d["balance"]) for d in data), "datatype": "Float"},
		{"label": _("Deposits Held"), "value": sum(flt(d["deposit_held"]) for d in data), "datatype": "Currency"},
		{"label": _("Uncovered Exposure"), "value": sum(flt(d["exposure"]) for d in data), "datatype": "Currency", "indicator": "Red"},
	]
