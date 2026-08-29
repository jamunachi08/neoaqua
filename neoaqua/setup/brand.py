# Copyright (c) 2026, Neotec Integrated Solutions
"""Brand handling.

The product name a customer sees is a business decision, not something an app
should bake into its source. Everything the seeder creates composes its name
from a single brand string held in NeoAqua Settings:

    "{brand} 600 ml Bottle"  ->  "Neo Aqua 600 ml Bottle"

Item CODES never contain the brand. `FG-BOT-600` stays `FG-BOT-600` whatever the
label says, which is what lets the brand be renamed later without touching a
single transaction, BOM, batch or stock ledger entry.
"""

import re

import frappe
from frappe import _

DEFAULT_BRAND = "Neo Aqua"


# ---------------------------------------------------------------- resolve
def get_brand(company=None):
	"""The brand to use, in order of preference: what the user typed, then the
	company name, then a neutral fallback."""
	brand = frappe.db.get_single_value("NeoAqua Settings", "brand_name")
	if brand:
		return brand.strip()
	if company:
		return frappe.get_cached_value("Company", company, "company_name")
	return DEFAULT_BRAND


def get_brand_code(company=None):
	"""Short code for batch numbering. Derived from the brand when not set:
	'Neo Aqua' -> 'NAQ', 'Crystal Springs Water' -> 'CSW'."""
	code = frappe.db.get_single_value("NeoAqua Settings", "brand_code")
	if code:
		return code.strip().upper()
	return derive_code(get_brand(company))


def derive_code(brand, length=3):
	words = [w for w in re.split(r"\W+", brand or "") if w]
	if not words:
		return "NAQ"
	if len(words) >= length:
		return "".join(w[0] for w in words[:length]).upper()
	if len(words) == 1:
		return words[0][:length].upper()
	# two words: first letter of the first, fill from the second
	head = words[0][0]
	return (head + words[1][: length - 1]).upper()


def set_brand(brand, brand_ar=None, brand_code=None):
	"""Record the brand on Settings and make sure a Brand master exists."""
	brand = (brand or "").strip()
	if not brand:
		frappe.throw(_("Enter a brand name."))

	s = frappe.get_single("NeoAqua Settings")
	s.brand_name = brand
	if brand_ar:
		s.brand_name_ar = brand_ar
	s.brand_code = (brand_code or derive_code(brand)).upper()
	s.flags.ignore_permissions = True
	s.flags.ignore_mandatory = True
	s.save()

	ensure_brand_record(brand)
	frappe.db.commit()
	return {"brand": brand, "brand_code": s.brand_code}


def ensure_brand_record(brand):
	"""ERPNext has a Brand master; use it rather than inventing a parallel one,
	so brand-wise reporting works out of the box."""
	if not brand or frappe.db.exists("Brand", brand):
		return brand
	doc = frappe.new_doc("Brand")
	doc.brand = brand
	doc.flags.ignore_permissions = True
	try:
		doc.insert()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "NeoAqua: could not create Brand")
	return brand


# ---------------------------------------------------------------- rename
# ERPNext denormalises `item_name` into BOM, Work Order and several other
# tables for display. Renaming `tabItem` alone leaves the old name showing
# everywhere it matters most - which is what happened, and why this cascades.
CASCADE = [
	("BOM", "item", ["item_name"]),
	("BOM Item", "item_code", ["item_name", "description"]),
	("BOM Explosion Item", "item_code", ["item_name", "description"]),
	("Work Order", "production_item", ["item_name"]),
	("Work Order Item", "item_code", ["item_name", "description"]),
	("Production Plan Item", "item_code", ["item_name", "description"]),
	("Item Price", "item_code", ["item_name"]),
	("Packed Item", "item_code", ["item_name", "description"]),
	("Website Item", "item_code", ["item_name"]),
]


