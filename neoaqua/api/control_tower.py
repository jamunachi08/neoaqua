# Copyright (c) 2026, Neotec Integrated Solutions
"""Control Tower data service.

One whitelisted call returns the whole operational picture, because a cockpit
that fires fifteen requests to draw itself is a cockpit nobody leaves open.

Every panel is computed in its own guarded block. A panel that cannot be built
returns empty and names its error rather than taking the page down with it -
the same principle applied to the setup stages, for the same reason.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate

PANELS = {}


def panel(name):
	"""Register a panel builder and isolate its failures."""

	def wrap(fn):
		PANELS[name] = fn
		return fn

	return wrap


def _company(company=None):
	return company or frappe.defaults.get_user_default("company") or frappe.defaults.get_global_default("company")


# ================================================================== pipeline
@panel("pipeline")
def build_pipeline(company, date):
	"""The four process stages, each with the counts that matter and a route
	to click through to."""
	stages = []

	# ---- procure to pay
	stages.append(
		{
			"key": "procure",
			"label": _("Procure to Pay"),
			"icon": "&#128230;",
			"steps": [
				{
					"label": _("Open material requests"),
					"count": frappe.db.count(
						"Material Request",
						{"docstatus": 1, "status": ["in", ["Pending", "Partially Ordered"]], "company": company},
					),
					"route": ["List", "Material Request", {"status": ["in", ["Pending", "Partially Ordered"]]}],
				},
				{
					"label": _("Orders to receive"),
					"count": frappe.db.count(
						"Purchase Order",
						{"docstatus": 1, "status": ["in", ["To Receive and Bill", "To Receive"]], "company": company},
					),
					"route": ["List", "Purchase Order", {"status": ["in", ["To Receive and Bill", "To Receive"]]}],
				},
				{
					"label": _("Invoices to pay"),
					"count": frappe.db.count(
						"Purchase Invoice",
						{"docstatus": 1, "outstanding_amount": [">", 0], "company": company},
					),
					"route": ["List", "Purchase Invoice", {"status": "Unpaid"}],
				},
			],
		}
	)

	# ---- production
	pending_qc = frappe.db.count("Batch", {"neoaqua_qc_status": ["in", ["Pending", ""]]})
	stages.append(
		{
			"key": "produce",
			"label": _("Plan to Produce"),
			"icon": "&#127974;",
			"steps": [
				{
					"label": _("Work orders in process"),
					"count": frappe.db.count(
						"Work Order",
						{"docstatus": 1, "status": ["in", ["Not Started", "In Process"]], "company": company},
					),
					"route": ["List", "Work Order", {"status": ["in", ["Not Started", "In Process"]]}],
				},
				{
					"label": _("Batches awaiting QC"),
					"count": pending_qc,
					"route": ["List", "Batch", {"neoaqua_qc_status": "Pending"}],
				},
				{
					"label": _("Produced today"),
					"count": _produced_today(company, date),
					"route": ["List", "Work Order", {"status": "Completed"}],
					"is_qty": True,
				},
			],
		}
	)

	# ---- distribution
	stages.append(
		{
			"key": "distribute",
			"label": _("Load to Deliver"),
			"icon": "&#128666;",
			"steps": [
				{
					"label": _("Vans on the road"),
					"count": frappe.db.count(
						"Van Trip", {"docstatus": 1, "status": ["in", ["Loaded", "In Progress"]]}
					),
					"route": ["List", "Van Trip", {"status": ["in", ["Loaded", "In Progress"]]}],
				},
				{
					"label": _("Visits logged today"),
					"count": frappe.db.count(
						"Salesman Check In",
						{"docstatus": 1, "checkin_datetime": ["between", [f"{date} 00:00:00", f"{date} 23:59:59"]]},
					),
					"route": ["List", "Salesman Check In", {}],
				},
				{
					"label": _("Invoices today"),
					"count": frappe.db.count(
						"Sales Invoice", {"docstatus": 1, "posting_date": date, "company": company}
					),
					"route": ["List", "Sales Invoice", {"posting_date": date}],
				},
			],
		}
	)

	# ---- settlement
	stages.append(
		{
			"key": "settle",
			"label": _("Settle and Collect"),
			"icon": "&#128176;",
			"steps": [
				{
					"label": _("Trips awaiting day close"),
					"count": frappe.db.count("Van Trip", {"docstatus": 1, "status": "Returned"}),
					"route": ["List", "Van Trip", {"status": "Returned"}],
				},
				{
					"label": _("Day closes pending approval"),
					"count": frappe.db.count(
						"Salesman Day Close", {"docstatus": 0, "status": "Pending Approval"}
					),
					"route": ["List", "Salesman Day Close", {"status": "Pending Approval"}],
				},
				{
					"label": _("Customers owing"),
					"count": frappe.db.sql(
						"""select count(distinct customer) from `tabSales Invoice`
						   where docstatus = 1 and outstanding_amount > 0 and company = %s""",
						company,
					)[0][0],
					"route": ["query-report", "Accounts Receivable"],
				},
			],
		}
	)

	return stages


def _produced_today(company, date):
	return flt(
		frappe.db.sql(
			"""select sum(sed.qty)
			   from `tabStock Entry Detail` sed
			   join `tabStock Entry` se on se.name = sed.parent
			   where se.docstatus = 1 and se.purpose = 'Manufacture'
			     and se.posting_date = %s and se.company = %s
			     and sed.is_finished_item = 1""",
			(date, company),
		)[0][0]
	)


# ================================================================== kpis
@panel("kpis")
def build_kpis(company, date):
	month_start = getdate(date).replace(day=1)

	sales_today = flt(
		frappe.db.sql(
			"""select sum(base_grand_total) from `tabSales Invoice`
			   where docstatus = 1 and posting_date = %s and company = %s and is_return = 0""",
			(date, company),
		)[0][0]
	)
	collections_today = flt(
		frappe.db.sql(
			"""select sum(base_paid_amount) from `tabPayment Entry`
			   where docstatus = 1 and posting_date = %s and company = %s
			     and payment_type = 'Receive'""",
			(date, company),
		)[0][0]
	)
	receivables = flt(
		frappe.db.sql(
			"""select sum(outstanding_amount) from `tabSales Invoice`
			   where docstatus = 1 and company = %s""",
			company,
		)[0][0]
	)
	variance_mtd = flt(
		frappe.db.sql(
			"""select sum(cash_variance) from `tabSalesman Day Close`
			   where docstatus = 1 and posting_date between %s and %s and company = %s""",
			(month_start, date, company),
		)[0][0]
	)

	qc = frappe.db.sql(
		"""select overall_result, count(*) as n from `tabWater Quality Check`
		   where docstatus = 1 and posting_date >= %s group by overall_result""",
		add_days(date, -7),
		as_dict=True,
	)
	total_qc = sum(r.n for r in qc) or 0
	passed = sum(r.n for r in qc if r.overall_result in ("Pass", "Conditional Release"))
	pass_rate = (passed / total_qc * 100) if total_qc else None

	containers = flt(
		frappe.db.sql(
			"""select
			     sum(case when entry_type in ('Issue (Full Out)','Opening Balance','Lost / Damaged')
			              then qty else 0 end)
			   - sum(case when entry_type = 'Return (Empty In)' then qty else 0 end)
			   from `tabContainer Ledger Entry` where docstatus = 1""",
		)[0][0]
	)

	fg_value = flt(
		frappe.db.sql(
			"""select sum(b.stock_value) from `tabBin` b
			   join `tabItem` i on i.name = b.item_code
			   where i.item_code like 'FG-%%'""",
		)[0][0]
	)

	van_stock_value = flt(
		frappe.db.sql(
			"""select sum(b.stock_value) from `tabBin` b
			   join `tabVan` v on v.warehouse = b.warehouse""",
		)[0][0]
	)

	return [
		{"key": "sales_today", "label": _("Sales today"), "value": sales_today, "fmt": "currency"},
		{"key": "collections_today", "label": _("Collected today"), "value": collections_today, "fmt": "currency"},
		{"key": "receivables", "label": _("Receivables"), "value": receivables, "fmt": "currency",
		 "tone": "warn" if receivables > 0 else None},
		{"key": "variance_mtd", "label": _("Cash variance MTD"), "value": variance_mtd, "fmt": "currency",
		 "tone": "bad" if variance_mtd < 0 else ("good" if variance_mtd == 0 else "info")},
		{"key": "qc_pass", "label": _("QC pass rate (7d)"), "value": pass_rate, "fmt": "percent",
		 "tone": "bad" if (pass_rate is not None and pass_rate < 95) else "good"},
		{"key": "containers", "label": _("Containers in market"), "value": containers, "fmt": "number"},
		{"key": "fg_value", "label": _("Finished goods value"), "value": fg_value, "fmt": "currency"},
		{"key": "van_stock", "label": _("Stock on vans"), "value": van_stock_value, "fmt": "currency"},
	]


# ================================================================== vans
@panel("vans")
def build_vans(company, date):
	"""Live board: one row per van, showing where the day stands."""
	rows = []
	for van in frappe.get_all(
		"Van",
		filters={"status": "Active"},
		fields=["name", "van_name", "salesman", "warehouse", "plate_number"],
		order_by="van_name",
	):
		trip = frappe.db.get_value(
			"Van Trip",
			{"van": van.name, "docstatus": 1, "trip_date": date},
			["name", "status", "coverage_pct", "planned_stops", "visited_stops",
			 "total_invoiced", "total_collected", "day_close"],
			as_dict=True,
			order_by="creation desc",
		)
		stock_value = flt(
			frappe.db.get_value("Bin", {"warehouse": van.warehouse}, "sum(stock_value)") or 0
		) if van.warehouse else 0

		state = "idle"
		if trip:
			state = {
				"Loaded": "loaded",
				"In Progress": "running",
				"Returned": "awaiting_close",
				"Closed": "closed",
			}.get(trip.status, "idle")

		rows.append(
			{
				"van": van.name,
				"plate": van.plate_number,
				"salesman": van.salesman,
				"state": state,
				"trip": trip.name if trip else None,
				"status": trip.status if trip else _("No trip today"),
				"coverage": flt(trip.coverage_pct) if trip else 0,
				"visited": trip.visited_stops if trip else 0,
				"planned": trip.planned_stops if trip else 0,
				"invoiced": flt(trip.total_invoiced) if trip else 0,
				"collected": flt(trip.total_collected) if trip else 0,
				"day_close": trip.day_close if trip else None,
				"stock_value": stock_value,
			}
		)
	return rows


# ================================================================== lines
@panel("lines")
def build_lines(company, date):
	rows = frappe.db.sql(
		"""select neoaqua_production_line as line,
		          sum(qty) as planned, sum(produced_qty) as produced,
		          count(*) as orders
		   from `tabWork Order`
		   where docstatus = 1 and company = %s
		     and creation >= %s and neoaqua_production_line is not null
		   group by neoaqua_production_line""",
		(company, add_days(date, -7)),
		as_dict=True,
	)
	for r in rows:
		r["attainment"] = (flt(r.produced) / flt(r.planned) * 100) if flt(r.planned) else 0
	return rows


# ================================================================== exceptions
@panel("exceptions")
def build_exceptions(company, date):
	"""Things that need a human. Ordered by how much they cost if ignored."""
	out = []

	def add(severity, label, count, route, hint=None):
		if count:
			out.append(
				{"severity": severity, "label": label, "count": count, "route": route, "hint": hint}
			)

	add(
		"high",
		_("Failed quality checks"),
		frappe.db.count("Water Quality Check", {"docstatus": 1, "overall_result": "Fail"}),
		["List", "Water Quality Check", {"overall_result": "Fail"}],
		_("Batches are blocked from release."),
	)
	add(
		"high",
		_("Trips returned without a day close"),
		frappe.db.count("Van Trip", {"docstatus": 1, "status": "Returned"}),
		["List", "Van Trip", {"status": "Returned"}],
		_("Cash is unreconciled until these settle."),
	)
	add(
		"medium",
		_("Check-ins outside the geofence"),
		frappe.db.count(
			"Salesman Check In",
			{"docstatus": 1, "within_geofence": 0,
			 "checkin_datetime": ["between", [f"{add_days(date, -7)} 00:00:00", f"{date} 23:59:59"]]},
		),
		["List", "Salesman Check In", {"within_geofence": 0}],
		_("Last seven days."),
	)
	add(
		"medium",
		_("Day closes with a cash variance"),
		frappe.db.count("Salesman Day Close", {"docstatus": 0, "status": "Pending Approval"}),
		["List", "Salesman Day Close", {"status": "Pending Approval"}],
	)

	near_expiry = flt(
		frappe.db.sql(
			"""select count(distinct b.name) from `tabBatch` b
			   where b.expiry_date between %s and %s""",
			(date, add_days(date, 60)),
		)[0][0]
	)
	add(
		"medium",
		_("Batches expiring within 60 days"),
		int(near_expiry),
		["List", "Batch", {}],
	)

	add(
		"low",
		_("Suppliers with an expired CR"),
		frappe.db.count("Supplier", {"neoaqua_cr_expiry": ["<", date]}),
		["List", "Supplier", {}],
		_("Purchase orders for food-contact material are blocked."),
	)

	return out


# ================================================================== trend
@panel("trend")
def build_trend(company, date):
	rows = frappe.db.sql(
		"""select posting_date, sum(base_grand_total) as total
		   from `tabSales Invoice`
		   where docstatus = 1 and company = %s
		     and posting_date between %s and %s and is_return = 0
		   group by posting_date order by posting_date""",
		(company, add_days(date, -13), date),
		as_dict=True,
	)
	by_date = {str(r.posting_date): flt(r.total) for r in rows}
	series = []
	for i in range(13, -1, -1):
		d = str(add_days(date, -i))
		series.append({"date": d, "value": by_date.get(d, 0)})
	return series


# ================================================================== entry
@frappe.whitelist()
def get_overview(company=None, date=None):
	company = _company(company)
	date = str(getdate(date or nowdate()))

	if not company:
		return {"error": _("No company found. Create one, then reload.")}

	result = {"company": company, "date": date, "panels": {}, "errors": {}}

	for name, fn in PANELS.items():
		try:
			result["panels"][name] = fn(company, date)
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), f"NeoAqua Control Tower: {name}")
			result["panels"][name] = []
			result["errors"][name] = str(e)[:200]

	try:
		from neoaqua.setup import orchestrator

		state = orchestrator.status(company)
		result["setup_complete"] = state.get("complete")
		result["setup_missing"] = [c["check"] for c in state.get("checks", []) if not c["ok"]]
	except Exception:
		result["setup_complete"] = True
		result["setup_missing"] = []

	return result


@frappe.whitelist()
def get_companies():
	return frappe.get_all("Company", pluck="name")
