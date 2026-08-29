# Copyright (c) 2026, Neotec Integrated Solutions
"""Idempotent master-data seeder for a Saudi bottled-water plant.

Everything here is safe to run repeatedly - each helper checks for existence
before inserting, so `bench --site <site> migrate` can re-run the seeder after
every deployment without duplicating records.

Pack configurations and preform weights follow what is actually sold in the
KSA market (200 ml, 330 ml, 600 ml, 1.5 L, 5 L and the 18.9 L / 5-gallon
returnable used for home and office delivery).
"""

import frappe
from frappe.utils import flt

# ---------------------------------------------------------------- reference data

UOMS = [
	("Bottle", 1), ("Case", 1), ("Shrink Pack", 1), ("Pallet", 1),
	("Preform", 1), ("Roll", 1), ("Litre", 1), ("Kg", 1), ("Gram", 1),
]

ITEM_GROUPS = [
	("Water & Packaging RM", "Raw Material", 1),
	("Water Source", "Water & Packaging RM", 0),
	("Preforms & Closures", "Water & Packaging RM", 0),
	("Labels & Secondary Packaging", "Water & Packaging RM", 0),
	("Treatment Chemicals", "Water & Packaging RM", 0),
	("Water WIP", "Sub Assemblies", 1),
	("Treated Water", "Water WIP", 0),
	("Blown Bottles", "Water WIP", 0),
	("Bottled Water - Small PET", "Products", 0),
	("Bottled Water - Large PET", "Products", 0),
	("Bottled Water - 5 Gallon", "Products", 0),
	("Returnable Containers", "Products", 0),
]

WAREHOUSES = [
	("Raw Material Store", "All Warehouses", 1),
	("Preform Store", "Raw Material Store", 0),
	("Chemical Store", "Raw Material Store", 0),
	("Packaging Store", "Raw Material Store", 0),
	("Work In Progress", "All Warehouses", 1),
	("RO Plant", "Work In Progress", 0),
	("Blow Moulding WIP", "Work In Progress", 0),
	("Filling WIP", "Work In Progress", 0),
	("Finished Goods Store", "All Warehouses", 0),
	("QC Quarantine", "All Warehouses", 0),
	("Scrap & Rejection", "All Warehouses", 0),
	("Empty Container Yard", "All Warehouses", 0),
	("Vans", "All Warehouses", 1),
	("Van 01 - Riyadh North", "Vans", 0),
	("Van 02 - Riyadh South", "Vans", 0),
	("Van 03 - Riyadh East", "Vans", 0),
]

