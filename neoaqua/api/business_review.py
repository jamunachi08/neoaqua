# Copyright (c) 2026, Neotec Integrated Solutions
"""Business Review — the pack that goes to management.

Every report in this app answers one question. A board or an owner does not
read fifteen reports; they read one document that says what happened, what it
cost, what is at risk and what is planned. This assembles that document from
the same data the reports use, and delivers it three ways:

    print   - a laid-out HTML page sized for A4
    PDF     - the same, rendered and attached
    email   - sent to a distribution list, on demand or monthly
    Excel   - the underlying tables, for anyone who wants to re-cut them

The commentary lines are generated from the numbers, not written in advance:
a section that says "route 2 is loss-making" says it because the arithmetic
found it, and stays silent when it did not.
"""

import json

import frappe
from frappe import _
from frappe.utils import (add_months, flt, fmt_money, get_first_day, get_last_day,
                          getdate, now_datetime, nowdate)


# ---------------------------------------------------------------- helpers
def _period(from_date=None, to_date=None):
	if from_date and to_date:
		return getdate(from_date), getdate(to_date)
	today = getdate(nowdate())
	last_month = add_months(today, -1)
	return get_first_day(last_month), get_last_day(last_month)


def _sar(v):
	return fmt_money(flt(v), currency="SAR")


def _delta(current, previous):
	if not previous:
		return None
	return (flt(current) - flt(previous)) / flt(previous) * 100


def _one(sql, values):
	try:
		return flt(frappe.db.sql(sql, values)[0][0])
	except Exception:
		return 0.0


# ---------------------------------------------------------------- sections
def headline(company, start, end):
	prev_start, prev_end = add_months(start, -1), add_months(end, -1)
	ly_start, ly_end = add_months(start, -12), add_months(end, -12)
	v = {"c": company, "s": start, "e": end}
	pv = {"c": company, "s": prev_start, "e": prev_end}
	lv = {"c": company, "s": ly_start, "e": ly_end}

	rev_sql = """select sum(base_net_total) from `tabSales Invoice`
	             where docstatus = 1 and company = %(c)s and is_return = 0
	               and posting_date between %(s)s and %(e)s"""
	cogs_sql = """select sum(-1 * sle.stock_value_difference) from `tabStock Ledger Entry` sle
	              join `tabSales Invoice` si on si.name = sle.voucher_no
	              where sle.voucher_type = 'Sales Invoice' and sle.is_cancelled = 0
	                and si.docstatus = 1 and si.company = %(c)s
	                and si.posting_date between %(s)s and %(e)s"""

	revenue, prev_rev, ly_rev = _one(rev_sql, v), _one(rev_sql, pv), _one(rev_sql, lv)
	cogs = _one(cogs_sql, v)
	collections = _one(
		"""select sum(base_paid_amount) from `tabPayment Entry`
		   where docstatus = 1 and company = %(c)s and payment_type = 'Receive'
		     and posting_date between %(s)s and %(e)s""", v)
	receivables = _one(
		"""select sum(outstanding_amount) from `tabSales Invoice`
		   where docstatus = 1 and company = %(c)s""", v)
	expenses = _one(
		"""select sum(total_expenses) from `tabSalesman Day Close`
		   where docstatus = 1 and company = %(c)s and posting_date between %(s)s and %(e)s""", v)
	variance = _one(
		"""select sum(cash_variance) from `tabSalesman Day Close`
		   where docstatus = 1 and company = %(c)s and posting_date between %(s)s and %(e)s""", v)
	produced = _one(
		"""select sum(sed.qty) from `tabStock Entry Detail` sed
		   join `tabStock Entry` se on se.name = sed.parent
		   where se.docstatus = 1 and se.purpose = 'Manufacture' and se.company = %(c)s
		     and se.posting_date between %(s)s and %(e)s and sed.is_finished_item = 1""", v)

	gross = revenue - cogs
	return {
		"revenue": revenue, "revenue_vs_prev": _delta(revenue, prev_rev),
		"revenue_vs_ly": _delta(revenue, ly_rev),
		"cogs": cogs, "gross": gross,
		"gross_pct": (gross / revenue * 100) if revenue else 0,
		"collections": collections,
		"collection_ratio": (collections / revenue * 100) if revenue else 0,
		"receivables": receivables, "route_expenses": expenses,
		"cash_variance": variance, "produced": produced,
	}


