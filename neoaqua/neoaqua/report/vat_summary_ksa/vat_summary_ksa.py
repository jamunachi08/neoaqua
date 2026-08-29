# Copyright (c) 2026, Neotec Integrated Solutions

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, getdate, nowdate

def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, None, None, get_summary(data)


def get_columns():
	return [
		{"label": _("Period"), "fieldname": "period", "fieldtype": "Data", "width": 120},
		{"label": _("Taxable Sales"), "fieldname": "taxable_sales", "fieldtype": "Currency", "width": 140},
		{"label": _("Output VAT"), "fieldname": "output_vat", "fieldtype": "Currency", "width": 130},
		{"label": _("Sales Returns"), "fieldname": "sales_returns", "fieldtype": "Currency", "width": 130},
		{"label": _("Taxable Purchases"), "fieldname": "taxable_purchases", "fieldtype": "Currency", "width": 150},
		{"label": _("Input VAT"), "fieldname": "input_vat", "fieldtype": "Currency", "width": 130},
		{"label": _("Net VAT Payable"), "fieldname": "net_vat", "fieldtype": "Currency", "width": 150},
	]


def get_data(filters):
	"""Monthly output and input VAT with the net position.

	This summarises the ledger for review before filing. It is NOT a ZATCA
	submission and does not replace the e-invoicing layer - it tells you what
	the books say the return should look like.
	"""
	values = {
		"company": filters.get("company") or frappe.defaults.get_user_default("company"),
		"from_date": filters.get("from_date") or add_months(nowdate(), -3),
		"to_date": filters.get("to_date") or nowdate(),
	}

	sales = frappe.db.sql(
		"""select date_format(posting_date, '%%Y-%%m') as period,
		          sum(case when is_return = 0 then base_net_total else 0 end) as taxable_sales,
		          sum(case when is_return = 1 then -base_net_total else 0 end) as sales_returns,
		          sum(base_total_taxes_and_charges) as output_vat
		   from `tabSales Invoice`
		   where docstatus = 1 and company = %(company)s
		     and posting_date between %(from_date)s and %(to_date)s
		   group by period""",
		values, as_dict=True,
	)

	purchases = frappe.db.sql(
		"""select date_format(posting_date, '%%Y-%%m') as period,
		          sum(base_net_total) as taxable_purchases,
		          sum(base_total_taxes_and_charges) as input_vat
		   from `tabPurchase Invoice`
		   where docstatus = 1 and company = %(company)s
		     and posting_date between %(from_date)s and %(to_date)s
		   group by period""",
		values, as_dict=True,
	)

	idx = {}
	for r in sales:
		idx.setdefault(r.period, {"period": r.period}).update(
			{"taxable_sales": flt(r.taxable_sales), "sales_returns": flt(r.sales_returns),
			 "output_vat": flt(r.output_vat)}
		)
	for r in purchases:
		idx.setdefault(r.period, {"period": r.period}).update(
			{"taxable_purchases": flt(r.taxable_purchases), "input_vat": flt(r.input_vat)}
		)

	rows = []
	for period in sorted(idx, reverse=True):
		r = idx[period]
		r["net_vat"] = flt(r.get("output_vat")) - flt(r.get("input_vat"))
		rows.append(r)
	return rows


def get_summary(data):
	net = sum(flt(d.get("net_vat")) for d in data)
	return [
		{"label": _("Output VAT"), "value": sum(flt(d.get("output_vat")) for d in data), "datatype": "Currency"},
		{"label": _("Input VAT"), "value": sum(flt(d.get("input_vat")) for d in data), "datatype": "Currency"},
		{"label": _("Net VAT Payable"), "value": net, "datatype": "Currency",
		 "indicator": "Red" if net > 0 else "Green"},
	]