# code, name, group, uom, is_stock, valuation, purchase_rate, extra
RAW_MATERIALS = [
	("RM-WTR-SRC", "Raw Source Water (Well / Municipal)", "Water Source", "Litre", 0.004, 0.004),
	("RM-PRF-09G", "PET Preform 9 g - 28 mm PCO 1810", "Preforms & Closures", "Nos", 0.155, 0.155),
	("RM-PRF-11G", "PET Preform 11 g - 28 mm PCO 1810", "Preforms & Closures", "Nos", 0.185, 0.185),
	("RM-PRF-14G", "PET Preform 14 g - 28 mm PCO 1810", "Preforms & Closures", "Nos", 0.235, 0.235),
	("RM-PRF-28G", "PET Preform 28 g - 28 mm PCO 1810", "Preforms & Closures", "Nos", 0.460, 0.460),
	("RM-PRF-60G", "PET Preform 60 g - 30 mm Handle Neck", "Preforms & Closures", "Nos", 0.980, 0.980),
	("RM-CAP-28", "Closure 28 mm PCO 1810 - Blue", "Preforms & Closures", "Nos", 0.045, 0.045),
	("RM-CAP-30", "Closure 30 mm - 5 L", "Preforms & Closures", "Nos", 0.075, 0.075),
	("RM-CAP-55", "Cap & Tamper Seal 55 mm - 18.9 L", "Preforms & Closures", "Nos", 0.320, 0.320),
	("RM-HDL-5L", "Snap Handle - 5 L", "Preforms & Closures", "Nos", 0.110, 0.110),
	("RM-LBL-200", "BOPP Wrap Label - 200 ml", "Labels & Secondary Packaging", "Nos", 0.022, 0.022),
	("RM-LBL-330", "BOPP Wrap Label - 330 ml", "Labels & Secondary Packaging", "Nos", 0.026, 0.026),
	("RM-LBL-600", "BOPP Wrap Label - 600 ml", "Labels & Secondary Packaging", "Nos", 0.031, 0.031),
	("RM-LBL-1500", "BOPP Wrap Label - 1.5 L", "Labels & Secondary Packaging", "Nos", 0.048, 0.048),
	("RM-LBL-5000", "BOPP Wrap Label - 5 L", "Labels & Secondary Packaging", "Nos", 0.085, 0.085),
	("RM-LBL-189", "Shoulder Label - 18.9 L", "Labels & Secondary Packaging", "Nos", 0.140, 0.140),
	("RM-SHR-FILM", "LDPE Shrink Film - 50 micron", "Labels & Secondary Packaging", "Kg", 6.400, 6.400),
	("RM-CTN-TRAY", "Corrugated Base Tray", "Labels & Secondary Packaging", "Nos", 0.480, 0.480),
	("RM-STRETCH", "Pallet Stretch Wrap", "Labels & Secondary Packaging", "Kg", 7.200, 7.200),
	("RM-PALLET", "Wooden Pallet 1200x1000", "Labels & Secondary Packaging", "Nos", 32.000, 32.000),
	("RM-CHM-ANTISCAL", "RO Antiscalant", "Treatment Chemicals", "Kg", 24.000, 24.000),
	("RM-CHM-NAOCL", "Sodium Hypochlorite 12%", "Treatment Chemicals", "Litre", 3.200, 3.200),
	("RM-CHM-MINERAL", "Mineral Blend (Ca / Mg / K salts)", "Treatment Chemicals", "Kg", 46.000, 46.000),
	("RM-CHM-CIP", "CIP Caustic & Acid Blend", "Treatment Chemicals", "Litre", 8.500, 8.500),
	("RM-BTL-PC-189", "Polycarbonate Bottle 18.9 L (Returnable)", "Returnable Containers", "Nos", 38.000, 38.000),
]

# code, name, group, uom, valuation
WIP_ITEMS = [
	("WIP-WTR-RO", "RO Permeate Water", "Treated Water", "Litre", 0.030),
	("WIP-WTR-OZ", "Mineralised & Ozonated Water (Filler Ready)", "Treated Water", "Litre", 0.041),
	("WIP-BTL-200", "Blown Empty Bottle 200 ml", "Blown Bottles", "Nos", 0.192),
	("WIP-BTL-330", "Blown Empty Bottle 330 ml", "Blown Bottles", "Nos", 0.224),
	("WIP-BTL-600", "Blown Empty Bottle 600 ml", "Blown Bottles", "Nos", 0.278),
	("WIP-BTL-1500", "Blown Empty Bottle 1.5 L", "Blown Bottles", "Nos", 0.516),
	("WIP-BTL-5000", "Blown Empty Bottle 5 L", "Blown Bottles", "Nos", 1.070),
]