def channel_mix(company, start, end):
	return frappe.db.sql(
		"""select coalesce(customer_group, 'Unassigned') as channel,
		          sum(base_net_total) as revenue, count(*) as invoices,
		          count(distinct customer) as customers
		   from `tabSales Invoice`
		   where docstatus = 1 and company = %(c)s and is_return = 0
		     and posting_date between %(s)s and %(e)s
		   group by customer_group order by revenue desc""",
		{"c": company, "s": start, "e": end}, as_dict=True,
	)


def route_performance(company, start, end):
	trips = frappe.db.sql(
		"""select route, van, count(*) as trips, avg(coverage_pct) as coverage
		   from `tabVan Trip` where docstatus = 1 and company = %(c)s
		     and trip_date between %(s)s and %(e)s group by route, van""",
		{"c": company, "s": start, "e": end}, as_dict=True,
	)
	rev = {
		r.van: flt(r.revenue)
		for r in frappe.db.sql(
			"""select neoaqua_van as van, sum(base_net_total) as revenue
			   from `tabSales Invoice` where docstatus = 1 and company = %(c)s
			     and posting_date between %(s)s and %(e)s and neoaqua_van is not null
			   group by neoaqua_van""",
			{"c": company, "s": start, "e": end}, as_dict=True,
		)
	}
	exp = {
		r.van: (flt(r.expenses), flt(r.losses))
		for r in frappe.db.sql(
			"""select van, sum(total_expenses) as expenses,
			          sum(abs(stock_variance_value)) as losses
			   from `tabSalesman Day Close` where docstatus = 1 and company = %(c)s
			     and posting_date between %(s)s and %(e)s group by van""",
			{"c": company, "s": start, "e": end}, as_dict=True,
		)
	}
	out = []
	for t in trips:
		e, l = exp.get(t.van, (0, 0))
		r = rev.get(t.van, 0)
		out.append({
			"route": t.route, "van": t.van, "trips": t.trips,
			"coverage": flt(t.coverage), "revenue": r,
			"expenses": e + l, "net": r - e - l,
		})
	out.sort(key=lambda x: x["revenue"], reverse=True)
	return out


def top_products(company, start, end, limit=8):
	return frappe.db.sql(
		"""select sii.item_code, i.item_name, sum(sii.stock_qty) as qty,
		          sum(sii.base_net_amount) as revenue
		   from `tabSales Invoice Item` sii
		   join `tabSales Invoice` si on si.name = sii.parent
		   join `tabItem` i on i.name = sii.item_code
		   where si.docstatus = 1 and si.company = %(c)s
		     and si.posting_date between %(s)s and %(e)s
		   group by sii.item_code, i.item_name
		   order by revenue desc limit %(l)s""",
		{"c": company, "s": start, "e": end, "l": limit}, as_dict=True,
	)


def customer_movement(company, start, end):
	prev_start, prev_end = add_months(start, -1), add_months(end, -1)

	def sales(s, e):
		return {
			r.customer: flt(r.total)
			for r in frappe.db.sql(
				"""select customer, sum(base_net_total) as total from `tabSales Invoice`
				   where docstatus = 1 and company = %(c)s and posting_date between %(s)s and %(e)s
				   group by customer""",
				{"c": company, "s": s, "e": e}, as_dict=True,
			)
		}

	cur, prev = sales(start, end), sales(prev_start, prev_end)
	won = [c for c in cur if c not in prev]
	lost = [c for c in prev if c not in cur]
	names = {}
	if won or lost:
		names = {
			r.name: r.customer_name
			for r in frappe.get_all("Customer", filters={"name": ["in", won + lost]},
			                        fields=["name", "customer_name"])
		}
	return {
		"won": [{"customer": c, "name": names.get(c, c), "value": cur[c]} for c in won][:10],
		"lost": [{"customer": c, "name": names.get(c, c), "value": prev[c]} for c in lost][:10],
		"lost_value": sum(prev[c] for c in lost),
		"won_value": sum(cur[c] for c in won),
	}


