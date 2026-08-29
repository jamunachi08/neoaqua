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
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 175},
		{"label": _("Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 190},
		{"label": _("Channel"), "fieldname": "customer_group", "fieldtype": "Link", "options": "Customer Group", "width": 135},
		{"label": _("Revenue"), "fieldname": "revenue", "fieldtype": "Currency", "width": 115},
		{"label": _("Gross Margin"), "fieldname": "gross", "fieldtype": "Currency", "width": 120},
		{"label": _("Margin %"), "fieldname": "margin_pct", "fieldtype": "Percent", "width": 95},
		{"label": _("Visits"), "fieldname": "visits", "fieldtype": "Int", "width": 70},
		{"label": _("Cost to Serve"), "fieldname": "cost_to_serve", "fieldtype": "Currency", "width": 125},
		{"label": _("Net Contribution"), "fieldname": "net", "fieldtype": "Currency", "width": 135},
		{"label": _("Avg Drop"), "fieldname": "avg_drop", "fieldtype": "Currency", "width": 105},
		{"label": _("Days to Pay"), "fieldname": "days_to_pay", "fieldtype": "Int", "width": 105},
		{"label": _("Containers Held"), "fieldname": "containers", "fieldtype": "Int", "width": 125},
		{"label": _("Verdict"), "fieldname": "verdict", "fieldtype": "Data", "width": 135},
	]


def get_data(filters):
	"""Margin is only half the story. A customer taking small drops on a long
	route, paying late and sitting on twenty containers can be unprofitable at
	a healthy gross margin. Cost to serve makes that visible."""
	values = {
		"company": filters.get("company") or frappe.defaults.get_user_default("company"),
		"from_date": filters.get("from_date") or add_months(nowdate(), -3),
		"to_date": filters.get("to_date") or nowdate(),
	}
	visit_cost = flt(filters.get("cost_per_visit")) or 18.0

	sales = frappe.db.sql(
		"""select si.customer, si.customer_name, si.customer_group,
		          sum(si.base_net_total) as revenue, count(*) as invoices
		   from `tabSales Invoice` si
		   where si.docstatus = 1 and si.company = %(company)s
		     and si.posting_date between %(from_date)s and %(to_date)s
		   group by si.customer, si.customer_name, si.customer_group""",
		values, as_dict=True,
	)
	if not sales:
		return []

	cogs = {
		r.customer: flt(r.cogs)
		for r in frappe.db.sql(
			"""select si.customer, sum(-1 * sle.stock_value_difference) as cogs
			   from `tabStock Ledger Entry` sle
			   join `tabSales Invoice` si on si.name = sle.voucher_no
			   where sle.voucher_type = 'Sales Invoice' and sle.is_cancelled = 0
			     and si.docstatus = 1 and si.company = %(company)s
			     and si.posting_date between %(from_date)s and %(to_date)s
			   group by si.customer""",
			values, as_dict=True,
		)
	}
	visits = {
		r.customer: r.n
		for r in frappe.db.sql(
			"""select customer, count(*) as n from `tabSalesman Check In`
			   where docstatus = 1 and date(checkin_datetime) between %(from_date)s and %(to_date)s
			   group by customer""",
			values, as_dict=True,
		)
	}
	containers = {
		r.customer: flt(r.held)
		for r in frappe.db.sql(
			"""select customer,
			      sum(case when entry_type in ('Issue (Full Out)','Opening Balance','Lost / Damaged')
			               then qty else 0 end)
			    - sum(case when entry_type = 'Return (Empty In)' then qty else 0 end) as held
			   from `tabContainer Ledger Entry` where docstatus = 1 group by customer""",
			as_dict=True,
		)
	}
	paydays = {
		r.customer: flt(r.d)
		for r in frappe.db.sql(
			"""select si.customer, avg(datediff(per.posting_date, si.posting_date)) as d
			   from `tabPayment Entry Reference` per
			   join `tabPayment Entry` pe on pe.name = per.parent
			   join `tabSales Invoice` si on si.name = per.reference_name
			   where pe.docstatus = 1 and per.reference_doctype = 'Sales Invoice'
			     and si.posting_date between %(from_date)s and %(to_date)s
			   group by si.customer""",
			values, as_dict=True,
		)
	}

	rows = []
	for s in sales:
		gross = flt(s.revenue) - cogs.get(s.customer, 0)
		n_visits = visits.get(s.customer, s.invoices)
		cts = n_visits * visit_cost
		net = gross - cts
		rows.append(
			{
				"customer": s.customer, "customer_name": s.customer_name,
				"customer_group": s.customer_group, "revenue": flt(s.revenue),
				"gross": gross,
				"margin_pct": (gross / flt(s.revenue) * 100) if flt(s.revenue) else 0,
				"visits": n_visits, "cost_to_serve": cts, "net": net,
				"avg_drop": (flt(s.revenue) / s.invoices) if s.invoices else 0,
				"days_to_pay": int(paydays.get(s.customer, 0)),
				"containers": int(containers.get(s.customer, 0)),
				"verdict": _verdict(net, gross, flt(s.revenue)),
			}
		)
	rows.sort(key=lambda r: r["net"], reverse=True)
	if filters.get("only_unprofitable"):
		rows = [r for r in rows if r["net"] <= 0]
	return rows


def _verdict(net, gross, revenue):
	if net <= 0:
		return _("Loss making")
	if revenue and net / revenue < 0.05:
		return _("Marginal")
	if revenue and net / revenue > 0.20:
		return _("Star")
	return _("Healthy")


def get_summary(data):
	losers = [d for d in data if d["net"] <= 0]
	return [
		{"label": _("Customers"), "value": len(data), "datatype": "Int"},
		{"label": _("Net Contribution"), "value": sum(flt(d["net"]) for d in data), "datatype": "Currency"},
		{"label": _("Loss making"), "value": len(losers), "datatype": "Int",
		 "indicator": "Red" if losers else "Green"},
		{"label": _("Drag from loss makers"), "value": abs(sum(flt(d["net"]) for d in losers)),
		 "datatype": "Currency", "indicator": "Red"},
	]
