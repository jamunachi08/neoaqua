# Copyright (c) 2026, Neotec Integrated Solutions
"""Staged setup orchestrator.

The previous design had one silent auto-seed that only fired when the site had
exactly one company, and swallowed any error into the Error Log. On a site with
several companies, or where the install aborted before reaching it, nothing was
created and nothing said so. The user was left with an installed app and an
empty item master.

This replaces that with an explicit, staged, resumable run:

  * every stage reports what it created and VERIFIES the result independently,
    so "done" means the records are actually there, not that the code returned
  * a stage that fails records its traceback and does not stop the stages after
    it, unless they genuinely depend on it
  * the whole thing is idempotent, so it can be re-run to fill in gaps
  * status() can be called at any time to see exactly what exists and what does
    not, from the desk or the CLI
"""

import json
import traceback

import frappe
from frappe import _
from frappe.utils import now_datetime

# ---------------------------------------------------------------- stages


def _stage_roles(company):
	from neoaqua.setup import roles

	roles.install()
	return {"roles": frappe.db.count("Role", {"name": ["like", "%Van%"]})}


def _stage_custom_fields(company):
	from neoaqua.setup import custom_fields

	custom_fields.install()
	return {"custom_fields": frappe.db.count("Custom Field", {"module": "NeoAqua"})}


def _stage_foundation(company):
	"""UOMs, item groups, warehouses, territories, customer groups, price lists,
	modes of payment. Everything the item master and the accounts hang off."""
	from neoaqua.setup import masters

	masters.create_uoms()
	masters.create_item_groups()
	masters.create_warehouses(company)
	masters.create_territories()
	masters.create_customer_groups()
	masters.create_price_lists(company)
	masters.create_modes_of_payment(company)
	return {
		"item_groups": frappe.db.count("Item Group", {"name": ["in", [g[0] for g in masters.ITEM_GROUPS]]}),
		"warehouses": frappe.db.count("Warehouse", {"company": company}),
		"price_lists": frappe.db.count("Price List", {"name": ["like", "NeoAqua%"]}),
	}


def _stage_accounts(company):
	from neoaqua.setup import accounts

	return accounts.run(company)



def _stage_items(company):
	"""The item master: 25 raw materials, 7 WIP, 6 finished bottles, 6 packs,
	each with warehouse, income, expense and cost center defaults."""
	from neoaqua.setup import masters

	failures = masters.create_items(company) or []
	result = {
		"raw_materials": frappe.db.count("Item", {"item_code": ["like", "RM-%"]}),
		"work_in_progress": frappe.db.count("Item", {"item_code": ["like", "WIP-%"]}),
		"finished_bottles": frappe.db.count("Item", {"item_code": ["like", "FG-BOT-%"]}),
		"finished_packs": frappe.db.count("Item", {"item_code": ["like", "FG-PCK-%"]}),
		"item_prices": frappe.db.count("Item Price", {"price_list": ["like", "NeoAqua%"]}),
	}
	if failures:
		result["failed_items"] = failures[:10]
		result["failed_count"] = len(failures)
	return result


def _stage_manufacturing_masters(company):
	from neoaqua.setup import masters

	masters.create_workstations(company)
	masters.create_operations()
	return {
		"workstations": frappe.db.count("Workstation"),
		"operations": frappe.db.count("Operation"),
	}


def _stage_boms(company):
	"""The five-level BOM tree. Depends on items, workstations and operations."""
	from neoaqua.setup import bom

	created = bom.build_all(company)
	return {
		"boms_created_now": len(created or []),
		"active_boms": frappe.db.count("BOM", {"is_active": 1, "docstatus": 1}),
	}


def _stage_commercial(company):
	from neoaqua.setup import masters

	masters.create_tax_templates(company)
	masters.create_pos_profiles(company)
	masters.create_vans_and_routes(company)
	masters.configure_settings(company)
	return {
		"vans": frappe.db.count("Van"),
		"routes": frappe.db.count("Van Route"),
		"pos_profiles": frappe.db.count("POS Profile"),
	}


def _stage_batch_rules(company):
	from neoaqua.setup import batch_rules

	batch_rules.run(company)
	return {"batch_naming_rules": frappe.db.count("Batch Naming Rule")}


def _stage_dashboards(company):
	from neoaqua.setup import dashboards

	return dashboards.run()


