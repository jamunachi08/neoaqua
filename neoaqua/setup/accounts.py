# Copyright (c) 2026, Neotec Integrated Solutions
"""Accounting setup for a bottled-water plant.

Creates the accounts, cost centers and warehouse-to-account mappings that the
rest of the app posts against, then wires them into the Company defaults and
NeoAqua Settings so an installed site can transact immediately.

Everything is idempotent and additive. Existing accounts are reused, never
renamed or moved, so this is safe to run on a company that already has a live
chart of accounts.

Account placement is resolved by root_type and a list of likely parent names
rather than by hardcoded paths, because the parent differs between the
standard chart, the Saudi chart and whatever the client's accountant built.
"""

import frappe
from frappe import _
from frappe.utils import cint

# ---------------------------------------------------------------- helpers


def abbr(company):
	return frappe.get_cached_value("Company", company, "abbr")


def _find_parent(company, root_type, candidates, account_type=None):
	"""Locate a sensible group account to hang new accounts under."""
	for name in candidates:
		acc = frappe.db.get_value(
			"Account",
			{"company": company, "account_name": name, "is_group": 1},
			"name",
		)
		if acc:
			return acc

	if account_type:
		acc = frappe.db.get_value(
			"Account",
			{"company": company, "account_type": account_type, "is_group": 1},
			"name",
		)
		if acc:
			return acc

	# fall back to the first group under the right root
	return frappe.db.get_value(
		"Account",
		{"company": company, "root_type": root_type, "is_group": 1, "parent_account": ["!=", ""]},
		"name",
	) or frappe.db.get_value(
		"Account", {"company": company, "root_type": root_type, "is_group": 1}, "name"
	)


def create_account(company, account_name, parent, root_type, account_type=None,
                   is_group=0, number=None, tax_rate=None):
	"""Create one account if it does not already exist. Returns its name."""
	a = abbr(company)
	existing = frappe.db.get_value(
		"Account", {"company": company, "account_name": account_name}, "name"
	)
	if existing:
		return existing
	if not parent:
		return None

	doc = frappe.new_doc("Account")
	doc.update(
		{
			"account_name": account_name,
			"parent_account": parent,
			"company": company,
			"root_type": root_type,
			"account_type": account_type,
			"is_group": is_group,
			"account_number": number,
			"tax_rate": tax_rate,
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	try:
		doc.insert()
		return doc.name
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"NeoAqua: account {account_name}")
		return None


def create_cost_center(company, name, parent, is_group=0):
	existing = frappe.db.get_value(
		"Cost Center", {"company": company, "cost_center_name": name}, "name"
	)
	if existing:
		return existing
	if not parent:
		return None
	doc = frappe.new_doc("Cost Center")
	doc.update(
		{
			"cost_center_name": name,
			"parent_cost_center": parent,
			"company": company,
			"is_group": is_group,
		}
	)
	doc.flags.ignore_permissions = True
	try:
		doc.insert()
		return doc.name
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"NeoAqua: cost center {name}")
		return None


