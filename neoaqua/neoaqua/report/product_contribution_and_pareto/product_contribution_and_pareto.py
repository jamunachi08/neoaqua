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
		{"label": _("Rank"), "fieldname": "rank", "fieldtype": "Int", "width": 60},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 230},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 95},
		{"label": _("Revenue"), "fieldname": "revenue", "fieldtype": "Currency", "width": 120},
		{"label": _("Contribution"), "fieldname": "contribution", "fieldtype": "Currency", "width": 125},
		{"label": _("Contribution %"), "fieldname": "contribution_pct", "fieldtype": "Percent", "width": 120},
		{"label": _("Share of Total"), "fieldname": "share", "fieldtype": "Percent", "width": 120},
		{"label": _("Cumulative"), "fieldname": "cumulative", "fieldtype": "Percent", "width": 110},
		{"label": _("Class"), "fieldname": "abc", "fieldtype": "Data", "width": 80},
		{"label": _("Per Unit"), "fieldname": "per_unit", "fieldtype": "Currency", "width": 100},
	]


def get_data(filters):
	"""Contribution ranked, with an ABC class from the cumulative curve.

	The A items earn the plant's attention: they justify a dedicated line slot,
	a safety stock and a price review. The C tail usually costs more in
	changeovers and SKU complexity than it contributes."""
	values = {
		"company": filters.get("company") or frappe.defaults.get_user_default("company"),
		"from_date": filters.get("from_date") or add_months(nowdate(), -3),
		"to_date": filters.get("to_date") or nowdate(),
	}

	rows = frappe.db.sql(
		"""select sii.item_code, i.item_name, sum(sii.stock_qty) as qty,
		          sum(sii.base_net_amount) as revenue
		   from `tabSales Invoice Item` sii
		   join `tabSales Invoice` si on si.name = sii.parent
		   join `tabItem` i on i.name = sii.item_code
		   where si.docstatus = 1 and si.company = %(company)s
		     and si.posting_date between %(from_date)s and %(to_date)s
		   group by sii.item_code, i.item_name""",
		values, as_dict=True,
	)
	if not rows:
		return []

	cogs = {
		r.item_code: flt(r.cogs)
		for r in frappe.db.sql(
			"""select sle.item_code, sum(-1 * sle.stock_value_difference) as cogs
			   from `tabStock Ledger Entry` sle
			   join `tabSales Invoice` si on si.name = sle.voucher_no
			   where sle.voucher_type = 'Sales Invoice' and sle.is_cancelled = 0
			     and si.docstatus = 1 and si.company = %(company)s
			     and si.posting_date between %(from_date)s and %(to_date)s
			   group by sle.item_code""",
			values, as_dict=True,
		)
	}

	for r in rows:
		r["contribution"] = flt(r.revenue) - cogs.get(r.item_code, 0)
		r["contribution_pct"] = (r["contribution"] / flt(r.revenue) * 100) if flt(r.revenue) else 0
		r["per_unit"] = (r["contribution"] / flt(r.qty)) if flt(r.qty) else 0

	rows.sort(key=lambda r: r["contribution"], reverse=True)
	total = sum(r["contribution"] for r in rows) or 1

	cum = 0
	for i, r in enumerate(rows, start=1):
		r["rank"] = i
		r["share"] = r["contribution"] / total * 100
		cum += r["share"]
		r["cumulative"] = cum
		r["abc"] = "A" if cum <= 80 else ("B" if cum <= 95 else "C")
	return rows


def get_chart(data):
	top = data[:12]
	return {
		"data": {
			"labels": [d["item_code"] for d in top],
			"datasets": [{"name": _("Contribution"), "values": [flt(d["contribution"]) for d in top]}],
		},
		"type": "bar",
	}


def get_summary(data):
	a = [d for d in data if d["abc"] == "A"]
	c = [d for d in data if d["abc"] == "C"]
	total = sum(flt(d["contribution"]) for d in data)
	return [
		{"label": _("Total Contribution"), "value": total, "datatype": "Currency"},
		{"label": _("A items"), "value": len(a), "datatype": "Int", "indicator": "Green"},
		{"label": _("A items carry"), "value": sum(flt(d["share"]) for d in a), "datatype": "Percent"},
		{"label": _("C tail"), "value": len(c), "datatype": "Int", "indicator": "Orange"},
		{"label": _("C tail carries"), "value": sum(flt(d["share"]) for d in c), "datatype": "Percent"},
	]