def production_summary(company, start, end):
	wo = frappe.db.sql(
		"""select coalesce(neoaqua_production_line, 'Unassigned') as line,
		          sum(qty) as planned, sum(produced_qty) as produced, count(*) as orders
		   from `tabWork Order` where docstatus = 1 and company = %(c)s
		     and creation between %(s)s and %(e)s
		   group by neoaqua_production_line""",
		{"c": company, "s": start, "e": end}, as_dict=True,
	)
	for r in wo:
		r["yield_pct"] = (flt(r.produced) / flt(r.planned) * 100) if flt(r.planned) else 0

	qc = frappe.db.sql(
		"""select overall_result, count(*) as n from `tabWater Quality Check`
		   where docstatus = 1 and posting_date between %(s)s and %(e)s group by overall_result""",
		{"s": start, "e": end}, as_dict=True,
	)
	total = sum(r.n for r in qc) or 0
	passed = sum(r.n for r in qc if r.overall_result in ("Pass", "Conditional Release"))
	return {
		"lines": wo, "qc_total": total,
		"qc_pass_rate": (passed / total * 100) if total else None,
		"qc_failed": sum(r.n for r in qc if r.overall_result == "Fail"),
	}


def risk_register(company, start, end):
	"""What management should be told without being asked."""
	risks = []

	def add(sev, headline_text, detail):
		risks.append({"severity": sev, "headline": headline_text, "detail": detail})

	over90 = _one(
		"""select sum(outstanding_amount) from `tabSales Invoice`
		   where docstatus = 1 and company = %(c)s and outstanding_amount > 0
		     and posting_date < date_sub(%(e)s, interval 90 day)""",
		{"c": company, "e": end})
	if over90 > 0:
		add("high", _("Receivables over 90 days"),
		    _("{0} is more than ninety days old and should be treated as at risk.").format(_sar(over90)))

	variance = _one(
		"""select sum(cash_variance) from `tabSalesman Day Close`
		   where docstatus = 1 and company = %(c)s and posting_date between %(s)s and %(e)s""",
		{"c": company, "s": start, "e": end})
	if variance < -1:
		add("high", _("Cash shortages at day close"),
		    _("Net {0} short across the period. Review the salesmen concerned.").format(_sar(abs(variance))))

	failed = frappe.db.count("Water Quality Check",
	                         {"docstatus": 1, "overall_result": "Fail",
	                          "posting_date": ["between", [start, end]]})
	if failed:
		add("high", _("Failed quality checks"),
		    _("{0} batch(es) failed and were blocked from release.").format(failed))

	containers = _one(
		"""select sum(case when entry_type in ('Issue (Full Out)','Opening Balance','Lost / Damaged')
		            then qty else 0 end)
		        - sum(case when entry_type = 'Return (Empty In)' then qty else 0 end)
		   from `tabContainer Ledger Entry` where docstatus = 1 and company = %(c)s""",
		{"c": company})
	rate = flt(frappe.db.get_single_value("NeoAqua Settings", "container_deposit_amount"))
	if containers and rate:
		add("medium", _("Returnable containers in the market"),
		    _("{0} containers, a deposit exposure of {1}.").format(int(containers), _sar(containers * rate)))

	expired = frappe.db.count("Supplier", {"neoaqua_cr_expiry": ["<", nowdate()]})
	if expired:
		add("low", _("Suppliers with an expired CR"),
		    _("{0} supplier(s). Food-contact purchase orders to them are blocked.").format(expired))

	return risks


