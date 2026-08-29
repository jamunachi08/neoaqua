# Copyright (c) 2026, Neotec Integrated Solutions
"""Dashboard charts, number cards, dashboards and workspaces.

Three role-facing dashboards are created:

    NeoAqua Sales          - van sales, route coverage, collections, containers
    NeoAqua Manufacturing  - line attainment, yield, QC pass rate, scrap
    NeoAqua Finance        - revenue, receivables, cash variance, deposits

Everything is created idempotently so a migrate can re-run it.
"""

import json

import frappe
from frappe import _

# ---------------------------------------------------------------- charts
CHARTS = [
	# name, doctype, chart_type, group_by/value field, type, timespan, filters, dashboard
	{
		"name": "NeoAqua Daily Sales",
		"chart_name": "Daily Sales Value",
		"document_type": "Sales Invoice",
		"chart_type": "Sum",
		"based_on": "posting_date",
		"value_based_on": "base_grand_total",
		"type": "Line",
		"timespan": "Last Month",
		"time_interval": "Daily",
		"filters_json": json.dumps([["Sales Invoice", "docstatus", "=", 1]]),
		"group": "Sales",
	},
	{
		"name": "NeoAqua Sales by Van",
		"chart_name": "Sales by Van",
		"document_type": "Sales Invoice",
		"chart_type": "Group By",
		"group_by_type": "Sum",
		"group_by_based_on": "neoaqua_van",
		"aggregate_function_based_on": "base_grand_total",
		"type": "Bar",
		"filters_json": json.dumps([["Sales Invoice", "docstatus", "=", 1]]),
		"group": "Sales",
	},
	{
		"name": "NeoAqua Sales by Customer Group",
		"chart_name": "Sales by Channel",
		"document_type": "Sales Invoice",
		"chart_type": "Group By",
		"group_by_type": "Sum",
		"group_by_based_on": "customer_group",
		"aggregate_function_based_on": "base_grand_total",
		"type": "Donut",
		"filters_json": json.dumps([["Sales Invoice", "docstatus", "=", 1]]),
		"group": "Sales",
	},
	{
		"name": "NeoAqua Route Coverage",
		"chart_name": "Route Coverage %",
		"document_type": "Van Trip",
		"chart_type": "Average",
		"based_on": "trip_date",
		"value_based_on": "coverage_pct",
		"type": "Line",
		"timespan": "Last Month",
		"time_interval": "Daily",
		"filters_json": json.dumps([["Van Trip", "docstatus", "=", 1]]),
		"group": "Sales",
	},
	{
		"name": "NeoAqua Visit Outcomes",
		"chart_name": "Visit Outcomes",
		"document_type": "Salesman Check In",
		"chart_type": "Group By",
		"group_by_type": "Count",
		"group_by_based_on": "visit_status",
		"type": "Donut",
		"filters_json": json.dumps([["Salesman Check In", "docstatus", "=", 1]]),
		"group": "Sales",
	},
	{
		"name": "NeoAqua Production by Line",
		"chart_name": "Production by Line",
		"document_type": "Work Order",
		"chart_type": "Group By",
		"group_by_type": "Sum",
		"group_by_based_on": "neoaqua_production_line",
		"aggregate_function_based_on": "produced_qty",
		"type": "Bar",
		"filters_json": json.dumps([["Work Order", "docstatus", "=", 1]]),
		"group": "Manufacturing",
	},
	{
		"name": "NeoAqua Daily Output",
		"chart_name": "Daily Finished Goods Output",
		"document_type": "Work Order",
		"chart_type": "Sum",
		"based_on": "actual_end_date",
		"value_based_on": "produced_qty",
		"type": "Bar",
		"timespan": "Last Month",
		"time_interval": "Daily",
		"filters_json": json.dumps([["Work Order", "docstatus", "=", 1]]),
		"group": "Manufacturing",
	},
	{
		"name": "NeoAqua QC Results",
		"chart_name": "Quality Check Results",
		"document_type": "Water Quality Check",
		"chart_type": "Group By",
		"group_by_type": "Count",
		"group_by_based_on": "overall_result",
		"type": "Donut",
		"filters_json": json.dumps([["Water Quality Check", "docstatus", "=", 1]]),
		"group": "Manufacturing",
	},
	{
		"name": "NeoAqua Monthly Revenue",
		"chart_name": "Monthly Revenue",
		"document_type": "Sales Invoice",
		"chart_type": "Sum",
		"based_on": "posting_date",
		"value_based_on": "base_net_total",
		"type": "Bar",
		"timespan": "Last Year",
		"time_interval": "Monthly",
		"filters_json": json.dumps([["Sales Invoice", "docstatus", "=", 1]]),
		"group": "Finance",
	},
	{
		"name": "NeoAqua Cash Variance Trend",
		"chart_name": "Cash Variance Trend",
		"document_type": "Salesman Day Close",
		"chart_type": "Sum",
		"based_on": "posting_date",
		"value_based_on": "cash_variance",
		"type": "Line",
		"timespan": "Last Quarter",
		"time_interval": "Daily",
		"filters_json": json.dumps([["Salesman Day Close", "docstatus", "=", 1]]),
		"group": "Finance",
	},
	{
		"name": "NeoAqua Purchase by Supplier",
		"chart_name": "Purchases by Supplier",
		"document_type": "Purchase Invoice",
		"chart_type": "Group By",
		"group_by_type": "Sum",
		"group_by_based_on": "supplier",
		"aggregate_function_based_on": "base_grand_total",
		"type": "Bar",
		"filters_json": json.dumps([["Purchase Invoice", "docstatus", "=", 1]]),
		"group": "Finance",
	},
]

