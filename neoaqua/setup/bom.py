# Copyright (c) 2026, Neotec Integrated Solutions
"""Multi-level BOM and routing builder.

The chain is five levels deep for a small PET bottle, which is what a real
bottling plant costs against:

    L5  RO Permeate Water           <- source water + antiscalant + hypochlorite
    L4  Mineralised/Ozonated Water  <- RO permeate + mineral blend
    L3  Blown Empty Bottle          <- PET preform
    L2  Filled & Labelled Bottle    <- blown bottle + water + closure + label
    L1  Shrink Pack / Case          <- n x bottles + shrink film (+ tray)

The 18.9 L (5-gallon) line skips blow moulding: the polycarbonate bottle is a
returnable asset that is washed and refilled, so its BOM consumes the washed
container rather than a preform.

BOMs are created bottom-up so that every sub-assembly already has an active
BOM by the time its parent is built - otherwise ERPNext cannot resolve the
exploded item list or roll up the cost.
"""

import frappe
from frappe.utils import flt

# ---------------------------------------------------------------- yields
RO_RECOVERY = 0.74          # 74% permeate recovery, 26% reject to drain
FILLING_YIELD = 0.985       # 1.5% rejects at filler / labeller
BLOWING_YIELD = 0.985       # preform + blowing scrap
PACKING_YIELD = 0.998

# ---------------------------------------------------------------- definitions
# (fg_item, qty, [(rm_item, qty_per_unit, is_scrap)], [(operation, minutes)], warehouse_key)

def _rm(item, qty):
	return {"item_code": item, "qty": qty}


LEVEL_5 = [
	{
		"item": "WIP-WTR-RO",
		"qty": 1000,  # produce 1000 L of permeate
		"items": [
			_rm("RM-WTR-SRC", 1000 / RO_RECOVERY),
			_rm("RM-CHM-ANTISCAL", 0.0035),
			_rm("RM-CHM-NAOCL", 0.0120),
		],
		"operations": [("Reverse Osmosis Treatment", 42)],
		"routing": "RO Treatment",
		"scrap": [],
	}
]

LEVEL_4 = [
	{
		"item": "WIP-WTR-OZ",
		"qty": 1000,
		"items": [
			_rm("WIP-WTR-RO", 1002),
			_rm("RM-CHM-MINERAL", 0.120),
		],
		"operations": [("Mineralisation & Ozonation", 18)],
		"routing": "Mineralisation & Ozonation",
		"scrap": [],
	}
]

# blown bottles: (wip_item, preform, qty_per_batch, minutes)
LEVEL_3 = [
	("WIP-BTL-200", "RM-PRF-09G", 10000, 62),
	("WIP-BTL-330", "RM-PRF-11G", 10000, 66),
	("WIP-BTL-600", "RM-PRF-14G", 10000, 71),
	("WIP-BTL-1500", "RM-PRF-28G", 5000, 58),
	("WIP-BTL-5000", "RM-PRF-60G", 2000, 46),
]

# filled bottles: (fg, blown, volume_l, cap, label, batch_qty, operation, minutes)
LEVEL_2 = [
	("FG-BOT-200", "WIP-BTL-200", 0.200, "RM-CAP-28", "RM-LBL-200", 10000, "Bottle Rinse Fill Cap", 48),
	("FG-BOT-330", "WIP-BTL-330", 0.330, "RM-CAP-28", "RM-LBL-330", 10000, "Bottle Rinse Fill Cap", 50),
	("FG-BOT-600", "WIP-BTL-600", 0.600, "RM-CAP-28", "RM-LBL-600", 10000, "Bottle Rinse Fill Cap", 55),
	("FG-BOT-1500", "WIP-BTL-1500", 1.500, "RM-CAP-28", "RM-LBL-1500", 5000, "Bottle Rinse Fill Cap - Large", 52),
	("FG-BOT-5000", "WIP-BTL-5000", 5.000, "RM-CAP-30", "RM-LBL-5000", 2000, "Bottle Rinse Fill Cap - Large", 64),
]

# packs: (pack_item, bottle_item, bottles, film_kg_per_pack, tray, batch_packs, minutes)
LEVEL_1 = [
	("FG-PCK-200-48", "FG-BOT-200", 48, 0.052, 1, 200, 34),
	("FG-PCK-330-40", "FG-BOT-330", 40, 0.055, 1, 200, 34),
	("FG-PCK-600-24", "FG-BOT-600", 24, 0.048, 1, 400, 42),
	("FG-PCK-600-12", "FG-BOT-600", 12, 0.030, 0, 400, 30),
	("FG-PCK-1500-06", "FG-BOT-1500", 6, 0.038, 0, 400, 28),
	("FG-PCK-5000-04", "FG-BOT-5000", 4, 0.055, 0, 250, 26),
]


# ---------------------------------------------------------------- routing
def create_routing(name, operations):
	"""operations = [(operation_name, minutes)]"""
	if frappe.db.exists("Routing", name):
		return name
	doc = frappe.new_doc("Routing")
	doc.routing_name = name
	for op, minutes in operations:
		if not frappe.db.exists("Operation", op):
			continue
		doc.append(
			"operations",
			{
				"operation": op,
				"workstation": frappe.db.get_value("Operation", op, "workstation"),
				"time_in_mins": minutes,
				"hour_rate": 0,
				"batch_size": 1,
			},
		)
	if not doc.operations:
		return None
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