# ---------------------------------------------------------------- accounts
def build_accounts(company):
	"""Create every account NeoAqua posts against. Returns a name map."""
	acc = {}

	asset_parent = _find_parent(company, "Asset", ["Current Assets", "Stock Assets"])
	stock_parent = _find_parent(company, "Asset", ["Stock Assets", "Current Assets"], "Stock")
	cash_parent = _find_parent(company, "Asset", ["Cash In Hand", "Bank Accounts", "Current Assets"], "Cash")
	liab_parent = _find_parent(company, "Liability", ["Current Liabilities", "Accounts Payable"])
	income_parent = _find_parent(company, "Income", ["Direct Income", "Income"])
	ind_income_parent = _find_parent(company, "Income", ["Indirect Income", "Direct Income", "Income"])
	cogs_parent = _find_parent(company, "Expense", ["Cost of Goods Sold", "Direct Expenses", "Expenses"])
	exp_parent = _find_parent(company, "Expense", ["Indirect Expenses", "Expenses"])

	# ---- stock assets, one per stage so the balance sheet shows where value sits
	acc["stock_group"] = create_account(
		company, "Water Plant Stock", stock_parent, "Asset", is_group=1
	)
	sp = acc["stock_group"] or stock_parent
	acc["rm_stock"] = create_account(company, "Raw Material Stock", sp, "Asset", "Stock")
	acc["wip_stock"] = create_account(company, "Work In Progress Stock", sp, "Asset", "Stock")
	acc["fg_stock"] = create_account(company, "Finished Goods Stock", sp, "Asset", "Stock")
	acc["van_stock"] = create_account(company, "Van Stock", sp, "Asset", "Stock")
	acc["quarantine_stock"] = create_account(company, "Quarantine Stock", sp, "Asset", "Stock")
	acc["container_asset"] = create_account(
		company, "Returnable Containers in Market", sp, "Asset", "Stock"
	)

	# ---- cash held by salesmen, separate from the cashier's till
	acc["van_cash"] = create_account(
		company, "Van Cash in Hand", cash_parent, "Asset", "Cash"
	)

	# ---- liabilities
	acc["container_deposit"] = create_account(
		company, "Container Deposit Liability", liab_parent, "Liability", "Payable"
	)

	# ---- income
	acc["water_sales"] = create_account(
		company, "Sale of Bottled Water", income_parent, "Income", "Income Account"
	)
	acc["container_income"] = create_account(
		company, "Container Forfeiture Income", ind_income_parent, "Income", "Income Account"
	)
	acc["cash_over"] = create_account(
		company, "Cash Overage", ind_income_parent, "Income", "Income Account"
	)

	# ---- cost of sales
	acc["cogs"] = create_account(
		company, "Cost of Bottled Water Sold", cogs_parent, "Expense", "Cost of Goods Sold"
	)
	acc["stock_adjustment"] = create_account(
		company, "Stock Adjustment - Water", cogs_parent, "Expense", "Stock Adjustment"
	)
	acc["damage"] = create_account(
		company, "Stock Damage and Scrap", cogs_parent, "Expense", "Expense Account"
	)
	acc["cash_short"] = create_account(
		company, "Cash Shortage", cogs_parent, "Expense", "Expense Account"
	)

	# ---- route expenses, mirroring the Day Close Expense options
	acc["route_group"] = create_account(
		company, "Route Distribution Expenses", exp_parent, "Expense", is_group=1
	)
	rp = acc["route_group"] or exp_parent
	for label, key in (
		("Fuel", "fuel"),
		("Toll and Salik", "toll"),
		("Vehicle Parking", "parking"),
		("Vehicle Repair and Maintenance", "repair"),
		("Loading and Unloading Labour", "labour"),
		("Driver Meals and Allowance", "meals"),
		("Municipality and Traffic Fines", "fines"),
		("Other Route Expenses", "other"),
	):
		acc[key] = create_account(company, label, rp, "Expense", "Expense Account")

	return acc


# ---------------------------------------------------------------- cost centers
def build_cost_centers(company):
	a = abbr(company)
	root = frappe.db.get_value(
		"Cost Center", {"company": company, "is_group": 1, "parent_cost_center": ["in", ["", None]]}, "name"
	) or f"{company} - {a}"

	cc = {}
	cc["production"] = create_cost_center(company, "Production", root, is_group=1)
	for line in ("RO Plant", "Blow Moulding", "Line 1 - Small PET",
	             "Line 2 - Large PET", "Line 3 - 5 Gallon", "Packing and Palletising"):
		cc[line] = create_cost_center(company, line, cc["production"] or root)

	cc["distribution"] = create_cost_center(company, "Distribution", root, is_group=1)
	for van in ("Van 01 - Riyadh North", "Van 02 - Riyadh South", "Van 03 - Riyadh East"):
		cc[van] = create_cost_center(company, van, cc["distribution"] or root)

	cc["admin"] = create_cost_center(company, "Administration", root)
	return cc