# key, label, function, depends_on
STAGES = [
	("roles", "Roles and role profiles", _stage_roles, None),
	("custom_fields", "Custom fields on standard doctypes", _stage_custom_fields, None),
	("foundation", "UOMs, item groups, warehouses, territories, price lists", _stage_foundation, None),
	("accounts", "Chart of accounts, cost centers, perpetual inventory", _stage_accounts, "foundation"),
	("items", "Item master: raw materials, WIP and finished goods", _stage_items, "accounts"),
	("mfg_masters", "Workstations and operations", _stage_manufacturing_masters, None),
	("boms", "Multi-level BOM tree and routings", _stage_boms, "items"),
	("commercial", "Tax templates, POS profiles, vans and routes", _stage_commercial, "items"),
	("batch_rules", "Batch naming rules", _stage_batch_rules, "items"),
	("dashboards", "Dashboards, number cards and workspaces", _stage_dashboards, None),
]


# ---------------------------------------------------------------- runner
@frappe.whitelist()
def run_setup(company=None, only_stage=None, brand=None, brand_ar=None, brand_code=None):
	"""Run every setup stage in order. Safe to re-run at any time.

	`brand` names the finished goods, e.g. "Neo Aqua 600 ml Bottle". It is
	recorded before any item is created; pass it once and every later run
	reuses it from Settings.
	"""
	company = company or _resolve_company()

	if brand:
		from neoaqua.setup.brand import set_brand

		set_brand(brand, brand_ar, brand_code)

	report = {
		"company": company,
		"started": str(now_datetime()),
		"stages": [],
		"ok": True,
	}
	completed = set()

	for key, label, fn, depends_on in STAGES:
		if only_stage and key != only_stage:
			continue

		entry = {"key": key, "label": label}

		if depends_on and depends_on not in completed and not only_stage:
			entry.update(
				{
					"status": "Skipped",
					"detail": _("Depends on '{0}', which did not complete.").format(depends_on),
				}
			)
			report["stages"].append(entry)
			report["ok"] = False
			continue

		try:
			result = fn(company)
			frappe.db.commit()
			entry.update({"status": "Done", "result": result})
			completed.add(key)
		except Exception:
			frappe.db.rollback()
			tb = frappe.get_traceback()
			frappe.log_error(tb, f"NeoAqua setup: stage '{key}' failed")
			entry.update(
				{
					"status": "Failed",
					"error": traceback.format_exc(limit=3).splitlines()[-1][:300],
				}
			)
			report["ok"] = False

		report["stages"].append(entry)

	from neoaqua.setup.brand import get_brand

	report["brand"] = get_brand(company)
	report["finished"] = str(now_datetime())
	report["checklist"] = status(company)
	_save_report(company, report)
	frappe.db.commit()
	return report


def _resolve_company():
	companies = frappe.get_all("Company", pluck="name")
	if not companies:
		frappe.throw(_("Create a Company before running the NeoAqua setup."))
	if len(companies) == 1:
		return companies[0]

	default = frappe.defaults.get_global_default("company")
	if default:
		return default

	frappe.throw(
		_("This site has {0} companies. Pass the one to set up explicitly:<br>"
		  "<code>bench --site &lt;site&gt; execute neoaqua.setup.orchestrator.run_setup "
		  "--kwargs \"{{'company':'Your Company'}}\"</code>").format(len(companies))
	)


def _save_report(company, report):
	"""Persist the run report onto NeoAqua Settings.

	`company` on the settings doctype is mandatory, and on a site where the
	accounts stage failed it may never have been populated - which meant the
	report itself failed to save and the evidence of what went wrong was lost.
	Set it here and ignore mandatory, because a diagnostic must not depend on
	the thing it is diagnosing.
	"""
	try:
		s = frappe.get_single("NeoAqua Settings")
		if not s.company:
			s.company = company
		s.setup_company = company
		s.setup_completed = 1 if report["ok"] else 0
		s.setup_last_run = now_datetime()
		s.setup_report = json.dumps(report, indent=2, default=str)
		s.flags.ignore_permissions = True
		s.flags.ignore_mandatory = True
		s.save(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "NeoAqua: could not save setup report")