# ---------------------------------------------------------------- bom
def create_bom(company, item, qty, items, operations=None, scrap=None, routing_name=None,
               currency="SAR"):
	"""Idempotent BOM creation. Returns the BOM name."""
	if not frappe.db.exists("Item", item):
		return None
	existing = frappe.db.get_value(
		"BOM", {"item": item, "is_active": 1, "is_default": 1, "docstatus": 1}, "name"
	)
	if existing:
		return existing

	for row in items:
		if not frappe.db.exists("Item", row["item_code"]):
			return None

	doc = frappe.new_doc("BOM")
	doc.update(
		{
			"item": item,
			"company": company,
			"quantity": qty,
			"currency": currency,
			"is_active": 1,
			"is_default": 1,
			"allow_alternative_item": 1,
			"set_rate_of_sub_assembly_item_based_on_bom": 1,
			"rm_cost_as_per": "Valuation Rate",
			"with_operations": 1 if operations else 0,
			"transfer_material_against": "Work Order",
		}
	)

	if operations:
		routing = create_routing(routing_name or f"{item} Routing", operations)
		if routing:
			doc.routing = routing
			doc.with_operations = 1
			for op, minutes in operations:
				if not frappe.db.exists("Operation", op):
					continue
				doc.append(
					"operations",
					{
						"operation": op,
						"workstation": frappe.db.get_value("Operation", op, "workstation"),
						"time_in_mins": minutes,
						"hour_rate": 0,
					},
				)

	for row in items:
		doc.append(
			"items",
			{
				"item_code": row["item_code"],
				"qty": flt(row["qty"], 6),
				"uom": frappe.db.get_value("Item", row["item_code"], "stock_uom"),
				"rate": flt(frappe.db.get_value("Item", row["item_code"], "valuation_rate")),
			},
		)

	for row in scrap or []:
		doc.append(
			"scrap_items",
			{"item_code": row["item_code"], "stock_qty": flt(row["qty"], 6), "rate": 0},
		)

	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert()
	doc.submit()
	return doc.name


# ---------------------------------------------------------------- build
def build_all(company=None):
	company = company or frappe.defaults.get_global_default("company")
	created = []

	# ---- Level 5: RO permeate
	for spec in LEVEL_5:
		name = create_bom(
			company, spec["item"], spec["qty"], spec["items"],
			operations=spec["operations"], routing_name=spec["routing"],
		)
		if name:
			created.append(name)

	# ---- Level 4: mineralised & ozonated water
	for spec in LEVEL_4:
		name = create_bom(
			company, spec["item"], spec["qty"], spec["items"],
			operations=spec["operations"], routing_name=spec["routing"],
		)
		if name:
			created.append(name)

	# ---- Level 3: blow moulding
	for wip, preform, batch, minutes in LEVEL_3:
		name = create_bom(
			company, wip, batch,
			[_rm(preform, batch / BLOWING_YIELD)],
			operations=[("Preform Blowing", minutes)],
			routing_name=f"Blowing - {wip}",
		)
		if name:
			created.append(name)

	# ---- Level 2: filling, capping, labelling
	for fg, blown, volume, cap, label, batch, operation, minutes in LEVEL_2:
		name = create_bom(
			company, fg, batch,
			[
				_rm(blown, batch / FILLING_YIELD),
				_rm("WIP-WTR-OZ", batch * volume / FILLING_YIELD),
				_rm(cap, batch / FILLING_YIELD),
				_rm(label, batch / FILLING_YIELD),
			]
			+ ([_rm("RM-HDL-5L", batch)] if fg == "FG-BOT-5000" else []),
			operations=[(operation, minutes), ("Sleeve Labelling & Coding", round(minutes * 0.45))],
			routing_name=f"Filling - {fg}",
		)
		if name:
			created.append(name)

	# ---- Level 2b: 5-gallon refill (no blow moulding)
	name = create_bom(
		company, "FG-BOT-18900", 500,
		[
			_rm("RM-BTL-PC-189", 500 * 0.02),   # 2% attrition of the returnable fleet
			_rm("WIP-WTR-OZ", 500 * 18.9 / 0.99),
			_rm("RM-CAP-55", 500),
			_rm("RM-LBL-189", 500),
			_rm("RM-CHM-CIP", 500 * 0.012),
		],
		operations=[("Container Wash & Fill - 5 Gallon", 96)],
		routing_name="Filling - 5 Gallon",
	)
	if name:
		created.append(name)

	# ---- Level 1: shrink packs
	for pack, bottle, bottles, film, tray, batch, minutes in LEVEL_1:
		items = [
			_rm(bottle, batch * bottles / PACKING_YIELD),
			_rm("RM-SHR-FILM", batch * film),
		]
		if tray:
			items.append(_rm("RM-CTN-TRAY", batch))
		name = create_bom(
			company, pack, batch, items,
			operations=[("Shrink Wrapping", minutes), ("Palletising & Batch Coding", round(minutes * 0.35))],
			routing_name=f"Packing - {pack}",
		)
		if name:
			created.append(name)

	frappe.db.commit()
	return created


@frappe.whitelist()
def rebuild_bom_costs():
	"""Recost the whole tree bottom-up after a purchase-price change."""
	from erpnext.manufacturing.doctype.bom_update_tool.bom_update_tool import update_cost

	update_cost()
	return "BOM costs refreshed"