# code, NAME TEMPLATE, group, uom, volume_ml, valuation, retail, wholesale, shelf_life
# The name carries a {brand} token filled in at creation time - the brand is a
# business decision held in NeoAqua Settings, never baked into the source.
FG_BOTTLES = [
	("FG-BOT-200", "{brand} 200 ml Bottle", "Bottled Water - Small PET", "Nos", 200, 0.255, 0.75, 0.52, 365),
	("FG-BOT-330", "{brand} 330 ml Bottle", "Bottled Water - Small PET", "Nos", 330, 0.305, 1.00, 0.68, 365),
	("FG-BOT-600", "{brand} 600 ml Bottle", "Bottled Water - Small PET", "Nos", 600, 0.379, 1.50, 0.95, 365),
	("FG-BOT-1500", "{brand} 1.5 L Bottle", "Bottled Water - Large PET", "Nos", 1500, 0.665, 2.50, 1.65, 365),
	("FG-BOT-5000", "{brand} 5 L Bottle", "Bottled Water - Large PET", "Nos", 5000, 1.470, 5.00, 3.40, 365),
	("FG-BOT-18900", "{brand} 18.9 L (5 Gallon) Refill", "Bottled Water - 5 Gallon", "Nos", 18900, 1.320, 12.00, 8.50, 180),
]

# pack_code, name, group, fg_item, bottles, film_kg, tray, retail, wholesale
FG_PACKS = [
	("FG-PCK-200-48", "{brand} 200 ml x 48 Shrink Pack", "Bottled Water - Small PET", "FG-BOT-200", 48, 0.052, 1, 30.00, 22.00),
	("FG-PCK-330-40", "{brand} 330 ml x 40 Shrink Pack", "Bottled Water - Small PET", "FG-BOT-330", 40, 0.055, 1, 34.00, 25.00),
	("FG-PCK-600-24", "{brand} 600 ml x 24 Shrink Pack", "Bottled Water - Small PET", "FG-BOT-600", 24, 0.048, 1, 30.00, 21.00),
	("FG-PCK-600-12", "{brand} 600 ml x 12 Shrink Pack", "Bottled Water - Small PET", "FG-BOT-600", 12, 0.030, 0, 16.00, 11.50),
	("FG-PCK-1500-06", "{brand} 1.5 L x 6 Shrink Pack", "Bottled Water - Large PET", "FG-BOT-1500", 6, 0.038, 0, 13.00, 9.50),
	("FG-PCK-5000-04", "{brand} 5 L x 4 Shrink Pack", "Bottled Water - Large PET", "FG-BOT-5000", 4, 0.055, 0, 19.00, 13.50),
]

WORKSTATIONS = [
	("RO Treatment Plant", 180.0, 3, 55),
	("Ozonation & Storage", 90.0, 1, 12),
	("Blow Moulding Line 1", 240.0, 2, 96),
	("Blow Moulding Line 2", 260.0, 2, 110),
	("Filling Line 1 - Small PET", 320.0, 6, 132),
	("Filling Line 2 - Large PET", 280.0, 5, 88),
	("Filling Line 3 - 5 Gallon", 210.0, 4, 45),
	("Shrink Wrapping Station", 150.0, 3, 24),
	("Palletising & Coding", 120.0, 2, 18),
]

OPERATIONS = [
	("Reverse Osmosis Treatment", "RO Treatment Plant"),
	("Mineralisation & Ozonation", "Ozonation & Storage"),
	("Preform Blowing", "Blow Moulding Line 1"),
	("Bottle Rinse Fill Cap", "Filling Line 1 - Small PET"),
	("Bottle Rinse Fill Cap - Large", "Filling Line 2 - Large PET"),
	("Container Wash & Fill - 5 Gallon", "Filling Line 3 - 5 Gallon"),
	("Sleeve Labelling & Coding", "Filling Line 1 - Small PET"),
	("Shrink Wrapping", "Shrink Wrapping Station"),
	("Palletising & Batch Coding", "Palletising & Coding"),
]

CUSTOMER_GROUPS = [
	"Wholesale Distributor", "Retail Baqala", "Supermarket Chain",
	"HORECA", "Home & Office Delivery", "Government & Institutional",
]

TERRITORIES = [
	("Riyadh Region", "All Territories", 1),
	("Riyadh - North", "Riyadh Region", 0),
	("Riyadh - South", "Riyadh Region", 0),
	("Riyadh - East", "Riyadh Region", 0),
	("Riyadh - West", "Riyadh Region", 0),
	("Qassim", "All Territories", 0),
	("Eastern Province", "All Territories", 0),
]

