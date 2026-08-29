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
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 220},
		{"label": _("Group"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 160},
		{"label": _("Qty Sold"), "fieldname": "qty", "fieldtype": "Float", "width": 100},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Data", "width": 70},
		{"label": _("Revenue"), "fieldname": "revenue", "fieldtype": "Currency", "width": 120},
		{"label": _("Avg Rate"), "fieldname": "avg_rate", "fieldtype": "Currency", "width": 100},
		{"label": _("Cost of Sales"), "fieldname": "cogs", "fieldtype": "Currency", "width": 120},
		{"label": _("Gross Margin"), "fieldname": "margin", "fieldtype": "Currency", "width": 120},
		{"label": _("Margin %"), "fieldname": "margin_pct", "fieldtype": "Percent", "width": 95},
		{"label": _("Invoices"), "fieldname": "invoices", "fieldtype": "Int", "width": 85},
	]


def get_data(filters):
	"""Cost comes from the stock ledger rather than the item's current
	valuation rate, so margin reflects what the goods actually cost when they
	were sold, not what a replacement would cost today."""
	conditions = ["si.docstatus = 1"]
	values = {}
	if filters.get("company"):
		conditions.append("si.company = %(company)s")
		values["company"] = filters.company
	if filters.get("from_date"):
		conditions.append("si.posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("si.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date
	if filters.get("item_group"):
		conditions.append("i.item_group = %(item_group)s")
		values["item_group"] = filters.item_group
	if filters.get("item_code"):
		conditions.append("sii.item_code = %(item_code)s")
		values["item_code"] = filters.item_code

	rows = frappe.db.sql(
		"""
		select sii.item_code, i.item_name, i.item_group, sii.uom,
		       sum(sii.stock_qty) as qty,
		       sum(sii.base_net_amount) as revenue,
		       count(distinct si.name) as invoices
		from `tabSales Invoice Item` sii
		join `tabSales Invoice` si on si.name = sii.parent
		join `tabItem` i on i.name = sii.item_code
		where {conditions}
		group by sii.item_code, i.item_name, i.item_group, sii.uom
		order by revenue desc
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)

	cogs_map = {}
	if rows:
		cogs_rows = frappe.db.sql(
			"""
			select sle.item_code, sum(-1 * sle.stock_value_difference) as cogs
			from `tabStock Ledger Entry` sle
			join `tabSales Invoice` si on si.name = sle.voucher_no
			where sle.voucher_type = 'Sales Invoice' and sle.is_cancelled = 0
			  and si.docstatus = 1 and {conditions}
			group by sle.item_code
			""".format(conditions=" and ".join(conditions).replace("i.item_group", "1=1")
			           .replace("sii.item_code = %(item_code)s", "sle.item_code = %(item_code)s")),
			values,
			as_dict=True,
		)
		cogs_map = {r.item_code: flt(r.cogs) for r in cogs_rows}

	for r in rows:
		r["cogs"] = cogs_map.get(r.item_code, 0)
		r["avg_rate"] = flt(r.revenue) / flt(r.qty) if flt(r.qty) else 0
		r["margin"] = flt(r.revenue) - flt(r["cogs"])
		r["margin_pct"] = (r["margin"] / flt(r.revenue) * 100) if flt(r.revenue) else 0
	return rows


def get_chart(data):
	top = data[:10]
	return {
		"data": {
			"labels": [d.item_code for d in top],
			"datasets": [
				{"name": _("Revenue"), "values": [flt(d.revenue) for d in top]},
				{"name": _("Margin"), "values": [flt(d["margin"]) for d in top]},
			],
		},
		"type": "bar",
	}


def get_summary(data):
	revenue = sum(flt(d.revenue) for d in data)
	margin = sum(flt(d["margin"]) for d in data)
	return [
		{"label": _("Revenue"), "value": revenue, "datatype": "Currency"},
		{"label": _("Cost of Sales"), "value": sum(flt(d["cogs"]) for d in data), "datatype": "Currency"},
		{"label": _("Gross Margin"), "value": margin, "datatype": "Currency"},
		{"label": _("Margin %"), "value": (margin / revenue * 100) if revenue else 0,
		 "datatype": "Percent", "indicator": "Green" if revenue and margin / revenue > 0.25 else "Orange"},
	]
