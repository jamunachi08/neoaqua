# Copyright (c) 2026, Neotec Integrated Solutions

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, getdate, nowdate

def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, None, get_chart(data), get_summary(data)


def get_columns():
	return [
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Gross Sales"), "fieldname": "gross", "fieldtype": "Currency", "width": 120},
		{"label": _("Returns"), "fieldname": "returns", "fieldtype": "Currency", "width": 105},
		{"label": _("Net Sales"), "fieldname": "net", "fieldtype": "Currency", "width": 120},
		{"label": _("VAT"), "fieldname": "vat", "fieldtype": "Currency", "width": 100},
		{"label": _("Cash Sales"), "fieldname": "cash_sales", "fieldtype": "Currency", "width": 115},
		{"label": _("Credit Sales"), "fieldname": "credit_sales", "fieldtype": "Currency", "width": 115},
		{"label": _("Collections"), "fieldname": "collections", "fieldtype": "Currency", "width": 115},
		{"label": _("Route Expenses"), "fieldname": "expenses", "fieldtype": "Currency", "width": 125},
		{"label": _("Expected Cash"), "fieldname": "expected_cash", "fieldtype": "Currency", "width": 125},
		{"label": _("Declared"), "fieldname": "declared_cash", "fieldtype": "Currency", "width": 115},
		{"label": _("Variance"), "fieldname": "variance", "fieldtype": "Currency", "width": 110},
		{"label": _("Deposited"), "fieldname": "deposited", "fieldtype": "Currency", "width": 115},
	]


def get_data(filters):
	values = {
		"company": filters.get("company") or frappe.defaults.get_user_default("company"),
		"from_date": filters.get("from_date") or add_days(nowdate(), -30),
		"to_date": filters.get("to_date") or nowdate(),
	}

	sales = frappe.db.sql(
		"""select posting_date,
		          sum(case when is_return = 0 then base_grand_total else 0 end) as gross,
		          sum(case when is_return = 1 then -base_grand_total else 0 end) as returns,
		          sum(base_net_total) as net,
		          sum(base_total_taxes_and_charges) as vat,
		          sum(case when is_pos = 1 then base_grand_total else 0 end) as cash_sales,
		          sum(outstanding_amount) as credit_sales
		   from `tabSales Invoice`
		   where docstatus = 1 and company = %(company)s
		     and posting_date between %(from_date)s and %(to_date)s
		   group by posting_date""",
		values, as_dict=True,
	)

	collections = frappe.db.sql(
		"""select posting_date, sum(base_paid_amount) as collections
		   from `tabPayment Entry`
		   where docstatus = 1 and company = %(company)s and payment_type = 'Receive'
		     and posting_date between %(from_date)s and %(to_date)s
		   group by posting_date""",
		values, as_dict=True,
	)

	closes = frappe.db.sql(
		"""select posting_date, sum(total_expenses) as expenses,
		          sum(expected_cash) as expected_cash, sum(declared_cash) as declared_cash,
		          sum(cash_variance) as variance, sum(deposit_amount) as deposited
		   from `tabSalesman Day Close`
		   where docstatus = 1 and company = %(company)s
		     and posting_date between %(from_date)s and %(to_date)s
		   group by posting_date""",
		values, as_dict=True,
	)

	idx = {}
	for src in (sales, collections, closes):
		for r in src:
			row = idx.setdefault(str(r.posting_date), {"posting_date": r.posting_date})
			for k, v in r.items():
				if k != "posting_date":
					row[k] = flt(v)

	rows = sorted(idx.values(), key=lambda r: str(r["posting_date"]), reverse=True)
	return rows


def get_chart(data):
	series = list(reversed(data))[-30:]
	return {
		"data": {
			"labels": [str(d["posting_date"]) for d in series],
			"datasets": [
				{"name": _("Net Sales"), "values": [flt(d.get("net")) for d in series]},
				{"name": _("Collections"), "values": [flt(d.get("collections")) for d in series]},
			],
		},
		"type": "line",
	}


def get_summary(data):
	variance = sum(flt(d.get("variance")) for d in data)
	return [
		{"label": _("Net Sales"), "value": sum(flt(d.get("net")) for d in data), "datatype": "Currency"},
		{"label": _("VAT"), "value": sum(flt(d.get("vat")) for d in data), "datatype": "Currency"},
		{"label": _("Collections"), "value": sum(flt(d.get("collections")) for d in data), "datatype": "Currency"},
		{"label": _("Route Expenses"), "value": sum(flt(d.get("expenses")) for d in data), "datatype": "Currency"},
		{"label": _("Cash Variance"), "value": variance, "datatype": "Currency",
		 "indicator": "Red" if variance < 0 else "Green"},
	]