PRICE_LISTS = [
	("NeoAqua Retail", "Selling"),
	("NeoAqua Wholesale", "Selling"),
	("NeoAqua HORECA", "Selling"),
	("NeoAqua Purchase", "Buying"),
]

MODES_OF_PAYMENT = ["Cash", "Mada", "STC Pay", "Bank Transfer", "Credit"]


# ---------------------------------------------------------------- helpers
def _insert(doctype, name_field, values, name=None):
	"""Insert a doc only when it does not already exist."""
	key = name or values.get(name_field)
	if frappe.db.exists(doctype, key):
		return key
	doc = frappe.new_doc(doctype)
	doc.update(values)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert()
	return doc.name


def abbr(company):
	return frappe.get_cached_value("Company", company, "abbr")


# ---------------------------------------------------------------- seeders
def create_uoms():
	for uom, whole in UOMS:
		_insert("UOM", "uom_name", {"uom_name": uom, "must_be_whole_number": whole}, name=uom)


def create_item_groups():
	for name, parent, is_group in ITEM_GROUPS:
		if not frappe.db.exists("Item Group", parent):
			parent = "All Item Groups"
		_insert(
			"Item Group", "item_group_name",
			{"item_group_name": name, "parent_item_group": parent, "is_group": is_group},
			name=name,
		)


def create_warehouses(company):
	a = abbr(company)
	created = {}
	for name, parent, is_group in WAREHOUSES:
		parent_name = f"{parent} - {a}" if parent != "All Warehouses" else f"All Warehouses - {a}"
		if not frappe.db.exists("Warehouse", parent_name):
			parent_name = f"All Warehouses - {a}"
		full = f"{name} - {a}"
		created[name] = _insert(
			"Warehouse", "warehouse_name",
			{
				"warehouse_name": name,
				"parent_warehouse": parent_name,
				"is_group": is_group,
				"company": company,
			},
			name=full,
		)
	return created


def create_territories():
	for name, parent, is_group in TERRITORIES:
		_insert(
			"Territory", "territory_name",
			{"territory_name": name, "parent_territory": parent, "is_group": is_group},
			name=name,
		)


def create_customer_groups():
	for name in CUSTOMER_GROUPS:
		_insert(
			"Customer Group", "customer_group_name",
			{"customer_group_name": name, "parent_customer_group": "All Customer Groups"},
			name=name,
		)


def create_price_lists(company):
	for name, ptype in PRICE_LISTS:
		_insert(
			"Price List", "price_list_name",
			{
				"price_list_name": name,
				"currency": "SAR",
				"buying": 1 if ptype == "Buying" else 0,
				"selling": 1 if ptype == "Selling" else 0,
				"enabled": 1,
			},
			name=name,
		)


def create_modes_of_payment(company):
	a = abbr(company)
	cash = frappe.db.get_value("Account", {"company": company, "account_type": "Cash", "is_group": 0}, "name")
	bank = frappe.db.get_value("Account", {"company": company, "account_type": "Bank", "is_group": 0}, "name")
	for mop in MODES_OF_PAYMENT:
		if frappe.db.exists("Mode of Payment", mop):
			continue
		doc = frappe.new_doc("Mode of Payment")
		doc.mode_of_payment = mop
		doc.type = "Cash" if mop == "Cash" else ("General" if mop == "Credit" else "Bank")
		account = cash if mop == "Cash" else bank
		if account:
			doc.append("accounts", {"company": company, "default_account": account})
		doc.flags.ignore_permissions = True
		doc.insert()


