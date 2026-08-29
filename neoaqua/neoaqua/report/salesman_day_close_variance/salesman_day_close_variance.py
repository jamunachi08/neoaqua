# Copyright (c) 2026, Neotec Integrated Solutions

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart(data)
	summary = get_summary(data)
	return columns, data, None, chart, summary


def get_columns():
	return [
		{"label": _("Day Close"), "fieldname": "name", "fieldtype": "Link", "options": "Salesman Day Close", "width": 140},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": _("Salesman"), "fieldname": "salesman", "fieldtype": "Link", "options": "Sales Person", "width": 140},
		{"label": _("Van"), "fieldname": "van", "fieldtype": "Link", "options": "Van", "width": 100},
		{"label": _("Net Sales"), "fieldname": "net_sales", "fieldtype": "Currency", "width": 115},
		{"label": _("Cash Sales"), "fieldname": "total_cash_sales", "fieldtype": "Currency", "width": 115},
		{"label": _("Collections"), "fieldname": "total_collections", "fieldtype": "Currency", "width": 115},
		{"label": _("Expenses"), "fieldname": "total_expenses", "fieldtype": "Currency", "width": 105},
		{"label": _("Expected Cash"), "fieldname": "expected_cash", "fieldtype": "Currency", "width": 125},
		{"label": _("Declared Cash"), "fieldname": "declared_cash", "fieldtype": "Currency", "width": 125},
		{"label": _("Cash Variance"), "fieldname": "cash_variance", "fieldtype": "Currency", "width": 125},
		{"label": _("Stock Variance"), "fieldname": "stock_variance_value", "fieldtype": "Currency", "width": 125},
		{"label": _("Container Var"), "fieldname": "container_variance", "fieldtype": "Int", "width": 110},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
	]


def get_data(filters):
	conditions = ["dc.docstatus = 1"]
	values = {}
	if filters.get("from_date"):
		conditions.append("dc.posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("dc.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date
	for f in ("salesman", "van", "company"):
		if filters.get(f):
			conditions.append(f"dc.{f} = %({f})s")
			values[f] = filters.get(f)
	if filters.get("only_variance"):
		conditions.append("abs(dc.cash_variance) > 0")

	return frappe.db.sql(
		"""
		select dc.name, dc.posting_date, dc.salesman, dc.van, dc.net_sales,
		       dc.total_cash_sales, dc.total_collections, dc.total_expenses,
		       dc.expected_cash, dc.declared_cash, dc.cash_variance,
		       dc.stock_variance_value, dc.container_variance, dc.status
		from `tabSalesman Day Close` dc
		where {conditions}
		order by dc.posting_date desc
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)


def get_chart(data):
	return {
		"data": {
			"labels": [str(d.posting_date) for d in data[:30]][::-1],
			"datasets": [{"name": _("Cash Variance"), "values": [flt(d.cash_variance) for d in data[:30]][::-1]}],
		},
		"type": "bar",
		"colors": ["#e24c4c"],
	}


def get_summary(data):
	short = sum(flt(d.cash_variance) for d in data if flt(d.cash_variance) < 0)
	over = sum(flt(d.cash_variance) for d in data if flt(d.cash_variance) > 0)
	stock = sum(flt(d.stock_variance_value) for d in data)
	return [
		{"label": _("Total Cash Short"), "value": abs(short), "datatype": "Currency", "indicator": "Red"},
		{"label": _("Total Cash Over"), "value": over, "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Stock Variance Value"), "value": stock, "datatype": "Currency", "indicator": "Orange"},
		{"label": _("Settlements"), "value": len(data), "datatype": "Int"},
	]