# ---------------------------------------------------------------- wiring
def enable_perpetual_inventory(company, acc):
	"""Turn on perpetual inventory and point the company defaults at the
	accounts just created. Without this, stock movements post nothing to the
	general ledger and the manufacturing cost never reaches the P&L."""
	doc = frappe.get_doc("Company", company)
	changed = False

	def set_company_default(field, value):
		nonlocal changed
		if value and not doc.get(field):
			doc.set(field, value)
			changed = True

	if not cint(doc.enable_perpetual_inventory):
		doc.enable_perpetual_inventory = 1
		changed = True

	set_company_default("default_inventory_account", acc.get("fg_stock"))
	set_company_default("stock_adjustment_account", acc.get("stock_adjustment"))
	set_company_default("default_expense_account", acc.get("cogs"))
	set_company_default("default_income_account", acc.get("water_sales"))

	if not doc.stock_received_but_not_billed:
		srbnb = frappe.db.get_value(
			"Account",
			{"company": company, "account_type": "Stock Received But Not Billed", "is_group": 0},
			"name",
		)
		set_company_default("stock_received_but_not_billed", srbnb)

	if not doc.expenses_included_in_valuation:
		eiv = frappe.db.get_value(
			"Account",
			{"company": company, "account_type": "Expenses Included In Valuation", "is_group": 0},
			"name",
		)
		set_company_default("expenses_included_in_valuation", eiv)

	if changed:
		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		doc.save()


WAREHOUSE_ACCOUNTS = {
	"Raw Material Store": "rm_stock",
	"Preform Store": "rm_stock",
	"Chemical Store": "rm_stock",
	"Packaging Store": "rm_stock",
	"Work In Progress": "wip_stock",
	"RO Plant": "wip_stock",
	"Blow Moulding WIP": "wip_stock",
	"Filling WIP": "wip_stock",
	"Finished Goods Store": "fg_stock",
	"QC Quarantine": "quarantine_stock",
	"Scrap & Rejection": "quarantine_stock",
	"Empty Container Yard": "container_asset",
	"Van 01 - Riyadh North": "van_stock",
	"Van 02 - Riyadh South": "van_stock",
	"Van 03 - Riyadh East": "van_stock",
}


def map_warehouse_accounts(company, acc):
	"""Give each warehouse its own stock account so the balance sheet shows
	raw material, WIP, finished goods and van stock as separate lines."""
	a = abbr(company)
	for wh_name, key in WAREHOUSE_ACCOUNTS.items():
		full = f"{wh_name} - {a}"
		account = acc.get(key)
		if not account or not frappe.db.exists("Warehouse", full):
			continue
		if frappe.db.get_value("Warehouse", full, "account"):
			continue
		frappe.db.set_value("Warehouse", full, "account", account, update_modified=False)


GROUP_ACCOUNTS = {
	"Water & Packaging RM": ("rm_stock", None, None),
	"Water Source": ("rm_stock", None, None),
	"Preforms & Closures": ("rm_stock", None, None),
	"Labels & Secondary Packaging": ("rm_stock", None, None),
	"Treatment Chemicals": ("rm_stock", None, None),
	"Water WIP": ("wip_stock", None, None),
	"Treated Water": ("wip_stock", None, None),
	"Blown Bottles": ("wip_stock", None, None),
	"Bottled Water - Small PET": ("fg_stock", "water_sales", "cogs"),
	"Bottled Water - Large PET": ("fg_stock", "water_sales", "cogs"),
	"Bottled Water - 5 Gallon": ("fg_stock", "water_sales", "cogs"),
	"Returnable Containers": ("container_asset", "container_income", "cogs"),
}


def set_item_group_defaults(company, acc, cc):
	"""Set accounts at item-group level so any item added later inherits them
	without anyone having to remember."""
	a = abbr(company)
	for group, (stock_key, income_key, expense_key) in GROUP_ACCOUNTS.items():
		if not frappe.db.exists("Item Group", group):
			continue
		doc = frappe.get_doc("Item Group", group)
		if any(d.company == company for d in doc.item_group_defaults):
			continue
		row = {
			"company": company,
			"income_account": acc.get(income_key) if income_key else None,
			"expense_account": acc.get(expense_key) if expense_key else None,
			"buying_cost_center": cc.get("admin"),
			"selling_cost_center": cc.get("distribution") or cc.get("admin"),
		}
		wh = _group_warehouse(group, a)
		if wh:
			row["default_warehouse"] = wh
		doc.append("item_group_defaults", row)
		doc.flags.ignore_permissions = True
		try:
			doc.save()
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"NeoAqua: item group defaults {group}")


