# Copyright (c) 2026, Neotec Integrated Solutions
"""NeoAqua Hub — the single entry point.

Two principles hold this together:

1. **Access is decided on the server.** Every node, tile and action is tested
   with `frappe.has_permission` before it is sent. A user who cannot read Van
   Trip never receives the Van Trip node - not a greyed-out one, not a hidden
   one. Filtering in the browser is decoration, not a permission model, and a
   count is itself information: telling a salesman there are 14 unpaid purchase
   invoices leaks something he has no right to.

2. **The page adapts to the person.** A van salesman opening the hub wants
   today's route; a plant operator wants the lines; an accountant wants what is
   unposted. The same page reorders itself around whoever is looking, rather
   than showing everyone the union of everything.
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate

# ---------------------------------------------------------------- personas
PERSONAS = [
	# key, label, roles that imply it, the lane it opens on
	("manager", _("Operations"), ["NeoAqua Manager", "System Manager"], "overview"),
	("field", _("Field Sales"), ["Van Salesman", "Van Supervisor"], "distribute"),
	("plant", _("Plant"), ["Plant Operator", "Manufacturing User"], "produce"),
	("quality", _("Quality"), ["QC Inspector", "Quality Manager"], "produce"),
	("finance", _("Finance"), ["Accounts Manager", "Accounts User", "Cashier - Water"], "settle"),
	("buying", _("Procurement"), ["Purchase Manager", "Purchase User"], "procure"),
]


def _roles():
	return set(frappe.get_roles())


def detect_persona():
	roles = _roles()
	for key, label, needed, lane in PERSONAS:
		if roles & set(needed):
			return {"key": key, "label": label, "lane": lane}
	return {"key": "guest", "label": _("General"), "lane": "overview"}


def can(doctype, ptype="read"):
	"""One place to ask the permission question, so no caller forgets to."""
	try:
		return bool(frappe.has_permission(doctype, ptype))
	except Exception:
		return False


def can_page(page_name):
	"""A Page carries its own role list. An empty list means public; otherwise
	the user needs one of those roles. Without this check a Page link slips
	past the tile filter, which is how a user with no permissions was still
	being offered the Batch Code Builder.
	"""
	if not frappe.db.exists("Page", page_name):
		return False
	roles = frappe.get_all("Has Role", filters={"parent": page_name, "parenttype": "Page"}, pluck="role")
	if not roles:
		return True
	return bool(set(roles) & _roles())


def can_report(report_name):
	"""Permission on a report follows the doctype it reports on, not the Report
	doctype itself - `can("Report")` only says whether the user may edit report
	definitions, which is a different question entirely."""
	if not frappe.db.exists("Report", report_name):
		return False
	ref = frappe.db.get_value("Report", report_name, "ref_doctype")
	if ref and not can(ref):
		return False
	roles = frappe.get_all("Has Role", filters={"parent": report_name, "parenttype": "Report"}, pluck="role")
	if roles and not (set(roles) & _roles()):
		return False
	return True


def _count(doctype, filters):
	if not can(doctype):
		return None
	try:
		return frappe.db.count(doctype, filters)
	except Exception:
		return None


# ---------------------------------------------------------------- the map
def _lane(key, label, colour, icon, nodes):
	visible = [n for n in nodes if n is not None]
	if not visible:
		return None
	return {"key": key, "label": label, "colour": colour, "icon": icon, "nodes": visible}


def _node(label, doctype, filters=None, route=None, ptype="read", hint=None):
	"""Return None when the user may not see this doctype, so the node simply
	does not exist as far as the client is concerned."""
	if not can(doctype, ptype):
		return None
	count = _count(doctype, filters) if filters is not None else None
	return {
		"label": label,
		"doctype": doctype,
		"count": count,
		"route": route or ["List", doctype, filters or {}],
		"hint": hint,
	}


def build_map(company):
	lanes = []

	lanes.append(
		_lane(
			"procure", _("Procure"), "#8B5CF6", "&#128230;",
			[
				_node(_("Material Requests"), "Material Request",
				      {"docstatus": 1, "status": ["in", ["Pending", "Partially Ordered"]]},
				      hint=_("What the plant has asked for")),
				_node(_("Purchase Orders"), "Purchase Order",
				      {"docstatus": 1, "status": ["in", ["To Receive and Bill", "To Receive"]]},
				      hint=_("Placed, not yet arrived")),
				_node(_("Receipts"), "Purchase Receipt", {"docstatus": 1, "status": "To Bill"},
				      hint=_("Arrived, not yet invoiced")),
				_node(_("Purchase Invoices"), "Purchase Invoice",
				      {"docstatus": 1, "outstanding_amount": [">", 0]},
				      hint=_("Owed to suppliers")),
			],
		)
	)

	lanes.append(
		_lane(
			"produce", _("Produce"), "#0EA5E9", "&#127974;",
			[
				_node(_("Work Orders"), "Work Order",
				      {"docstatus": 1, "status": ["in", ["Not Started", "In Process"]]},
				      hint=_("On the lines now")),
				_node(_("Job Cards"), "Job Card", {"docstatus": 0},
				      hint=_("Operations not yet finished")),
				_node(_("Quality Checks"), "Water Quality Check",
				      {"docstatus": 1, "overall_result": "Fail"},
				      hint=_("Failed — batches blocked")),
				_node(_("Batches"), "Batch", {"neoaqua_qc_status": "Pending"},
				      hint=_("Awaiting release")),
				_node(_("BOMs"), "BOM", {"is_active": 1, "docstatus": 1},
				      hint=_("The five-level recipe tree")),
			],
		)
	)

	lanes.append(
		_lane(
			"distribute", _("Distribute"), "#10B981", "&#128666;",
			[
				_node(_("Load Requests"), "Van Load Request", {"docstatus": 0},
				      hint=_("Drafted, not yet loaded")),
				_node(_("Van Trips"), "Van Trip",
				      {"docstatus": 1, "status": ["in", ["Loaded", "In Progress"]]},
				      hint=_("Vans on the road")),
				_node(_("Check-ins"), "Salesman Check In",
				      {"docstatus": 1, "within_geofence": 0},
				      hint=_("Logged outside the geofence")),
				_node(_("Invoices"), "Sales Invoice", {"docstatus": 1, "posting_date": nowdate()},
				      hint=_("Raised today")),
			],
		)
	)

	lanes.append(
		_lane(
			"settle", _("Settle"), "#F59E0B", "&#128176;",
			[
				_node(_("Collections"), "Payment Entry",
				      {"docstatus": 1, "posting_date": nowdate(), "payment_type": "Receive"},
				      hint=_("Money taken today")),
				_node(_("Day Closes"), "Salesman Day Close", {"docstatus": 0},
				      hint=_("Not yet settled")),
				_node(_("Containers"), "Container Ledger Entry", {"docstatus": 1},
				      hint=_("Returnable bottle ledger")),
				_node(_("Journals"), "Journal Entry", {"docstatus": 0},
				      hint=_("Unposted")),
			],
		)
	)

	return [x for x in lanes if x]


# ---------------------------------------------------------------- tiles
def _tile(label, icon, colour, links):
	"""A module tile. Links the user cannot open are removed; a tile with no
	links left is dropped entirely."""
	allowed = []
	for entry in links:
		label_, kind, target = entry
		if kind == "DocType" and not can(target):
			continue
		if kind == "Report" and not can_report(target):
			continue
		if kind == "Page" and not can_page(target):
			continue
		allowed.append({"label": label_, "kind": kind, "target": target})
	if not allowed:
		return None
	return {"label": label, "icon": icon, "colour": colour, "links": allowed}


def build_tiles():
	tiles = [
		_tile(_("Van Sales"), "&#128666;", "#10B981", [
			(_("Van Trip"), "DocType", "Van Trip"),
			(_("Van Load Request"), "DocType", "Van Load Request"),
			(_("Salesman Check In"), "DocType", "Salesman Check In"),
			(_("Salesman Day Close"), "DocType", "Salesman Day Close"),
			(_("Vans"), "DocType", "Van"),
			(_("Routes"), "DocType", "Van Route"),
			(_("Geofence Zones"), "DocType", "Geofence Zone"),
		]),
		_tile(_("Manufacturing"), "&#127974;", "#0EA5E9", [
			(_("Work Order"), "DocType", "Work Order"),
			(_("Production Planner"), "Page", "neoaqua-production-planner"),
			(_("Production Plan"), "DocType", "Production Plan"),
			(_("Job Card"), "DocType", "Job Card"),
			(_("BOM"), "DocType", "BOM"),
			(_("Stock Entry"), "DocType", "Stock Entry"),
			(_("Workstation"), "DocType", "Workstation"),
		]),
		_tile(_("Quality"), "&#128300;", "#6366F1", [
			(_("Water Quality Check"), "DocType", "Water Quality Check"),
			(_("Batch"), "DocType", "Batch"),
			(_("Batch Naming Rule"), "DocType", "Batch Naming Rule"),
			(_("Batch Code Builder"), "Page", "batch-code-builder"),
		]),
		_tile(_("Procurement"), "&#128230;", "#8B5CF6", [
			(_("Material Request"), "DocType", "Material Request"),
			(_("Purchase Order"), "DocType", "Purchase Order"),
			(_("Purchase Receipt"), "DocType", "Purchase Receipt"),
			(_("Purchase Invoice"), "DocType", "Purchase Invoice"),
			(_("Supplier"), "DocType", "Supplier"),
		]),
		_tile(_("Selling"), "&#128179;", "#EC4899", [
			(_("Sales Invoice"), "DocType", "Sales Invoice"),
			(_("Sales Order"), "DocType", "Sales Order"),
			(_("Customer"), "DocType", "Customer"),
			(_("Item Price"), "DocType", "Item Price"),
			(_("POS Profile"), "DocType", "POS Profile"),
		]),
		_tile(_("Finance"), "&#128176;", "#F59E0B", [
			(_("Payment Entry"), "DocType", "Payment Entry"),
			(_("Journal Entry"), "DocType", "Journal Entry"),
			(_("Container Ledger Entry"), "DocType", "Container Ledger Entry"),
			(_("Accounts Receivable"), "Report", "Accounts Receivable"),
			(_("Accounts Payable"), "Report", "Accounts Payable"),
		]),
		_tile(_("Stock"), "&#128203;", "#14B8A6", [
			(_("Item"), "DocType", "Item"),
			(_("Warehouse"), "DocType", "Warehouse"),
			(_("Stock Entry"), "DocType", "Stock Entry"),
			(_("Stock Reconciliation"), "DocType", "Stock Reconciliation"),
			(_("Stock Ledger"), "Report", "Stock Ledger"),
		]),
		_tile(_("Reports"), "&#128200;", "#64748B", [
			(_("Business Review"), "Page", "neoaqua-business-review"),
			(_("Route Profitability"), "Report", "Route and Van Profitability"),
			(_("Customer Profitability"), "Report", "Customer Profitability and Cost to Serve"),
			(_("Product Contribution"), "Report", "Product Contribution and Pareto"),
			(_("Working Capital"), "Report", "Working Capital and Cash Cycle"),
			(_("Sales Register"), "Report", "Sales Register Van and Channel"),
			(_("Item Sales & Margin"), "Report", "Item wise Sales and Margin"),
			(_("Customer Trend"), "Report", "Customer Sales Trend"),
			(_("Salesman Scorecard"), "Report", "Salesman Performance Scorecard"),
			(_("Receivables Aging"), "Report", "Receivables Aging by Route"),
			(_("Daily Cash Summary"), "Report", "Daily Cash and Sales Summary"),
			(_("VAT Summary"), "Report", "VAT Summary KSA"),
			(_("Van Sales Summary"), "Report", "Van Sales Summary"),
			(_("Day Close Variance"), "Report", "Salesman Day Close Variance"),
			(_("Route Visit Compliance"), "Report", "Route Visit Compliance"),
			(_("Container Balance"), "Report", "Customer Container Balance"),
			(_("Production Yield"), "Report", "Production Yield and Scrap"),
			(_("Batch QC Register"), "Report", "Batch QC Register"),
		]),
	]

	if can("NeoAqua Settings", "write"):
		tiles.append(
			_tile(_("Setup"), "&#9881;", "#475569", [
				(_("NeoAqua Settings"), "DocType", "NeoAqua Settings"),
				(_("Demo Data"), "DocType", "NeoAqua Demo Tool"),
				(_("Control Tower"), "Page", "neoaqua-control-tower"),
			])
		)

	return [t for t in tiles if t]


# ---------------------------------------------------------------- my work
def build_my_work(persona, company):
	"""The three or four things this particular person should act on."""
	items = []
	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	salesman = frappe.db.get_value("Sales Person", {"employee": employee}, "name") if employee else None

	def add(label, value, route, tone=None, sub=None):
		items.append({"label": label, "value": value, "route": route, "tone": tone, "sub": sub})

	if persona["key"] in ("field",) and salesman and can("Van Trip"):
		trip = frappe.db.get_value(
			"Van Trip",
			{"salesman": salesman, "docstatus": 1, "status": ["in", ["Loaded", "In Progress"]]},
			["name", "van", "visited_stops", "planned_stops", "total_invoiced"],
			as_dict=True,
		)
		if trip:
			add(_("Your trip today"), trip.name, ["Form", "Van Trip", trip.name], "good",
			    _("{0} — {1} of {2} stops, {3} invoiced").format(
			        trip.van, trip.visited_stops or 0, trip.planned_stops or 0,
			        frappe.utils.fmt_money(flt(trip.total_invoiced), currency="SAR")))
		else:
			add(_("No open trip"), _("Load the van"), ["new", "Van Trip"], "warn",
			    _("Start the day by loading stock onto your van"))

		pending = frappe.db.count(
			"Van Trip", {"salesman": salesman, "docstatus": 1, "status": "Returned"}
		)
		if pending:
			add(_("Awaiting your day close"), pending, ["List", "Van Trip", {"status": "Returned"}], "bad",
			    _("Cash stays unreconciled until these settle"))

	if persona["key"] in ("plant", "quality", "manager") and can("Work Order"):
		wo = frappe.db.count("Work Order", {"docstatus": 1, "status": "In Process"})
		add(_("Work orders running"), wo, ["List", "Work Order", {"status": "In Process"}])

	if persona["key"] in ("quality", "plant", "manager") and can("Batch"):
		pending_qc = frappe.db.count("Batch", {"neoaqua_qc_status": "Pending"})
		if pending_qc:
			add(_("Batches awaiting release"), pending_qc,
			    ["List", "Batch", {"neoaqua_qc_status": "Pending"}], "warn",
			    _("Finished goods cannot transfer until these pass"))

	if persona["key"] in ("finance", "manager") and can("Sales Invoice"):
		receivable = flt(
			frappe.db.sql(
				"""select sum(outstanding_amount) from `tabSales Invoice`
				   where docstatus = 1 and company = %s""",
				company,
			)[0][0]
		)
		add(_("Receivables"), frappe.utils.fmt_money(receivable, currency="SAR"),
		    ["query-report", "Accounts Receivable"], "warn" if receivable else None)

	if persona["key"] in ("finance", "manager") and can("Salesman Day Close"):
		pending = frappe.db.count("Salesman Day Close", {"docstatus": 0, "status": "Pending Approval"})
		if pending:
			add(_("Day closes to approve"), pending,
			    ["List", "Salesman Day Close", {"status": "Pending Approval"}], "bad",
			    _("Each carries a cash variance"))

	if persona["key"] in ("buying", "manager") and can("Purchase Order"):
		po = frappe.db.count(
			"Purchase Order", {"docstatus": 1, "status": ["in", ["To Receive and Bill", "To Receive"]]}
		)
		add(_("Orders to receive"), po,
		    ["List", "Purchase Order", {"status": ["in", ["To Receive and Bill", "To Receive"]]}])

	return items[:5]


# ---------------------------------------------------------------- actions
def build_actions():
	"""Create buttons, filtered by CREATE permission rather than read."""
	candidates = [
		(_("Van Trip"), "Van Trip", "&#128666;"),
		(_("Load Request"), "Van Load Request", "&#128230;"),
		(_("Day Close"), "Salesman Day Close", "&#128176;"),
		(_("Sales Invoice"), "Sales Invoice", "&#129534;"),
		(_("Work Order"), "Work Order", "&#127974;"),
		(_("Quality Check"), "Water Quality Check", "&#128300;"),
		(_("Material Request"), "Material Request", "&#128203;"),
		(_("Payment Entry"), "Payment Entry", "&#128181;"),
	]
	return [
		{"label": label, "doctype": dt, "icon": icon}
		for label, dt, icon in candidates
		if can(dt, "create")
	]


# ---------------------------------------------------------------- entry
@frappe.whitelist()
def get_hub(company=None):
	company = company or frappe.defaults.get_user_default("company") \
		or frappe.defaults.get_global_default("company")

	persona = detect_persona()
	user = frappe.db.get_value("User", frappe.session.user, ["full_name", "user_image"], as_dict=True) \
		or frappe._dict()

	result = {
		"company": company,
		"user": {"name": frappe.session.user, "full_name": user.get("full_name"),
		         "image": user.get("user_image")},
		"persona": persona,
		"brand": frappe.db.get_single_value("NeoAqua Settings", "brand_name"),
		"lanes": [],
		"tiles": [],
		"my_work": [],
		"actions": [],
	}

	for key, fn in (
		("lanes", lambda: build_map(company)),
		("tiles", build_tiles),
		("my_work", lambda: build_my_work(persona, company)),
		("actions", build_actions),
	):
		try:
			result[key] = fn()
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"NeoAqua Hub: {key}")
			result[key] = []

	try:
		from neoaqua.setup import orchestrator

		if can("NeoAqua Settings", "write"):
			state = orchestrator.status(company)
			result["setup_complete"] = state.get("complete")
			# send the failing checks WITH their counts. "Something is missing"
			# is not a useful thing to tell someone standing in front of it.
			result["setup_missing"] = [
				{"check": c["check"], "actual": c["actual"], "expected": c["expected"]}
				for c in state.get("checks", []) if not c["ok"]
			]
			result["setup_can_fix"] = True
	except Exception:
		result["setup_complete"] = True

	return result


@frappe.whitelist()
def run_setup_from_hub(company=None):
	"""Run the plant setup from the Hub banner.

	Someone looking at "the plant is not fully set up" should be able to fix it
	where they are standing, rather than being sent to find another page.
	"""
	if not can("NeoAqua Settings", "write"):
		frappe.throw(
			_("You do not have permission to run the plant setup."), frappe.PermissionError
		)

	from neoaqua.setup import orchestrator

	return orchestrator.run_setup(company)