def commentary(h, routes, movement, production):
	"""Plain sentences derived from the numbers. Nothing is asserted that the
	arithmetic did not find."""
	lines = []

	if h["revenue_vs_prev"] is not None:
		direction = _("up") if h["revenue_vs_prev"] >= 0 else _("down")
		lines.append(_("Revenue of {0} is {1} {2}% on the previous period.").format(
			_sar(h["revenue"]), direction, abs(round(h["revenue_vs_prev"], 1))))
	else:
		lines.append(_("Revenue of {0}.").format(_sar(h["revenue"])))

	if h["revenue_vs_ly"] is not None:
		lines.append(_("Against the same period last year the movement is {0}%.").format(
			round(h["revenue_vs_ly"], 1)))

	lines.append(_("Gross margin {0}%, after cost of sales of {1}.").format(
		round(h["gross_pct"], 1), _sar(h["cogs"])))

	if h["collection_ratio"] < 85 and h["revenue"]:
		lines.append(_("Collections covered only {0}% of revenue; receivables now stand at {1}.").format(
			round(h["collection_ratio"], 1), _sar(h["receivables"])))
	elif h["revenue"]:
		lines.append(_("Collections covered {0}% of revenue.").format(round(h["collection_ratio"], 1)))

	losers = [r for r in routes if r["net"] < 0]
	if losers:
		lines.append(_("{0} route(s) did not cover their own cost: {1}.").format(
			len(losers), ", ".join(str(r["van"] or r["route"]) for r in losers)))

	if movement["lost"]:
		lines.append(_("{0} customer(s) bought nothing this period, worth {1} previously.").format(
			len(movement["lost"]), _sar(movement["lost_value"])))
	if movement["won"]:
		lines.append(_("{0} new or returning customer(s) contributed {1}.").format(
			len(movement["won"]), _sar(movement["won_value"])))

	if production["qc_pass_rate"] is not None and production["qc_pass_rate"] < 98:
		lines.append(_("Quality pass rate {0}% with {1} failure(s).").format(
			round(production["qc_pass_rate"], 1), production["qc_failed"]))

	return lines


# ---------------------------------------------------------------- assemble
@frappe.whitelist()
def build(company=None, from_date=None, to_date=None):
	company = company or frappe.defaults.get_user_default("company") \
		or frappe.defaults.get_global_default("company")
	if not company:
		frappe.throw(_("Select a Company."))
	start, end = _period(from_date, to_date)

	h = headline(company, start, end)
	routes = route_performance(company, start, end)
	movement = customer_movement(company, start, end)
	production = production_summary(company, start, end)

	return {
		"company": company,
		"brand": frappe.db.get_single_value("NeoAqua Settings", "brand_name"),
		"from_date": str(start), "to_date": str(end),
		"generated": str(now_datetime()),
		"generated_by": frappe.session.user,
		"headline": h,
		"channels": channel_mix(company, start, end),
		"routes": routes,
		"products": top_products(company, start, end),
		"movement": movement,
		"production": production,
		"risks": risk_register(company, start, end),
		"commentary": commentary(h, routes, movement, production),
	}