def _group_warehouse(group, a):
	if group.startswith("Bottled Water"):
		wh = f"Finished Goods Store - {a}"
	elif group in ("Water WIP", "Treated Water", "Blown Bottles"):
		wh = f"Work In Progress - {a}"
	elif group == "Returnable Containers":
		wh = f"Empty Container Yard - {a}"
	else:
		wh = f"Raw Material Store - {a}"
	return wh if frappe.db.exists("Warehouse", wh) else None


ROUTE_EXPENSE_MAP = [
	("Fuel", "fuel"),
	("Toll / Salik", "toll"),
	("Parking", "parking"),
	("Vehicle Repair", "repair"),
	("Loading Labour", "labour"),
	("Meals", "meals"),
	("Municipality Fine", "fines"),
	("Other", "other"),
]


def configure_settings_accounts(company, acc, cc):
	"""Point NeoAqua Settings at the accounts, and build the route-expense
	mapping used to default the account on every Day Close Expense row."""
	s = frappe.get_single("NeoAqua Settings")
	s.company = s.company or company

	def setd(field, value):
		if value and not s.get(field):
			s.set(field, value)

	setd("cash_account", acc.get("van_cash"))
	setd("container_deposit_account", acc.get("container_deposit"))
	setd("cash_variance_account", acc.get("cash_short"))
	setd("cash_overage_account", acc.get("cash_over"))
	setd("stock_damage_account", acc.get("damage"))
	setd("default_income_account", acc.get("water_sales"))
	setd("default_cogs_account", acc.get("cogs"))
	setd("distribution_cost_center", cc.get("distribution"))

	if not s.route_expense_accounts:
		for label, key in ROUTE_EXPENSE_MAP:
			if acc.get(key):
				s.append("route_expense_accounts", {"expense_type": label, "expense_account": acc[key]})

	s.flags.ignore_permissions = True
	s.save()


# ---------------------------------------------------------------- entry point
def run(company=None):
	"""Build the accounting layer.

	Each step is isolated. Creating the accounts is what the item master
	actually depends on; wiring company defaults, warehouse accounts and item
	group defaults are refinements. A failure in a refinement must not cost
	you the item master - which is exactly what happened when a NameError in
	the perpetual-inventory step took the whole stage down and skipped items,
	BOMs, vans and batch rules with it.
	"""
	company = company or frappe.defaults.get_global_default("company")
	if not company:
		frappe.throw(_("Create a Company before running the NeoAqua accounting setup."))

	failures = []

	def step(label, fn, *args):
		try:
			return fn(*args)
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), f"NeoAqua accounts: {label}")
			failures.append(f"{label}: {str(e)[:160]}")
			return None

	# load-bearing: without these there is nothing to wire
	acc = build_accounts(company) or {}
	cc = build_cost_centers(company) or {}

	# refinements
	step("perpetual inventory", enable_perpetual_inventory, company, acc)
	step("warehouse accounts", map_warehouse_accounts, company, acc)
	step("item group defaults", set_item_group_defaults, company, acc, cc)
	step("settings accounts", configure_settings_accounts, company, acc, cc)

	frappe.db.commit()
	result = {
		"accounts": len([v for v in acc.values() if v]),
		"cost_centers": len([v for v in cc.values() if v]),
	}
	if failures:
		result["warnings"] = failures
	return result


@frappe.whitelist()
def get_expense_account(expense_type):
	"""Called from the Day Close Expense child table to default the account."""
	s = frappe.get_cached_doc("NeoAqua Settings")
	for row in s.route_expense_accounts or []:
		if row.expense_type == expense_type:
			return row.expense_account
	return None