# ---------------------------------------------------------------- items
def _item(code, name, group, uom, valuation, is_stock=1, has_batch=0, shelf_life=0,
          purchase_rate=0, extra=None):
	if frappe.db.exists("Item", code):
		return code
	doc = frappe.new_doc("Item")
	doc.update(
		{
			"item_code": code,
			"item_name": name,
			"item_group": group if frappe.db.exists("Item Group", group) else "All Item Groups",
			"stock_uom": uom,
			"is_stock_item": is_stock,
			"has_batch_no": has_batch,
			"create_new_batch": has_batch,
			# fallback only - the Batch Naming Rule engine composes the code when a
		# rule matches, and this series is used when none does.
		"batch_number_series": f"{code}-.YY..MM..DD.-.###" if has_batch else None,
			"shelf_life_in_days": shelf_life or 0,
			"valuation_rate": valuation,
			"include_item_in_manufacturing": 1,
			"is_purchase_item": 1 if purchase_rate else 0,
			"is_sales_item": 1 if group.startswith("Bottled Water") else 0,
		}
	)
	if extra:
		doc.update(extra)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert()
	return doc.name


def create_items(company):
	"""Create the whole item master.

	Each item is created independently: one bad row must not cost the other
	forty-three. Failures are collected and returned so the setup report can
	name them instead of the stage dying on the first exception.
	"""
	from neoaqua.setup.brand import ensure_brand_record, get_brand

	brand = get_brand(company)
	ensure_brand_record(brand)

	failures = []

	def guard(label, fn, *args, **kwargs):
		try:
			fn(*args, **kwargs)
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), f"NeoAqua item setup: {label}")
			failures.append(f"{label}: {str(e)[:160]}")

	a = abbr(company)
	rm_wh = f"Raw Material Store - {a}"
	fg_wh = f"Finished Goods Store - {a}"
	wip_wh = f"Work In Progress - {a}"

	# --- raw materials
	for code, name, group, uom, valuation, purchase_rate in RAW_MATERIALS:
		food_contact = 1 if group in ("Preforms & Closures", "Labels & Secondary Packaging", "Returnable Containers") else 0
		guard(code, _item,
			code, name, group, uom, valuation,
			purchase_rate=purchase_rate,
			extra={
				"neoaqua_food_contact": food_contact,
				"neoaqua_is_returnable": 1 if code == "RM-BTL-PC-189" else 0,
				"is_sub_contracted_item": 0,
				"default_material_request_type": "Purchase",
			},
		)
		kind = "container" if code == "RM-BTL-PC-189" else "rm"
		guard(code, _set_item_defaults, code, rm_wh, company, kind=kind)
		guard(code, _item_price, code, "NeoAqua Purchase", purchase_rate, buying=1)

	# --- work in progress
	for code, name, group, uom, valuation in WIP_ITEMS:
		guard(code, _item,
			code, name, group, uom, valuation,
			extra={
				"is_purchase_item": 0,
				"default_material_request_type": "Manufacture",
				"neoaqua_requires_qc": 1 if code.startswith("WIP-WTR") else 0,
			},
		)
		guard(code, _set_item_defaults, code, wip_wh, company, kind="wip")

	# --- finished bottles
	for code, template, group, uom, volume, valuation, retail, wholesale, shelf in FG_BOTTLES:
		name = template.format(brand=brand)
		guard(code, _item,
			code, name, group, uom, valuation,
			has_batch=1, shelf_life=shelf,
			extra={
				"brand": brand,
				"is_sales_item": 1,
				"is_purchase_item": 0,
				"default_material_request_type": "Manufacture",
				"neoaqua_requires_qc": 1,
				"neoaqua_fill_volume_ml": volume,
				"neoaqua_is_returnable": 1 if code == "FG-BOT-18900" else 0,
			},
		)
		guard(code, _set_item_defaults, code, fg_wh, company, kind="fg")
		guard(code, _item_price, code, "NeoAqua Retail", retail)
		guard(code, _item_price, code, "NeoAqua Wholesale", wholesale)
		guard(code, _item_price, code, "NeoAqua HORECA", round(wholesale * 1.12, 3))

	# --- packs
	for code, template, group, fg_item, bottles, film, tray, retail, wholesale in FG_PACKS:
		name = template.format(brand=brand)
		volume = next(f[4] for f in FG_BOTTLES if f[0] == fg_item) * bottles
		valuation = next(f[5] for f in FG_BOTTLES if f[0] == fg_item) * bottles + film * 6.4
		guard(code, _item,
			code, name, group, "Nos", round(valuation, 3),
			has_batch=1, shelf_life=365,
			extra={
				"brand": brand,
				"is_sales_item": 1,
				"is_purchase_item": 0,
				"default_material_request_type": "Manufacture",
				"neoaqua_requires_qc": 1,
				"neoaqua_bottles_per_pack": bottles,
				"neoaqua_fill_volume_ml": volume,
			},
		)
		guard(code, _set_item_defaults, code, fg_wh, company, kind="fg")
		guard(code, _item_price, code, "NeoAqua Retail", retail)
		guard(code, _item_price, code, "NeoAqua Wholesale", wholesale)
		guard(code, _item_price, code, "NeoAqua HORECA", round(wholesale * 1.10, 3))
		guard(code, _uom_conversion, code, "Case", 1)

	return failures


