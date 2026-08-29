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
		{"label": _("Month"), "fieldname": "period", "fieldtype": "Data", "width": 110},
		{"label": _("Revenue"), "fieldname": "revenue", "fieldtype": "Currency", "width": 125},
		{"label": _("Receivables"), "fieldname": "receivables", "fieldtype": "Currency", "width": 130},
		{"label": _("DSO (days)"), "fieldname": "dso", "fieldtype": "Float", "width": 110},
		{"label": _("Inventory"), "fieldname": "inventory", "fieldtype": "Currency", "width": 125},
		{"label": _("Inventory Days"), "fieldname": "dio", "fieldtype": "Float", "width": 130},
		{"label": _("Payables"), "fieldname": "payables", "fieldtype": "Currency", "width": 120},
		{"label": _("DPO (days)"), "fieldname": "dpo", "fieldtype": "Float", "width": 110},
		{"label": _("Cash Cycle"), "fieldname": "ccc", "fieldtype": "Float", "width": 115},
		{"label": _("Container Deposits"), "fieldname": "deposits", "fieldtype": "Currency", "width": 145},
	]


def get_data(filters):
	"""Days sales outstanding, inventory days, days payable, and the cash
	conversion cycle between them.

	For a van-sales water plant this is the number that governs how much cash
	the business needs to stand still. Every extra day of DSO is a day of
	working capital funded by somebody."""
	company = filters.get("company") or frappe.defaults.get_user_default("company")
	months = int(filters.get("months") or 6)
	end = getdate(filters.get("to_date") or nowdate())

	rows = []
	for i in range(months - 1, -1, -1):
		period_end = getdate(add_months(end, -i))
		period_start = getdate(add_months(period_end, -1))
		days = max((period_end - period_start).days, 1)
		v = {"company": company, "start": period_start, "end": period_end}

		revenue = flt(frappe.db.sql(
			"""select sum(base_net_total) from `tabSales Invoice`
			   where docstatus = 1 and company = %(company)s
			     and posting_date between %(start)s and %(end)s""", v)[0][0])
		purchases = flt(frappe.db.sql(
			"""select sum(base_net_total) from `tabPurchase Invoice`
			   where docstatus = 1 and company = %(company)s
			     and posting_date between %(start)s and %(end)s""", v)[0][0])
		receivables = flt(frappe.db.sql(
			"""select sum(outstanding_amount) from `tabSales Invoice`
			   where docstatus = 1 and company = %(company)s and posting_date <= %(end)s""", v)[0][0])
		payables = flt(frappe.db.sql(
			"""select sum(outstanding_amount) from `tabPurchase Invoice`
			   where docstatus = 1 and company = %(company)s and posting_date <= %(end)s""", v)[0][0])
		inventory = flt(frappe.db.sql(
			"""select sum(stock_value) from `tabBin` b
			   join `tabWarehouse` w on w.name = b.warehouse
			   where w.company = %(company)s""", v)[0][0])
		cogs = flt(frappe.db.sql(
			"""select sum(-1 * sle.stock_value_difference) from `tabStock Ledger Entry` sle
			   join `tabSales Invoice` si on si.name = sle.voucher_no
			   where sle.voucher_type = 'Sales Invoice' and sle.is_cancelled = 0
			     and si.docstatus = 1 and si.company = %(company)s
			     and si.posting_date between %(start)s and %(end)s""", v)[0][0])
		deposits = flt(frappe.db.sql(
			"""select sum(case when entry_type = 'Deposit Received' then deposit_amount else 0 end)
			        - sum(case when entry_type = 'Deposit Refunded' then deposit_amount else 0 end)
			   from `tabContainer Ledger Entry`
			   where docstatus = 1 and company = %(company)s and posting_date <= %(end)s""", v)[0][0])

		dso = (receivables / revenue * days) if revenue else 0
		dio = (inventory / cogs * days) if cogs else 0
		dpo = (payables / purchases * days) if purchases else 0
		rows.append(
			{
				"period": period_end.strftime("%Y-%m"),
				"revenue": revenue, "receivables": receivables, "dso": round(dso, 1),
				"inventory": inventory, "dio": round(dio, 1),
				"payables": payables, "dpo": round(dpo, 1),
				"ccc": round(dso + dio - dpo, 1), "deposits": deposits,
			}
		)
	return rows


def get_chart(data):
	return {
		"data": {
			"labels": [d["period"] for d in data],
			"datasets": [
				{"name": _("DSO"), "values": [d["dso"] for d in data]},
				{"name": _("Inventory days"), "values": [d["dio"] for d in data]},
				{"name": _("Cash cycle"), "values": [d["ccc"] for d in data]},
			],
		},
		"type": "line",
	}


def get_summary(data):
	if not data:
		return []
	last = data[-1]
	first = data[0]
	drift = last["ccc"] - first["ccc"]
	return [
		{"label": _("DSO"), "value": last["dso"], "datatype": "Float",
		 "indicator": "Red" if last["dso"] > 45 else "Green"},
		{"label": _("Inventory days"), "value": last["dio"], "datatype": "Float"},
		{"label": _("DPO"), "value": last["dpo"], "datatype": "Float"},
		{"label": _("Cash cycle"), "value": last["ccc"], "datatype": "Float",
		 "indicator": "Red" if last["ccc"] > 60 else "Green"},
		{"label": _("Change over period"), "value": drift, "datatype": "Float",
		 "indicator": "Red" if drift > 0 else "Green"},
	]