# ---------------------------------------------------------------- render
def render_html(pack):
	"""A4-width HTML used for the on-screen view, the print view and the PDF.
	One template, so what is emailed is what was reviewed."""
	h = pack["headline"]

	def kpi(label, value, sub=""):
		return (f'<div class="k"><div class="kl">{label}</div><div class="kv">{value}</div>'
		        f'<div class="ks">{sub}</div></div>')

	def pct(v):
		if v is None:
			return ""
		arrow = "&#9650;" if v >= 0 else "&#9660;"
		colour = "#15803D" if v >= 0 else "#B91C1C"
		return f'<span style="color:{colour}">{arrow} {abs(round(v, 1))}%</span>'

	kpis = "".join([
		kpi(_("Revenue"), _sar(h["revenue"]), pct(h["revenue_vs_prev"]) + _(" vs prev")),
		kpi(_("Gross margin"), f'{round(h["gross_pct"], 1)}%', _sar(h["gross"])),
		kpi(_("Collections"), _sar(h["collections"]), f'{round(h["collection_ratio"], 1)}% ' + _("of revenue")),
		kpi(_("Receivables"), _sar(h["receivables"]), ""),
		kpi(_("Units produced"), f'{int(h["produced"]):,}', ""),
		kpi(_("Cash variance"), _sar(h["cash_variance"]), ""),
	])

	commentary_html = "".join(f"<li>{c}</li>" for c in pack["commentary"])

	channels = "".join(
		f'<tr><td>{c.get("channel")}</td><td class="r">{c.get("customers")}</td>'
		f'<td class="r">{c.get("invoices")}</td><td class="r">{_sar(c.get("revenue"))}</td></tr>'
		for c in pack["channels"]
	) or '<tr><td colspan="4" class="m">' + _("No sales in the period.") + "</td></tr>"

	routes = "".join(
		f'<tr><td>{r["route"] or "—"}</td><td>{r["van"] or "—"}</td><td class="r">{r["trips"]}</td>'
		f'<td class="r">{round(r["coverage"])}%</td><td class="r">{_sar(r["revenue"])}</td>'
		f'<td class="r">{_sar(r["expenses"])}</td>'
		f'<td class="r" style="color:{"#B91C1C" if r["net"] < 0 else "#0F172A"}">{_sar(r["net"])}</td></tr>'
		for r in pack["routes"]
	) or '<tr><td colspan="7" class="m">' + _("No trips in the period.") + "</td></tr>"

	products = "".join(
		f'<tr><td>{p.get("item_name") or p.get("item_code")}</td>'
		f'<td class="r">{int(flt(p.get("qty"))):,}</td><td class="r">{_sar(p.get("revenue"))}</td></tr>'
		for p in pack["products"]
	) or '<tr><td colspan="3" class="m">—</td></tr>'

	lines = "".join(
		f'<tr><td>{l.get("line")}</td><td class="r">{l.get("orders")}</td>'
		f'<td class="r">{int(flt(l.get("planned"))):,}</td>'
		f'<td class="r">{int(flt(l.get("produced"))):,}</td>'
		f'<td class="r">{round(flt(l.get("yield_pct")), 1)}%</td></tr>'
		for l in pack["production"]["lines"]
	) or '<tr><td colspan="5" class="m">' + _("No production in the period.") + "</td></tr>"

	movement = ""
	if pack["movement"]["lost"]:
		movement += "<p><b>" + _("Customers lost") + "</b><br>" + ", ".join(
			f'{m["name"]} ({_sar(m["value"])})' for m in pack["movement"]["lost"]) + "</p>"
	if pack["movement"]["won"]:
		movement += "<p><b>" + _("New or returning") + "</b><br>" + ", ".join(
			f'{m["name"]} ({_sar(m["value"])})' for m in pack["movement"]["won"]) + "</p>"
	movement = movement or f'<p class="m">{_("No change in the customer base.")}</p>'

	risks = "".join(
		f'<div class="risk {r["severity"]}"><b>{r["headline"]}</b><div>{r["detail"]}</div></div>'
		for r in pack["risks"]
	) or f'<p class="m">{_("Nothing flagged.")}</p>'

	return f"""
<div class="brv">
  <div class="hd">
    <div>
      <div class="t">{pack.get("brand") or pack["company"]}</div>
      <div class="s">{_("Business Review")} &middot; {pack["from_date"]} &rarr; {pack["to_date"]}</div>
    </div>
    <div class="g">{_("Generated")} {pack["generated"][:16]}<br>{pack["generated_by"]}</div>
  </div>

  <div class="kpis">{kpis}</div>

  <h3>{_("Summary")}</h3>
  <ul class="cmt">{commentary_html}</ul>

  <h3>{_("Sales by channel")}</h3>
  <table><thead><tr><th>{_("Channel")}</th><th class="r">{_("Customers")}</th>
    <th class="r">{_("Invoices")}</th><th class="r">{_("Revenue")}</th></tr></thead>
    <tbody>{channels}</tbody></table>

  <h3>{_("Route performance")}</h3>
  <table><thead><tr><th>{_("Route")}</th><th>{_("Van")}</th><th class="r">{_("Trips")}</th>
    <th class="r">{_("Coverage")}</th><th class="r">{_("Revenue")}</th>
    <th class="r">{_("Cost")}</th><th class="r">{_("Net")}</th></tr></thead>
    <tbody>{routes}</tbody></table>

  <h3>{_("Top products")}</h3>
  <table><thead><tr><th>{_("Product")}</th><th class="r">{_("Qty")}</th>
    <th class="r">{_("Revenue")}</th></tr></thead><tbody>{products}</tbody></table>

  <h3>{_("Production")}</h3>
  <table><thead><tr><th>{_("Line")}</th><th class="r">{_("Orders")}</th>
    <th class="r">{_("Planned")}</th><th class="r">{_("Produced")}</th>
    <th class="r">{_("Yield")}</th></tr></thead><tbody>{lines}</tbody></table>
  <p class="m">{_("Quality checks")}: {pack["production"]["qc_total"]},
    {_("pass rate")} {round(pack["production"]["qc_pass_rate"], 1) if pack["production"]["qc_pass_rate"] is not None else "—"}%,
    {pack["production"]["qc_failed"]} {_("failed")}.</p>

  <h3>{_("Customer movement")}</h3>
  {movement}

  <h3>{_("Risks and exceptions")}</h3>
  {risks}
</div>
<style>
  .brv{{font-family:"Segoe UI",Arial,sans-serif;color:#0F172A;font-size:12px;max-width:800px}}
  .brv .hd{{display:flex;justify-content:space-between;align-items:flex-start;
    border-bottom:3px solid #1B98E0;padding-bottom:10px;margin-bottom:14px}}
  .brv .t{{font-size:22px;font-weight:700;color:#13293D}}
  .brv .s{{font-size:12px;color:#64748B;margin-top:2px}}
  .brv .g{{font-size:10px;color:#94A3B8;text-align:right}}
  .brv .kpis{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}}
  .brv .k{{flex:1 1 140px;border:1px solid #E2E8F0;border-left:3px solid #1B98E0;
    border-radius:6px;padding:8px 10px}}
  .brv .kl{{font-size:9px;text-transform:uppercase;letter-spacing:.05em;color:#64748B}}
  .brv .kv{{font-size:16px;font-weight:700;margin-top:1px}}
  .brv .ks{{font-size:10px;color:#64748B}}
  .brv h3{{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#1B98E0;
    margin:18px 0 7px;border-bottom:1px solid #E2E8F0;padding-bottom:4px}}
  .brv table{{width:100%;border-collapse:collapse;margin-bottom:4px}}
  .brv th{{background:#F1F5F9;padding:5px 7px;text-align:left;font-size:10px;
    border-bottom:1px solid #E2E8F0}}
  .brv td{{padding:4px 7px;border-bottom:1px solid #F1F5F9;font-size:11px}}
  .brv .r{{text-align:right}} .brv .m{{color:#94A3B8;font-size:11px}}
  .brv ul.cmt{{margin:0;padding-left:18px}} .brv ul.cmt li{{margin-bottom:3px}}
  .brv .risk{{border-left:3px solid #94A3B8;padding:6px 10px;margin-bottom:6px;
    background:#F8FAFC;border-radius:0 5px 5px 0}}
  .brv .risk.high{{border-left-color:#EF4444}} .brv .risk.medium{{border-left-color:#F59E0B}}
  .brv .risk.low{{border-left-color:#60A5FA}}
  .brv .risk div{{font-size:11px;color:#475569}}
  @media print{{ .brv{{max-width:none}} h3{{page-break-after:avoid}} table{{page-break-inside:avoid}} }}
</style>"""