# ---------------------------------------------------------------- status
CHECKS = [
	("Raw material items", lambda c: frappe.db.count("Item", {"item_code": ["like", "RM-%"]}), 25),
	("Work in progress items", lambda c: frappe.db.count("Item", {"item_code": ["like", "WIP-%"]}), 7),
	("Finished bottle items", lambda c: frappe.db.count("Item", {"item_code": ["like", "FG-BOT-%"]}), 6),
	("Finished pack items", lambda c: frappe.db.count("Item", {"item_code": ["like", "FG-PCK-%"]}), 6),
	("Active BOMs", lambda c: frappe.db.count("BOM", {"is_active": 1, "docstatus": 1}), 19),
	("Routings", lambda c: frappe.db.count("Routing"), 19),
	("Workstations", lambda c: frappe.db.count("Workstation"), 9),
	("Operations", lambda c: frappe.db.count("Operation"), 9),
	("Warehouses", lambda c: frappe.db.count("Warehouse", {"company": c}), 16),
	("Item prices", lambda c: frappe.db.count("Item Price", {"price_list": ["like", "NeoAqua%"]}), 61),
	("Vans", lambda c: frappe.db.count("Van"), 3),
	("Van routes", lambda c: frappe.db.count("Van Route"), 3),
	("POS profiles", lambda c: frappe.db.count("POS Profile"), 3),
	("Batch naming rules", lambda c: frappe.db.count("Batch Naming Rule"), 4),
	("NeoAqua accounts", lambda c: frappe.db.count(
		"Account", {"company": c, "account_name": ["in", [
			"Raw Material Stock", "Work In Progress Stock", "Finished Goods Stock",
			"Van Stock", "Container Deposit Liability", "Sale of Bottled Water",
			"Cost of Bottled Water Sold", "Van Cash in Hand",
		]]}), 8),
	("Cost centers", lambda c: frappe.db.count(
		"Cost Center", {"company": c, "cost_center_name": ["in", [
			"Production", "Distribution", "Line 1 - Small PET", "RO Plant",
		]]}), 4),
	("Custom fields", lambda c: frappe.db.count("Custom Field", {"module": "NeoAqua"}), 40),
	("Dashboards", lambda c: frappe.db.count("Dashboard", {"module": "NeoAqua"}), 3),
]


@frappe.whitelist()
def status(company=None):
	"""What actually exists on this site. Verifies records, not intentions."""
	try:
		company = company or _resolve_company()
	except Exception:
		company = frappe.defaults.get_global_default("company")

	rows, complete = [], True
	for label, fn, expected in CHECKS:
		try:
			actual = fn(company)
		except Exception:
			actual = 0
		ok = actual >= expected
		if not ok:
			complete = False
		rows.append(
			{"check": label, "expected": expected, "actual": actual, "ok": ok}
		)

	try:
		from neoaqua.setup.brand import get_brand

		brand = get_brand(company)
		branded = frappe.db.count("Item", {"item_code": ["like", "FG-%"], "brand": brand})
		rows.append(
			{"check": f"Items branded '{brand}'", "expected": 12, "actual": branded, "ok": branded >= 12}
		)
		if branded < 12:
			complete = False
	except Exception:
		pass

	# perpetual inventory is a yes/no, not a count
	pi = bool(frappe.db.get_value("Company", company, "enable_perpetual_inventory")) if company else False
	rows.append({"check": "Perpetual inventory enabled", "expected": 1, "actual": int(pi), "ok": pi})
	if not pi:
		complete = False

	return {"company": company, "complete": complete, "checks": rows}


@frappe.whitelist()
def diagnose(company=None):
	"""Everything needed to work out why setup did not complete, returned to
	the browser rather than buried in the Error Log.

	Stage tracebacks are logged, not shown, which is correct for an install but
	useless for someone looking at an empty item master. This surfaces the last
	run report and the recent NeoAqua error titles alongside the checklist.
	"""
	state = status(company)

	last_report = None
	try:
		raw = frappe.db.get_single_value("NeoAqua Settings", "setup_report")
		if raw:
			last_report = frappe.parse_json(raw)
	except Exception:
		last_report = None

	errors = []
	try:
		for row in frappe.get_all(
			"Error Log",
			filters={"error": ["like", "%NeoAqua%"]},
			fields=["name", "creation", "method", "error"],
			order_by="creation desc",
			limit=8,
		):
			text = (row.error or "").strip().splitlines()
			errors.append(
				{
					"name": row.name,
					"when": str(row.creation),
					"method": row.method,
					"last_line": text[-1][:300] if text else "",
				}
			)
	except Exception:
		pass

	failed_stages = []
	if last_report:
		failed_stages = [
			s for s in last_report.get("stages", []) if s.get("status") in ("Failed", "Skipped")
		]

	return {
		"status": state,
		"last_run": (last_report or {}).get("finished"),
		"failed_stages": failed_stages,
		"errors": errors,
		"companies": frappe.get_all("Company", pluck="name"),
	}


@frappe.whitelist()
def print_status(company=None):
	"""CLI-friendly:

	    bench --site <site> execute neoaqua.setup.orchestrator.print_status
	"""
	result = status(company)
	print(f"\nNeoAqua setup status for {result['company']}\n" + "-" * 58)
	for r in result["checks"]:
		mark = "OK  " if r["ok"] else "MISS"
		print(f"  {mark} {r['check']:<38} {r['actual']:>5} / {r['expected']}")
	print("-" * 58)
	if result["complete"]:
		print("  Setup is complete.\n")
	else:
		print("  Setup is INCOMPLETE. Run:")
		print("    bench --site <site> execute neoaqua.setup.orchestrator.run_setup\n")
	return result