# ---------------------------------------------------------------- number cards
CARDS = [
	("NeoAqua Sales Today", "Sales Invoice", "Sum", "base_grand_total",
	 [["Sales Invoice", "docstatus", "=", 1], ["Sales Invoice", "posting_date", "Timespan", "today"]], "Sales"),
	("NeoAqua Open Van Trips", "Van Trip", "Count", None,
	 [["Van Trip", "docstatus", "=", 1], ["Van Trip", "status", "in", ["Loaded", "In Progress"]]], "Sales"),
	("NeoAqua Pending Day Close", "Van Trip", "Count", None,
	 [["Van Trip", "docstatus", "=", 1], ["Van Trip", "status", "=", "Returned"]], "Sales"),
	("NeoAqua Visits Today", "Salesman Check In", "Count", None,
	 [["Salesman Check In", "docstatus", "=", 1], ["Salesman Check In", "checkin_datetime", "Timespan", "today"]], "Sales"),
	("NeoAqua Off-Fence Visits", "Salesman Check In", "Count", None,
	 [["Salesman Check In", "docstatus", "=", 1], ["Salesman Check In", "within_geofence", "=", 0]], "Sales"),
	("NeoAqua Containers with Customers", "Container Ledger Entry", "Sum", "qty",
	 [["Container Ledger Entry", "docstatus", "=", 1], ["Container Ledger Entry", "entry_type", "=", "Issue (Full Out)"]], "Sales"),
	("NeoAqua Open Work Orders", "Work Order", "Count", None,
	 [["Work Order", "docstatus", "=", 1], ["Work Order", "status", "in", ["Not Started", "In Process"]]], "Manufacturing"),
	("NeoAqua Produced This Month", "Work Order", "Sum", "produced_qty",
	 [["Work Order", "docstatus", "=", 1], ["Work Order", "actual_end_date", "Timespan", "this month"]], "Manufacturing"),
	("NeoAqua Failed QC", "Water Quality Check", "Count", None,
	 [["Water Quality Check", "docstatus", "=", 1], ["Water Quality Check", "overall_result", "=", "Fail"]], "Manufacturing"),
	("NeoAqua Open Material Requests", "Material Request", "Count", None,
	 [["Material Request", "docstatus", "=", 1], ["Material Request", "status", "in", ["Pending", "Partially Ordered"]]], "Manufacturing"),
	("NeoAqua Revenue MTD", "Sales Invoice", "Sum", "base_net_total",
	 [["Sales Invoice", "docstatus", "=", 1], ["Sales Invoice", "posting_date", "Timespan", "this month"]], "Finance"),
	("NeoAqua Receivables", "Sales Invoice", "Sum", "outstanding_amount",
	 [["Sales Invoice", "docstatus", "=", 1], ["Sales Invoice", "status", "!=", "Paid"]], "Finance"),
	("NeoAqua Cash Variance MTD", "Salesman Day Close", "Sum", "cash_variance",
	 [["Salesman Day Close", "docstatus", "=", 1], ["Salesman Day Close", "posting_date", "Timespan", "this month"]], "Finance"),
	("NeoAqua Purchase Orders to Receive", "Purchase Order", "Count", None,
	 [["Purchase Order", "docstatus", "=", 1], ["Purchase Order", "status", "in", ["To Receive and Bill", "To Receive"]]], "Finance"),
]