def _account(company, account_name):
	return frappe.db.get_value(
		"Account", {"company": company, "account_name": account_name, "is_group": 0}, "name"
	)


def _cost_center(company, name):
	return frappe.db.get_value("Cost Center", {"company": company, "cost_center_name": name}, "name")


def _set_item_defaults(item_code, warehouse, company, kind="rm", supplier=None):
	"""Give every item a complete Item Default row: warehouse, income account,
	expense account and cost centers.

	Without this an invoice cannot post - ERPNext falls back to the company
	default income account, and if that is unset the user gets a mandatory
	field error on their first sale. This is the difference between an app
	that installs and an app that can transact.
	"""
	item = frappe.get_doc("Item", item_code)
	row = next((d for d in item.item_defaults if d.company == company), None)

	values = {"company": company}
	if frappe.db.exists("Warehouse", warehouse):
		values["default_warehouse"] = warehouse

	if kind == "fg":
		values["income_account"] = _account(company, "Sale of Bottled Water")
		values["expense_account"] = _account(company, "Cost of Bottled Water Sold")
		values["selling_cost_center"] = _cost_center(company, "Distribution")
		values["buying_cost_center"] = _cost_center(company, "Administration")
	elif kind == "wip":
		values["expense_account"] = _account(company, "Cost of Bottled Water Sold")
		values["buying_cost_center"] = _cost_center(company, "Production")
		values["selling_cost_center"] = _cost_center(company, "Production")
	elif kind == "container":
		values["income_account"] = _account(company, "Container Forfeiture Income")
		values["expense_account"] = _account(company, "Cost of Bottled Water Sold")
		values["selling_cost_center"] = _cost_center(company, "Distribution")
		values["buying_cost_center"] = _cost_center(company, "Administration")
	else:  # raw material
		values["expense_account"] = _account(company, "Cost of Bottled Water Sold")
		values["buying_cost_center"] = _cost_center(company, "Administration")
		values["selling_cost_center"] = _cost_center(company, "Administration")

	if supplier and frappe.db.exists("Supplier", supplier):
		values["default_supplier"] = supplier

	values = {k: v for k, v in values.items() if v}

	if row:
		for k, v in values.items():
			if not row.get(k):
				row.set(k, v)
	else:
		item.append("item_defaults", values)

	item.flags.ignore_permissions = True
	item.flags.ignore_mandatory = True
	item.save()


# retained for callers that only need the warehouse
def _set_default_warehouse(item_code, warehouse, company):
	_set_item_defaults(item_code, warehouse, company, kind="rm")


def _uom_conversion(item_code, uom, factor):
	item = frappe.get_doc("Item", item_code)
	if any(d.uom == uom for d in item.uoms):
		return
	item.append("uoms", {"uom": uom, "conversion_factor": factor})
	item.flags.ignore_permissions = True
	item.save()


