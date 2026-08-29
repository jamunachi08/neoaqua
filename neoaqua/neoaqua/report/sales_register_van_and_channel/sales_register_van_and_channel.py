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
		{"label": _("Invoice"), "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice", "width": 140},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 90},
		{"label": _("Customer"), "fieldname": "customer_name", "fieldtype": "Data", "width": 190},
		{"label": _("Channel"), "fieldname": "customer_group", "fieldtype": "Link", "options": "Customer Group", "width": 140},
		{"label": _("Territory"), "fieldname": "territory", "fieldtype": "Link", "options": "Territory", "width": 120},
		{"label": _("Van"), "fieldname": "neoaqua_van", "fieldtype": "Link", "options": "Van", "width": 90},
		{"label": _("Salesman"), "fieldname": "neoaqua_salesman", "fieldtype": "Link", "options": "Sales Person", "width": 140},
		{"label": _("Sale Type"), "fieldname": "neoaqua_sale_type", "fieldtype": "Data", "width": 110},
		{"label": _("Net"), "fieldname": "base_net_total", "fieldtype": "Currency", "width": 110},
		{"label": _("VAT"), "fieldname": "vat_amount", "fieldtype": "Currency", "width": 95},
		{"label": _("Total"), "fieldname": "base_grand_total", "fieldtype": "Currency", "width": 115},
		{"label": _("Paid"), "fieldname": "paid", "fieldtype": "Currency", "width": 105},
		{"label": _("Outstanding"), "fieldname": "outstanding_amount", "fieldtype": "Currency", "width": 115},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 90},
	]


def get_data(filters):
	conditions = ["si.docstatus = 1"]
	values = {}
	for key, clause in (
		("company", "si.company = %(company)s"),
		("van", "si.neoaqua_van = %(van)s"),
		("salesman", "si.neoaqua_salesman = %(salesman)s"),
		("customer", "si.customer = %(customer)s"),
		("customer_group", "si.customer_group = %(customer_group)s"),
		("sale_type", "si.neoaqua_sale_type = %(sale_type)s"),
	):
		if filters.get(key):
			conditions.append(clause)
			values[key] = filters.get(key)
	if filters.get("from_date"):
		conditions.append("si.posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("si.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	rows = frappe.db.sql(
		"""
		select si.name, si.posting_date, si.customer, si.customer_name, si.customer_group,
		       si.territory, si.neoaqua_van, si.neoaqua_salesman, si.neoaqua_sale_type,
		       si.base_net_total, si.base_grand_total, si.base_total_taxes_and_charges as vat_amount,
		       si.outstanding_amount, si.status
		from `tabSales Invoice` si
		where {conditions}
		order by si.posting_date desc, si.name desc
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)
	for r in rows:
		r["paid"] = flt(r.base_grand_total) - flt(r.outstanding_amount)
	return rows


def get_summary(data):
	net = sum(flt(d.base_net_total) for d in data)
	vat = sum(flt(d.vat_amount) for d in data)
	paid = sum(flt(d["paid"]) for d in data)
	out = sum(flt(d.outstanding_amount) for d in data)
	return [
		{"label": _("Invoices"), "value": len(data), "datatype": "Int"},
		{"label": _("Net Sales"), "value": net, "datatype": "Currency"},
		{"label": _("VAT"), "value": vat, "datatype": "Currency"},
		{"label": _("Collected"), "value": paid, "datatype": "Currency", "indicator": "Green"},
		{"label": _("Outstanding"), "value": out, "datatype": "Currency",
		 "indicator": "Red" if out else "Green"},
	]