DASHBOARDS = {
	"NeoAqua Sales": "Sales",
	"NeoAqua Manufacturing": "Manufacturing",
	"NeoAqua Finance": "Finance",
}


# ---------------------------------------------------------------- builders
# Dashboard Chart autonames from `chart_name`, Number Card from `label`.
# Assigning doc.name before insert() is silently discarded, so the intended
# name must BE the naming field - and the dashboard must then link to whatever
# name the insert actually produced, not what we assumed it would be.


def _existing(doctype, field, *candidates):
	"""Find a record by its naming field, tolerating names left behind by an
	earlier build that used a different label."""
	for value in candidates:
		if not value:
			continue
		if frappe.db.exists(doctype, value):
			return value
		found = frappe.db.get_value(doctype, {field: value}, "name")
		if found:
			return found
	return None


def create_charts():
	"""Returns {intended_name: actual_name} for the dashboard builder."""
	created = {}
	for spec in CHARTS:
		name = spec["name"]
		short = spec["chart_name"]

		found = _existing("Dashboard Chart", "chart_name", name, short)
		if found:
			created[name] = found
			continue

		doc = frappe.new_doc("Dashboard Chart")
		payload = {k: v for k, v in spec.items() if k not in ("name", "group")}
		doc.update(payload)
		# the naming field carries the unique name; `short` becomes the subtitle
		doc.chart_name = name
		doc.module = "NeoAqua"
		doc.is_public = 1
		doc.timeseries = 1 if spec.get("based_on") else 0
		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		try:
			doc.insert()
			created[name] = doc.name
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"NeoAqua: could not create chart {name}")
	return created


def create_number_cards():
	"""Returns {intended_name: actual_name}."""
	created = {}
	for name, doctype, func, field, filters, group in CARDS:
		short = name.replace("NeoAqua ", "")
		found = _existing("Number Card", "label", name, short)
		if found:
			created[name] = found
			continue

		doc = frappe.new_doc("Number Card")
		doc.update(
			{
				"label": name,
				"document_type": doctype,
				"function": func,
				"aggregate_function_based_on": field,
				"filters_json": json.dumps(filters),
				"is_public": 1,
				"module": "NeoAqua",
				"show_percentage_stats": 1,
				"stats_time_interval": "Daily",
			}
		)
		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		try:
			doc.insert()
			created[name] = doc.name
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"NeoAqua: could not create number card {name}")
	return created


def create_dashboards(chart_map=None, card_map=None):
	chart_map = chart_map or {}
	card_map = card_map or {}

	for dash, group in DASHBOARDS.items():
		if frappe.db.exists("Dashboard", dash):
			continue

		doc = frappe.new_doc("Dashboard")
		doc.dashboard_name = dash
		doc.module = "NeoAqua"
		doc.is_default = 1 if group == "Sales" else 0

		for spec in CHARTS:
			if spec["group"] != group:
				continue
			actual = chart_map.get(spec["name"]) or _existing(
				"Dashboard Chart", "chart_name", spec["name"], spec["chart_name"]
			)
			if actual:
				doc.append("charts", {"chart": actual, "width": "Half"})

		for card in CARDS:
			name, card_group = card[0], card[5]
			if card_group != group:
				continue
			actual = card_map.get(name) or _existing(
				"Number Card", "label", name, name.replace("NeoAqua ", "")
			)
			if actual:
				doc.append("cards", {"card": actual})

		if not doc.charts and not doc.cards:
			continue

		doc.flags.ignore_permissions = True
		try:
			doc.insert()
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"NeoAqua: could not create dashboard {dash}")


# ---------------------------------------------------------------- workspaces
def _block(kind, data):
	"""Frappe renders a workspace from its `content` JSON. A link or shortcut
	that exists only as a child row is invisible - it must also appear as a
	block here, which is why the first build showed one shortcut and nothing
	else."""
	import secrets

	return {"id": secrets.token_hex(5), "type": kind, "data": data}


def _ws_content(blocks):
	return json.dumps(blocks)