@frappe.whitelist()
def get_html(company=None, from_date=None, to_date=None):
	pack = build(company, from_date, to_date)
	return {"html": render_html(pack), "pack": pack}


# ---------------------------------------------------------------- deliver
@frappe.whitelist()
def download_pdf(company=None, from_date=None, to_date=None):
	from frappe.utils.pdf import get_pdf

	pack = build(company, from_date, to_date)
	html = render_html(pack)
	frappe.local.response.filename = \
		f"Business-Review-{pack['from_date']}-to-{pack['to_date']}.pdf"
	frappe.local.response.filecontent = get_pdf(html, {"orientation": "Portrait"})
	frappe.local.response.type = "pdf"


@frappe.whitelist()
def download_xlsx(company=None, from_date=None, to_date=None):
	"""The underlying tables, for anyone who wants to re-cut them."""
	from frappe.utils.xlsxutils import make_xlsx

	pack = build(company, from_date, to_date)
	h = pack["headline"]

	rows = [
		[_("Business Review"), pack.get("brand") or pack["company"]],
		[_("Period"), f"{pack['from_date']} to {pack['to_date']}"],
		[],
		[_("Headline")],
		[_("Revenue"), flt(h["revenue"])],
		[_("Cost of sales"), flt(h["cogs"])],
		[_("Gross margin"), flt(h["gross"])],
		[_("Gross margin %"), round(flt(h["gross_pct"]), 2)],
		[_("Collections"), flt(h["collections"])],
		[_("Receivables"), flt(h["receivables"])],
		[_("Route expenses"), flt(h["route_expenses"])],
		[_("Cash variance"), flt(h["cash_variance"])],
		[_("Units produced"), flt(h["produced"])],
		[],
		[_("Sales by channel")],
		[_("Channel"), _("Customers"), _("Invoices"), _("Revenue")],
	]
	for c in pack["channels"]:
		rows.append([c.get("channel"), c.get("customers"), c.get("invoices"), flt(c.get("revenue"))])

	rows += [[], [_("Route performance")],
	         [_("Route"), _("Van"), _("Trips"), _("Coverage %"), _("Revenue"), _("Cost"), _("Net")]]
	for r in pack["routes"]:
		rows.append([r["route"], r["van"], r["trips"], round(flt(r["coverage"]), 1),
		             flt(r["revenue"]), flt(r["expenses"]), flt(r["net"])])

	rows += [[], [_("Top products")], [_("Item"), _("Name"), _("Qty"), _("Revenue")]]
	for p in pack["products"]:
		rows.append([p.get("item_code"), p.get("item_name"), flt(p.get("qty")), flt(p.get("revenue"))])

	rows += [[], [_("Production")],
	         [_("Line"), _("Orders"), _("Planned"), _("Produced"), _("Yield %")]]
	for l in pack["production"]["lines"]:
		rows.append([l.get("line"), l.get("orders"), flt(l.get("planned")),
		             flt(l.get("produced")), round(flt(l.get("yield_pct")), 1)])

	rows += [[], [_("Risks")], [_("Severity"), _("Issue"), _("Detail")]]
	for r in pack["risks"]:
		rows.append([r["severity"], r["headline"], r["detail"]])

	xlsx = make_xlsx(rows, "Business Review")
	frappe.local.response.filename = \
		f"Business-Review-{pack['from_date']}-to-{pack['to_date']}.xlsx"
	frappe.local.response.filecontent = xlsx.getvalue()
	frappe.local.response.type = "binary"