def _item_price(item_code, price_list, rate, buying=0):
	if not rate or not frappe.db.exists("Price List", price_list):
		return
	if frappe.db.exists("Item Price", {"item_code": item_code, "price_list": price_list}):
		return
	doc = frappe.new_doc("Item Price")
	doc.update(
		{
			"item_code": item_code,
			"price_list": price_list,
			"price_list_rate": flt(rate),
			"currency": "SAR",
			"buying": buying,
			"selling": 0 if buying else 1,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()


# ---------------------------------------------------------------- manufacturing
def create_workstations(company):
	for name, hour_rate, workers, capacity in WORKSTATIONS:
		if frappe.db.exists("Workstation", name):
			continue
		doc = frappe.new_doc("Workstation")
		doc.update(
			{
				"workstation_name": name,
				"hour_rate_electricity": round(hour_rate * 0.35, 2),
				"hour_rate_consumable": round(hour_rate * 0.15, 2),
				"hour_rate_labour": round(hour_rate * 0.40, 2),
				"hour_rate_rent": round(hour_rate * 0.10, 2),
				"production_capacity": capacity,
			}
		)
		for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"):
			doc.append("working_hours", {"start_time": "06:00:00", "end_time": "22:00:00", "enabled": 1})
			break
		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		doc.insert()


def create_operations():
	for name, workstation in OPERATIONS:
		_insert(
			"Operation", "name",
			{"name": name, "workstation": workstation, "description": name},
			name=name,
		)


# ---------------------------------------------------------------- tax
def create_tax_templates(company):
	a = abbr(company)
	vat_account = frappe.db.get_value(
		"Account", {"company": company, "account_name": ["like", "%VAT%"], "is_group": 0}, "name"
	)
	if not vat_account:
		parent = frappe.db.get_value(
			"Account", {"company": company, "account_name": "Duties and Taxes", "is_group": 1}, "name"
		)
		if parent:
			acc = frappe.new_doc("Account")
			acc.update(
				{
					"account_name": "VAT 15% Output",
					"parent_account": parent,
					"company": company,
					"account_type": "Tax",
					"tax_rate": 15,
				}
			)
			acc.flags.ignore_permissions = True
			acc.insert()
			vat_account = acc.name
	if not vat_account:
		return

	name = f"KSA VAT 15% - {a}"
	if not frappe.db.exists("Sales Taxes and Charges Template", name):
		doc = frappe.new_doc("Sales Taxes and Charges Template")
		doc.title = "KSA VAT 15%"
		doc.company = company
		doc.is_default = 1
		doc.append(
			"taxes",
			{
				"charge_type": "On Net Total",
				"account_head": vat_account,
				"description": "VAT @ 15%",
				"rate": 15,
			},
		)
		doc.flags.ignore_permissions = True
		doc.insert()

	itt = "KSA VAT 15%"
	if not frappe.db.exists("Item Tax Template", f"{itt} - {a}"):
		doc = frappe.new_doc("Item Tax Template")
		doc.title = itt
		doc.company = company
		doc.append("taxes", {"tax_type": vat_account, "tax_rate": 15})
		doc.flags.ignore_permissions = True
		doc.insert()


# ---------------------------------------------------------------- pos & vans
def create_pos_profiles(company):
	a = abbr(company)
	for idx, wh in enumerate(("Van 01 - Riyadh North", "Van 02 - Riyadh South", "Van 03 - Riyadh East"), start=1):
		name = f"Van POS {idx:02d}"
		warehouse = f"{wh} - {a}"
		if frappe.db.exists("POS Profile", name) or not frappe.db.exists("Warehouse", warehouse):
			continue
		doc = frappe.new_doc("POS Profile")
		doc.update(
			{
				"name": name,
				"company": company,
				"warehouse": warehouse,
				"selling_price_list": "NeoAqua Retail",
				"currency": "SAR",
				"disable_rounded_total": 1,
				"allow_negative_stock": 0,
				"update_stock": 1,
				"hide_unavailable_items": 1,
				"print_format": "NeoAqua Van Receipt 80mm"
				if frappe.db.exists("Print Format", "NeoAqua Van Receipt 80mm")
				else None,
			}
		)
		for mop in ("Cash", "Mada"):
			if frappe.db.exists("Mode of Payment", mop):
				doc.append("payments", {"mode_of_payment": mop, "default": 1 if mop == "Cash" else 0})
		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		doc.insert()


def create_vans_and_routes(company):
	a = abbr(company)
	vans = [
		("Van 01", "RUH-1234-ABC", "Van 01 - Riyadh North", "Riyadh - North"),
		("Van 02", "RUH-5678-DEF", "Van 02 - Riyadh South", "Riyadh - South"),
		("Van 03", "RUH-9012-GHI", "Van 03 - Riyadh East", "Riyadh - East"),
	]
	for name, plate, wh, territory in vans:
		route_name = f"{territory} Route"
		if not frappe.db.exists("Van Route", route_name):
			r = frappe.new_doc("Van Route")
			r.update(
				{
					"route_name": route_name,
					"company": company,
					"territory": territory if frappe.db.exists("Territory", territory) else None,
					"city": "Riyadh",
					"is_active": 1,
				}
			)
			r.flags.ignore_permissions = True
			r.insert()
		if frappe.db.exists("Van", name):
			continue
		v = frappe.new_doc("Van")
		v.update(
			{
				"van_name": name,
				"plate_number": plate,
				"company": company,
				"status": "Active",
				"warehouse": f"{wh} - {a}",
				"default_route": route_name,
				"max_cases": 320,
				"max_weight_kg": 3500,
			}
		)
		v.flags.ignore_permissions = True
		v.flags.ignore_mandatory = True
		v.insert()


# ---------------------------------------------------------------- settings
def configure_settings(company):
	a = abbr(company)
	s = frappe.get_single("NeoAqua Settings")
	s.company = company
	s.default_plant_warehouse = _wh(f"Finished Goods Store - {a}")
	s.rm_warehouse = _wh(f"Raw Material Store - {a}")
	s.scrap_warehouse = _wh(f"Scrap & Rejection - {a}")
	s.van_parent_warehouse = _wh(f"Vans - {a}")
	s.auto_create_load_stock_entry = 1
	s.require_day_close = 1
	s.cash_variance_tolerance = 25
	s.enable_geofencing = 1
	s.default_geofence_radius = 150
	s.geofence_enforcement = "Warn Only"
	s.track_containers = 1
	s.container_item = "RM-BTL-PC-189" if frappe.db.exists("Item", "RM-BTL-PC-189") else None
	s.container_deposit_amount = 50
	s.enforce_qc_before_fg_transfer = 1
	s.default_batch_shelf_life_days = 365
	s.cash_account = frappe.db.get_value(
		"Account", {"company": company, "account_type": "Cash", "is_group": 0}, "name"
	)
	s.flags.ignore_permissions = True
	s.save()


def _wh(name):
	return name if frappe.db.exists("Warehouse", name) else None


# ---------------------------------------------------------------- entry point
def run(company=None):
	company = company or frappe.defaults.get_global_default("company")
	if not company:
		frappe.throw("Create a Company before running the NeoAqua seeder.")

	create_uoms()
	create_item_groups()
	create_warehouses(company)
	create_territories()
	create_customer_groups()
	create_price_lists(company)
	create_modes_of_payment(company)
	create_items(company)
	create_workstations(company)
	create_operations()
	create_tax_templates(company)
	create_pos_profiles(company)
	create_vans_and_routes(company)
	configure_settings(company)
	frappe.db.commit()
	return f"NeoAqua masters seeded for {company}"
