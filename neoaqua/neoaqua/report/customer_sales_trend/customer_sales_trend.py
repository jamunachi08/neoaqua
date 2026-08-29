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
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 170},
		{"label": _("Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 200},
		{"label": _("Channel"), "fieldname": "customer_group", "fieldtype": "Link", "options": "Customer Group", "width": 140},
		{"label": _("Route"), "fieldname": "route", "fieldtype": "Link", "options": "Van Route", "width": 140},
		{"label": _("This Period"), "fieldname": "current", "fieldtype": "Currency", "width": 120},
		{"label": _("Prev Period"), "fieldname": "previous", "fieldtype": "Currency", "width": 120},
		{"label": _("Change %"), "fieldname": "growth", "fieldtype": "Percent", "width": 100},
		{"label": _("Same Period LY"), "fieldname": "last_year", "fieldtype": "Currency", "width": 130},
		{"label": _("YoY %"), "fieldname": "yoy", "fieldtype": "Percent", "width": 90},
		{"label": _("Last Invoice"), "fieldname": "last_invoice", "fieldtype": "Date", "width": 105},
		{"label": _("Status"), "fieldname": "trend", "fieldtype": "Data", "width": 110},
	]


def _period_sales(company, start, end):
	rows = frappe.db.sql(
		"""select customer, sum(base_net_total) as total
		   from `tabSales Invoice`
		   where docstatus = 1 and company = %(company)s
		     and posting_date between %(start)s and %(end)s
		   group by customer""",
		{"company": company, "start": start, "end": end},
		as_dict=True,
	)
	return {r.customer: flt(r.total) for r in rows}


def get_data(filters):
	company = filters.get("company") or frappe.defaults.get_user_default("company")
	to_date = getdate(filters.get("to_date") or nowdate())
	from_date = getdate(filters.get("from_date") or add_months(to_date, -1))
	span = (to_date - from_date).days or 30

	current = _period_sales(company, from_date, to_date)
	previous = _period_sales(company, add_days(from_date, -span - 1), add_days(from_date, -1))
	last_year = _period_sales(company, add_months(from_date, -12), add_months(to_date, -12))

	customers = set(current) | set(previous) | set(last_year)
	if not customers:
		return []

	meta = {
		c.name: c
		for c in frappe.get_all(
			"Customer",
			filters={"name": ["in", list(customers)]},
			fields=["name", "customer_name", "customer_group", "territory", "neoaqua_route"],
		)
	}
	last_inv = {
		r.customer: r.d
		for r in frappe.db.sql(
			"""select customer, max(posting_date) as d from `tabSales Invoice`
			   where docstatus = 1 and customer in %(c)s group by customer""",
			{"c": list(customers)},
			as_dict=True,
		)
	}

	rows = []
	for c in customers:
		m = meta.get(c) or frappe._dict()
		cur, prev, ly = current.get(c, 0), previous.get(c, 0), last_year.get(c, 0)
		if filters.get("customer_group") and m.get("customer_group") != filters.customer_group:
			continue
		rows.append(
			{
				"customer": c,
				"customer_name": m.get("customer_name"),
				"customer_group": m.get("customer_group"),
				"route": m.get("neoaqua_route"),
				"current": cur,
				"previous": prev,
				"growth": ((cur - prev) / prev * 100) if prev else (100 if cur else 0),
				"last_year": ly,
				"yoy": ((cur - ly) / ly * 100) if ly else (100 if cur else 0),
				"last_invoice": last_inv.get(c),
				"trend": _classify(cur, prev),
			}
		)

	if filters.get("only_declining"):
		rows = [r for r in rows if r["trend"] in ("Declining", "Lost")]

	rows.sort(key=lambda r: r["current"], reverse=True)
	return rows


def _classify(cur, prev):
	"""A customer who bought last period and nothing this period is the single
	most actionable row in this report - name it plainly."""
	if not cur and prev:
		return _("Lost")
	if not prev and cur:
		return _("New")
	if prev and cur < prev * 0.8:
		return _("Declining")
	if prev and cur > prev * 1.2:
		return _("Growing")
	return _("Steady")


def get_summary(data):
	lost = [d for d in data if d["trend"] == _("Lost")]
	declining = [d for d in data if d["trend"] == _("Declining")]
	return [
		{"label": _("Customers"), "value": len(data), "datatype": "Int"},
		{"label": _("This Period"), "value": sum(flt(d["current"]) for d in data), "datatype": "Currency"},
		{"label": _("Lost"), "value": len(lost), "datatype": "Int",
		 "indicator": "Red" if lost else "Green"},
		{"label": _("Declining"), "value": len(declining), "datatype": "Int",
		 "indicator": "Orange" if declining else "Green"},
		{"label": _("Value at Risk"), "value": sum(flt(d["previous"]) for d in lost), "datatype": "Currency",
		 "indicator": "Red"},
	]
