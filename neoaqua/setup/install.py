# Copyright (c) 2026, Neotec Integrated Solutions
"""Install / migrate orchestration.

Every step is idempotent. `after_migrate` re-runs the light-weight steps so a
`bench migrate` after a Frappe Cloud deployment self-heals custom fields,
roles, dashboards and workspaces without operator intervention. The heavy
master-data seeder only auto-runs when the site has exactly one company and no
NeoAqua items yet, so it never surprises a live database.
"""

import frappe

from neoaqua.setup import custom_fields, dashboards, roles


def _safe(step, fn, *args, **kwargs):
	"""Run an install step without letting a cosmetic failure abort the whole
	app installation. Only the steps the app genuinely cannot run without -
	roles and custom fields - are allowed to raise."""
	try:
		return fn(*args, **kwargs)
	except Exception:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), f"NeoAqua install: {step} failed")
		print(f"  ! NeoAqua: {step} failed and was skipped. See the Error Log, "
		      f"then run: bench --site <site> execute neoaqua.setup.install.repair")
		return None


def after_install():
	from neoaqua.setup import orchestrator

	# load-bearing: the app cannot function without these
	roles.install()
	custom_fields.install()
	frappe.db.commit()

	companies = frappe.get_all("Company", pluck="name")
	default = frappe.defaults.get_global_default("company")
	company = companies[0] if len(companies) == 1 else default

	if not company:
		_print_next_steps(
			"No company found on this site."
			if not companies
			else f"This site has {len(companies)} companies and no global default."
		)
		return

	report = orchestrator.run_setup(company)
	frappe.db.commit()
	_print_report(report)
	print("\nNeoAqua installed. Run:\n"
	      "  bench --site <site> execute neoaqua.setup.install.seed_plant --kwargs \"{'company':'Your Company'}\"\n"
	      "to load water-plant masters, BOMs and routings.\n")


def after_migrate():
	"""Self-heal on every deployment.

	Roles, custom fields and dashboards are re-applied unconditionally. Master
	data is NOT created here - creating items and accounts as a side effect of
	a deployment would be a surprise. Instead, if the plant is not set up, say
	so loudly, because the previous silent skip is exactly why sites ended up
	with an empty item master.
	"""
	from neoaqua.setup import orchestrator

	roles.install()
	custom_fields.install()
	frappe.db.commit()
	_safe("dashboards and workspaces", dashboards.run)
	frappe.db.commit()

	try:
		state = orchestrator.status()
		if not state.get("complete"):
			missing = [c["check"] for c in state["checks"] if not c["ok"]]
			_print_next_steps(
				"Plant masters are incomplete: " + ", ".join(missing[:6])
				+ ("..." if len(missing) > 6 else "")
			)
	except Exception:
		pass


def _print_report(report):
	print("\n" + "=" * 64)
	print("  NeoAqua setup")
	print("=" * 64)
	for stage in report.get("stages", []):
		mark = {"Done": "OK  ", "Failed": "FAIL", "Skipped": "SKIP"}.get(stage["status"], "??  ")
		print(f"  {mark} {stage['label']}")
		if stage.get("error"):
			print(f"        {stage['error']}")
		elif stage.get("detail"):
			print(f"        {stage['detail']}")
	print("-" * 64)
	if report.get("ok"):
		print("  Setup complete. Open NeoAqua Settings to review the checklist.")
	else:
		print("  Some stages did not complete. Tracebacks are in the Error Log.")
		print("  Retry with:")
		print("    bench --site <site> execute neoaqua.setup.orchestrator.run_setup")
	print("=" * 64 + "\n")


def _print_next_steps(reason):
	print("\n" + "=" * 64)
	print("  NeoAqua: plant masters were NOT created")
	print("=" * 64)
	print(f"  Reason: {reason}")
	print("  Create them with:")
	print("    bench --site <site> execute neoaqua.setup.orchestrator.run_setup \\")
	print("      --kwargs \"{'company':'Your Company'}\"")
	print("  Check what exists at any time with:")
	print("    bench --site <site> execute neoaqua.setup.orchestrator.print_status")
	print("=" * 64 + "\n")


def before_uninstall():
	custom_fields.uninstall()


@frappe.whitelist()
def seed_plant(company=None, with_boms=True):
	"""Backwards-compatible alias for the staged orchestrator."""
	from neoaqua.setup import orchestrator

	return orchestrator.run_setup(company)