WORKSPACES = [
	{
		"name": "Water Sales & Distribution",
		"icon": "sell",
		"dashboard": "NeoAqua Sales",
		"shortcuts": [
			("neoaqua-hub", "Page", "NeoAqua Hub"),
			("neoaqua-control-tower", "Page", "Control Tower"),
			("Van Trip", "DocType"), ("Van Load Request", "DocType"),
			("Salesman Day Close", "DocType"), ("Salesman Check In", "DocType"),
			("Sales Invoice", "DocType"),
		],
		"links": [
			("Daily Operations", [
				("neoaqua-hub", "Page", "NeoAqua Hub"),
			("neoaqua-control-tower", "Page", "Control Tower"),
				"Van Trip", "Van Load Request", "Salesman Check In", "Salesman Day Close",
			]),
			("Van Sales", ["Van", "Van Route", "Van Trip", "Van Load Request"]),
			("Field Force", ["Salesman Check In", "Geofence Zone", "Sales Person"]),
			("Settlement", ["Salesman Day Close", "Payment Entry", "Container Ledger Entry"]),
			("Selling", ["Customer", "Sales Order", "Sales Invoice", "POS Profile", "Item Price"]),
			("Reports", [
				("Sales Register Van and Channel", "Report"),
				("Item wise Sales and Margin", "Report"),
				("Customer Sales Trend", "Report"),
				("Salesman Performance Scorecard", "Report"),
				("Van Sales Summary", "Report"),
				("Route Visit Compliance", "Report"),
				("Customer Container Balance", "Report"),
			]),
		],
	},
	{
		"name": "Water Manufacturing",
		"icon": "setting-gear",
		"dashboard": "NeoAqua Manufacturing",
		"shortcuts": [
			("neoaqua-hub", "Page", "NeoAqua Hub"),
			("neoaqua-control-tower", "Page", "Control Tower"),
			("Work Order", "DocType"), ("BOM", "DocType"), ("Job Card", "DocType"),
			("Material Request", "DocType"), ("Stock Entry", "DocType"),
			("Water Quality Check", "DocType"), ("NeoAqua Settings", "DocType", "NeoAqua Setup"),
			("batch-code-builder", "Page", "Batch Code Builder"),
		],
		"links": [
			("Planning", [
				("neoaqua-production-planner", "Page", "Production Planner"),
				"Production Plan", "Material Request",
			]),
			("Production", ["Production Plan", "Work Order", "Job Card", "Stock Entry"]),
			("Bill of Materials", ["BOM", "Routing", "Operation", "Workstation", "BOM Update Tool"]),
			("Batch Numbering", [
				("batch-code-builder", "Page", "Batch Code Builder"),
				"Batch Naming Rule",
				"Batch Sequence Counter",
			]),
			("Quality", ["Water Quality Check", "Batch", "Quality Inspection"]),
			("Setup", ["NeoAqua Settings", "NeoAqua Demo Tool"]),
			("Stock", ["Item", "Warehouse", "Stock Entry", "Stock Reconciliation", "Bin"]),
			("Reports", [
				("Production Yield and Scrap", "Report"),
				("BOM Explorer", "Report"),
				("Batch QC Register", "Report"),
			]),
		],
	},
	{
		"name": "Water Finance",
		"icon": "accounting",
		"dashboard": "NeoAqua Finance",
		"shortcuts": [
			("neoaqua-hub", "Page", "NeoAqua Hub"),
			("neoaqua-control-tower", "Page", "Control Tower"),
			("Sales Invoice", "DocType"), ("Purchase Invoice", "DocType"),
			("Payment Entry", "DocType"), ("Journal Entry", "DocType"),
			("Accounts Receivable", "Report"),
		],
		"links": [
			("Procure to Pay", [
				"Material Request", "Request for Quotation", "Supplier Quotation",
				"Purchase Order", "Purchase Receipt", "Purchase Invoice", "Payment Entry",
			]),
			("Order to Cash", ["Sales Order", "Delivery Note", "Sales Invoice", "Payment Entry"]),
			("Accounting", ["Journal Entry", "Account", "Cost Center", "Fiscal Year"]),
			("Management", [
				("neoaqua-business-review", "Page", "Business Review"),
				("Route and Van Profitability", "Report"),
				("Customer Profitability and Cost to Serve", "Report"),
				("Product Contribution and Pareto", "Report"),
				("Working Capital and Cash Cycle", "Report"),
			]),
			("Reports", [
				("Daily Cash and Sales Summary", "Report"),
				("Receivables Aging by Route", "Report"),
				("VAT Summary KSA", "Report"),
				("Salesman Day Close Variance", "Report"),
				("Accounts Receivable", "Report"),
				("Accounts Payable", "Report"),
			]),
		],
	},
]