def descriptors():
	"""item_code -> name template, the authoritative source of a product name."""
	from neoaqua.setup.masters import FG_BOTTLES, FG_PACKS

	out = {}
	for row in FG_BOTTLES:
		out[row[0]] = row[1]
	for row in FG_PACKS:
		out[row[0]] = row[1]
	return out


def detect_current_brand():
	"""Work out the brand actually in use by reading an item name and removing
	the descriptor, rather than trusting what Settings claims.

	Settings can be wrong - a site seeded under one brand and later backfilled
	will disagree with its own item master. The item names are the truth."""
	for code, template in descriptors().items():
		name = frappe.db.get_value("Item", code, "item_name")
		if not name:
			continue
		suffix = template.replace("{brand}", "").strip()
		if suffix and name.endswith(suffix):
			candidate = name[: -len(suffix)].strip()
			if candidate:
				return candidate
	return None


@frappe.whitelist()
def rename_brand(new_brand, new_brand_ar=None, new_brand_code=None):
	"""Change the brand everywhere it is displayed.

	Names are REBUILT from the product descriptor rather than string-replaced.
	A replace only works when you already know the old brand exactly; rebuilding
	is correct even when the stored brand is stale, was never set, or half the
	catalogue was renamed by hand.

	Item codes, BOM structure, batches, stock and posted transactions are
	untouched. Historical invoices deliberately keep the name they were issued
	under - reprinting an old invoice with a new brand would misrepresent what
	the customer actually received.
	"""
	new_brand = (new_brand or "").strip()
	if not new_brand:
		frappe.throw(_("Enter the new brand name."))

	old_brand = detect_current_brand() or get_brand()
	old_code = get_brand_code()
	new_code = (new_brand_code or derive_code(new_brand)).upper()

	ensure_brand_record(new_brand)
	templates = descriptors()

	renamed, cascaded = [], 0
	for code, template in templates.items():
		if not frappe.db.exists("Item", code):
			continue
		new_name = template.format(brand=new_brand)
		current = frappe.db.get_value("Item", code, ["item_name", "description"], as_dict=True)
		values = {"item_name": new_name, "brand": new_brand}

		if current.description and old_brand and old_brand in current.description:
			values["description"] = current.description.replace(old_brand, new_brand)

		frappe.db.set_value("Item", code, values, update_modified=False)
		renamed.append(code)

		# push the new name into every table that caches it
		for doctype, key, fields in CASCADE:
			table = f"tab{doctype}"
			if not frappe.db.table_exists(table):
				continue
			try:
				sets = ["item_name = %(name)s"]
				params = {"name": new_name, "code": code}
				if "description" in fields and old_brand:
					sets.append("description = replace(description, %(old)s, %(new)s)")
					params.update({"old": old_brand, "new": new_brand})
				frappe.db.sql(
					f"update `{table}` set {', '.join(sets)} where {key} = %(code)s", params
				)
				cascaded += 1
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"NeoAqua rename: {doctype}")

	# batch naming rules carry the brand short code as literal text
	rules_touched = []
	if old_code and old_code != new_code:
		for seg in frappe.get_all(
			"Batch Naming Segment",
			filters={"segment_type": "Fixed Text"},
			fields=["name", "parent", "fixed_text"],
		):
			if seg.fixed_text and old_code in seg.fixed_text:
				frappe.db.set_value(
					"Batch Naming Segment", seg.name, "fixed_text",
					seg.fixed_text.replace(old_code, new_code), update_modified=False,
				)
				rules_touched.append(seg.parent)

	set_brand(new_brand, new_brand_ar, new_code)
	frappe.clear_cache()
	frappe.db.commit()

	return {
		"old_brand": old_brand,
		"new_brand": new_brand,
		"old_code": old_code,
		"new_code": new_code,
		"items_renamed": len(renamed),
		"tables_cascaded": cascaded,
		"batch_rules_updated": sorted(set(rules_touched)),
		"message": _(
			"Renamed {0} items from {1} to {2}, refreshed {3} linked records, "
			"and updated the batch prefix from {4} to {5}. Item codes and posted "
			"transactions are unchanged."
		).format(len(renamed), old_brand or _("(none)"), new_brand, cascaded, old_code, new_code),
	}