@frappe.whitelist()
def send_email(recipients, company=None, from_date=None, to_date=None,
               subject=None, message=None, attach_pdf=1):
	"""Send the pack. The HTML goes in the body so it can be read on a phone
	without opening an attachment; the PDF goes along for filing."""
	if isinstance(recipients, str):
		recipients = [r.strip() for r in recipients.replace(";", ",").split(",") if r.strip()]
	if not recipients:
		frappe.throw(_("Add at least one recipient."))

	pack = build(company, from_date, to_date)
	html = render_html(pack)
	title = subject or _("{0} — Business Review {1} to {2}").format(
		pack.get("brand") or pack["company"], pack["from_date"], pack["to_date"])

	attachments = []
	if int(attach_pdf or 0):
		try:
			from frappe.utils.pdf import get_pdf

			attachments.append({
				"fname": f"Business-Review-{pack['from_date']}.pdf",
				"fcontent": get_pdf(html, {"orientation": "Portrait"}),
			})
		except Exception:
			frappe.log_error(frappe.get_traceback(), "NeoAqua business review: PDF")

	body = (f"<p>{message}</p>" if message else "") + html
	frappe.sendmail(recipients=recipients, subject=title, message=body,
	                attachments=attachments, now=True)

	return {"sent_to": recipients, "subject": title,
	        "attached_pdf": bool(attachments),
	        "message": _("Sent to {0}.").format(", ".join(recipients))}


# ---------------------------------------------------------------- scheduled
def send_monthly_review():
	"""Monthly distribution, if a list is configured in NeoAqua Settings."""
	recipients = frappe.db.get_single_value("NeoAqua Settings", "review_recipients")
	if not recipients:
		return
	companies = frappe.get_all("Company", pluck="name")
	company = frappe.db.get_single_value("NeoAqua Settings", "company") or (
		companies[0] if len(companies) == 1 else None)
	if not company:
		return
	try:
		send_email(recipients, company=company)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "NeoAqua: monthly business review")