def _link_exists(link_to, link_type):
	"""Workspace Link and Workspace Shortcut both store `link_to` as a Dynamic
	Link, so a target that does not exist aborts the whole workspace insert.
	Skipping a missing link costs one menu entry; letting it through costs the
	install."""
	try:
		return bool(frappe.db.exists(link_type, link_to))
	except Exception:
		return False


def _unpack(entry):
	"""Accept 'Name', ('Name', 'Type') or ('name', 'Type', 'Label')."""
	if isinstance(entry, tuple):
		if len(entry) == 3:
			return entry[0], entry[1], entry[2]
		return entry[0], entry[1], entry[0]
	return entry, "DocType", entry


def _build_blocks(title, shortcuts, cards):
	"""Header, then every shortcut, then every link card - so the workspace
	actually shows what was attached to it."""
	blocks = [
		_block("header", {"text": f"<span class='h4'><b>{title}</b></span>", "col": 12})
	]
	if shortcuts:
		blocks.append(_block("header", {"text": f"<span class='h5'>{_('Jump to')}</span>", "col": 12}))
		for name in shortcuts:
			blocks.append(_block("shortcut", {"shortcut_name": name, "col": 3}))
		blocks.append(_block("spacer", {"col": 12}))
	for card in cards:
		blocks.append(_block("card", {"card_name": card, "col": 4}))
	return blocks


def _content_is_broken(name):
	"""An earlier build wrote a header and one shortcut and nothing else.
	Detect that specific shape rather than trampling a workspace someone has
	deliberately customised."""
	try:
		content = json.loads(frappe.db.get_value("Workspace", name, "content") or "[]")
	except Exception:
		return True
	return len([b for b in content if b.get("type") in ("card", "shortcut")]) <= 1


def create_workspaces():
	for ws in WORKSPACES:
		existing = frappe.db.exists("Workspace", ws["name"])
		if existing and not _content_is_broken(ws["name"]):
			continue
		if existing:
			# repair in place: keep the record, rebuild what it shows
			frappe.delete_doc("Workspace", ws["name"], force=True, ignore_permissions=True)

		doc = frappe.new_doc("Workspace")
		# Workspace autonames from `title` - assigning doc.name here would be
		# discarded, so title is the only thing that decides the record name.
		doc.title = ws["name"]
		doc.label = ws["name"]
		doc.module = "NeoAqua"
		doc.icon = ws["icon"]
		doc.public = 1
		doc.is_hidden = 0

		shortcuts, cards = [], []
		for entry in ws["shortcuts"]:
			link_to, ltype, label = _unpack(entry)
			if not _link_exists(link_to, ltype):
				continue
			doc.append("shortcuts", {"label": label, "link_to": link_to, "type": ltype})
			shortcuts.append(label)

		for group, entries in ws["links"]:
			valid = []
			for entry in entries:
				link_to, ltype, label = _unpack(entry)
				if _link_exists(link_to, ltype):
					valid.append((link_to, ltype, label))
			if not valid:
				continue
			doc.append("links", {"label": group, "type": "Card Break", "link_count": len(valid)})
			cards.append(group)
			for link_to, ltype, label in valid:
				doc.append(
					"links",
					{
						"label": label,
						"link_to": link_to,
						"link_type": ltype,
						"type": "Link",
						"is_query_report": 1 if ltype == "Report" else 0,
						"onboard": 0,
					},
				)

		doc.content = _ws_content(_build_blocks(ws["name"], shortcuts, cards))

		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		try:
			doc.insert()
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"NeoAqua: could not create workspace {ws['name']}")


def run():
	"""Build charts, cards, dashboards and workspaces.

	Each stage is isolated: a cosmetic artifact that cannot be built is logged
	and skipped rather than aborting the caller. Nothing here is load-bearing
	for transactions, and an install must never fail because a chart could not
	be drawn."""
	chart_map, card_map = {}, {}
	try:
		chart_map = create_charts()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "NeoAqua: chart creation failed")
	try:
		card_map = create_number_cards()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "NeoAqua: number card creation failed")
	try:
		create_dashboards(chart_map, card_map)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "NeoAqua: dashboard creation failed")
	try:
		create_workspaces()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "NeoAqua: workspace creation failed")
	frappe.db.commit()
	return {
		"charts": len(chart_map),
		"cards": len(card_map),
		"dashboards": frappe.db.count("Dashboard", {"module": "NeoAqua"}),
		"workspaces": frappe.db.count("Workspace", {"module": "NeoAqua"}),
	}