def _legacy_seed_plant(company=None, with_boms=True):
	"""Load the full water-plant master set: UOMs, item groups, warehouses,
	items, price lists, tax templates, workstations, operations, vans, routes,
	POS profiles and the multi-level BOM tree."""
	from neoaqua.setup import accounts, batch_rules, bom, masters

	company = company or frappe.defaults.get_global_default("company")

	# order matters: warehouses and item groups must exist before accounts can
	# be mapped to them, and accounts must exist before items can reference
	# them in item_defaults.
	result = {"masters_pass_1": masters.run(company)}
	result["accounts"] = accounts.run(company)
	result["masters_pass_2"] = masters.run(company)
	if with_boms:
		result["boms"] = bom.build_all(company)
	result["batch_rules"] = batch_rules.run(company)
	frappe.db.commit()
	return result


@frappe.whitelist()
def setup_all(company=None, with_demo=False, brand=None):
	"""One command to take a bare site to a working water plant.

	    bench --site <site> execute neoaqua.setup.install.setup_all \
	      --kwargs "{'company':'Neo Aqua','brand':'Neo Aqua','with_demo':True}"
	"""
	from neoaqua.setup import orchestrator

	result = orchestrator.run_setup(company, brand=brand)
	if with_demo and result.get("ok"):
		from neoaqua.setup import demo

		result["demo"] = demo.generate(company=result["company"])
	elif with_demo:
		result["demo"] = "skipped - setup did not complete"
	frappe.db.commit()
	return result


@frappe.whitelist()
def repair():
	"""Browser- and CLI-callable self-heal.

	Re-applies roles and custom fields, then rebuilds any dashboard artifact
	that is missing or was left half-created by a failed install. Safe to run
	repeatedly on a live site - nothing here touches transactional data.

	    bench --site <site> execute neoaqua.setup.install.repair
	"""
	result = {}
	roles.install()
	custom_fields.install()
	frappe.db.commit()

	result["dashboards"] = dashboards.run()
	result["orphans_removed"] = cleanup_orphan_dashboard_artifacts()

	# Patches that existed at install time are auto-marked as already-run by
	# Frappe, so they never execute on the site that first installed them.
	# Anything a patch would have done is re-applied here instead, which is
	# why repair() - not migrate - is the command that makes a site correct.
	companies = frappe.get_all("Company", pluck="name")
	if len(companies) == 1 and frappe.db.exists("Item", "FG-BOT-600"):
		company = companies[0]
		from neoaqua.setup import accounts, batch_rules, masters

		result["accounts"] = _safe("accounting setup", accounts.run, company)
		result["item_defaults"] = _safe("item defaults", masters.create_items, company)
		result["batch_rules"] = _safe("batch naming rules", batch_rules.run, company)

	frappe.db.commit()
	return result


@frappe.whitelist()
def cleanup_orphan_dashboard_artifacts():
	"""Remove NeoAqua charts and cards left behind under an old label by a
	build that assigned doc.name before insert - Dashboard Chart autonames
	from chart_name and Number Card from label, so those assignments were
	discarded and the records landed under the wrong name."""
	removed = []

	legacy_charts = [
		"Daily Sales Value", "Sales by Van", "Sales by Channel", "Route Coverage %",
		"Visit Outcomes", "Production by Line", "Daily Finished Goods Output",
		"Quality Check Results", "Monthly Revenue", "Cash Variance Trend",
		"Purchases by Supplier",
	]
	for name in legacy_charts:
		if not frappe.db.exists("Dashboard Chart", name):
			continue
		if frappe.db.get_value("Dashboard Chart", name, "module") != "NeoAqua":
			continue
		if frappe.db.exists("Dashboard Chart Link", {"chart": name}):
			continue
		frappe.delete_doc("Dashboard Chart", name, force=True, ignore_permissions=True)
		removed.append(f"Dashboard Chart: {name}")

	for card in frappe.get_all(
		"Number Card", filters={"module": "NeoAqua"}, fields=["name", "label"]
	):
		if card.label and card.label.startswith("NeoAqua "):
			continue
		if frappe.db.exists("Number Card Link", {"card": card.name}):
			continue
		frappe.delete_doc("Number Card", card.name, force=True, ignore_permissions=True)
		removed.append(f"Number Card: {card.name}")

	frappe.db.commit()
	return removed


@frappe.whitelist()
def reset_demo_transactions():
	"""Developer helper - clears NeoAqua transactional data only."""
	if not frappe.conf.get("developer_mode"):
		frappe.throw("Only available in developer mode.")
	for dt in (
		"Salesman Day Close", "Salesman Check In", "Van Load Request",
		"Van Trip", "Container Ledger Entry", "Water Quality Check",
	):
		frappe.db.delete(dt)
	frappe.db.commit()
	return "NeoAqua transactions cleared"