@frappe.whitelist()
def resync_brand_names(brand=None):
	"""Rebuild every product name from its descriptor and push it into the
	tables that cache it — without changing the brand.

	This is the repair for a site that was renamed before the cascade existed:
	`tabItem` says "Neo Aqua 5 L Bottle" while the BOM still shows the old
	"Nova Water 5 L Bottle" it copied at creation time.
	"""
	brand = (brand or get_brand()).strip()
	ensure_brand_record(brand)

	fixed, cascaded = [], 0
	for code, template in descriptors().items():
		if not frappe.db.exists("Item", code):
			continue
		correct = template.format(brand=brand)
		current = frappe.db.get_value("Item", code, "item_name")

		if current != correct:
			frappe.db.set_value("Item", code, {"item_name": correct, "brand": brand},
			                    update_modified=False)
			fixed.append({"item": code, "was": current, "now": correct})
		else:
			frappe.db.set_value("Item", code, "brand", brand, update_modified=False)

		for doctype, key, _fields in CASCADE:
			table = f"tab{doctype}"
			if not frappe.db.table_exists(table):
				continue
			try:
				stale = frappe.db.sql(
					f"""select count(*) from `{table}`
					    where `{key}` = %(code)s and ifnull(item_name, '') != %(name)s""",
					{"code": code, "name": correct},
				)[0][0]
				if stale:
					frappe.db.sql(
						f"update `{table}` set item_name = %(name)s where `{key}` = %(code)s",
						{"code": code, "name": correct},
					)
					cascaded += stale
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"NeoAqua resync: {doctype}")

	frappe.clear_cache()
	frappe.db.commit()
	return {
		"brand": brand,
		"items_corrected": len(fixed),
		"rows_refreshed": cascaded,
		"details": fixed[:20],
		"message": _("Rebuilt {0} product name(s) and refreshed {1} cached row(s) in BOMs, "
		             "work orders and price lists.").format(len(fixed), cascaded),
	}


@frappe.whitelist()
def brand_audit():
	"""Where does the old brand still appear? Run this after a rename to prove
	nothing was missed."""
	brand = detect_current_brand() or get_brand()
	findings = []

	for code, template in descriptors().items():
		name = frappe.db.get_value("Item", code, "item_name")
		expected = template.format(brand=brand)
		if name and name != expected:
			findings.append({"where": "Item", "record": code, "found": name, "expected": expected})

	for doctype, key, fields in CASCADE:
		table = f"tab{doctype}"
		if not frappe.db.table_exists(table):
			continue
		try:
			rows = frappe.db.sql(
				f"""select `{key}` as code, item_name from `{table}`
				    where `{key}` like 'FG-%%' and item_name is not null
				    group by `{key}`, item_name""",
				as_dict=True,
			)
		except Exception:
			continue
		for r in rows:
			template = descriptors().get(r.code)
			if not template:
				continue
			expected = template.format(brand=brand)
			if r.item_name != expected:
				findings.append(
					{"where": doctype, "record": r.code, "found": r.item_name, "expected": expected}
				)

	return {"brand": brand, "brand_code": get_brand_code(), "stale": findings, "clean": not findings}


@frappe.whitelist()
def preview_brand(brand):
	"""Show what the item master will be called before committing to it."""
	from neoaqua.setup.masters import FG_BOTTLES, FG_PACKS

	brand = (brand or "").strip() or DEFAULT_BRAND
	sample = [
		{"item_code": r[0], "item_name": r[1].format(brand=brand)}
		for r in list(FG_BOTTLES)[:3] + list(FG_PACKS)[:2]
	]
	return {"brand": brand, "brand_code": derive_code(brand), "sample": sample}
