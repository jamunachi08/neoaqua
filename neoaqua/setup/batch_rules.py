# Copyright (c) 2026, Neotec Integrated Solutions
"""Default batch naming rules.

Three rules ship out of the box, chosen to reflect how the three lines in a
Saudi water plant actually code their bottles:

  * Small PET runs at high speed on an inkjet coder, so the code is compact,
    separator-free and includes the shift because a 10,000-bottle run can span
    two shifts.
  * Large PET and 5-gallon run slower with a laser coder and can carry a
    readable separated code.
  * The 5-gallon code carries the expiry date explicitly because the shorter
    180-day shelf life is the thing a delivery driver has to check at the door.

All three are idempotent - re-running the seeder will not duplicate them.
"""

import frappe

LINE_MAP = [
	{"source_value": "Line 1 - Small PET", "code": "L1"},
	{"source_value": "Line 2 - Large PET", "code": "L2"},
	{"source_value": "Line 3 - 5 Gallon", "code": "L3"},
	{"source_value": "RO Plant", "code": "RO"},
]

ITEM_BATCH_CODES = {
	"FG-BOT-200": "B200",
	"FG-BOT-330": "B330",
	"FG-BOT-600": "B600",
	"FG-BOT-1500": "B15L",
	"FG-BOT-5000": "B05L",
	"FG-BOT-18900": "B19L",
	"FG-PCK-200-48": "P248",
	"FG-PCK-330-40": "P340",
	"FG-PCK-600-24": "P624",
	"FG-PCK-600-12": "P612",
	"FG-PCK-1500-06": "P156",
	"FG-PCK-5000-04": "P504",
}

RULES = [
	{
		"rule_name": "Small PET Line Coder",
		"applies_to": "Production Line",
		"production_line": "Line 1 - Small PET",
		"priority": 10,
		"default_separator": "",
		"force_uppercase": 1,
		"max_length": 16,
		"set_expiry_from_shelf_life": 1,
		"description": "Compact separator-free code for the high-speed inkjet coder on Line 1.",
		"segments": [
			{"segment_type": "Item Batch Code", "length": 4, "is_mandatory": 1},
			{"segment_type": "Date (YYMMDD)"},
			{"segment_type": "Production Line Code", "length": 2, "use_value_map": 1, "value_map": LINE_MAP},
			{"segment_type": "Shift Code", "length": 1, "fallback": "A"},
			{"segment_type": "Sequence Counter", "length": 3, "pad_char": "0",
			 "counter_scope": "Per Line per Shift per Day", "counter_start": 1},
		],
	},
	{
		"rule_name": "Large PET Line Coder",
		"applies_to": "Production Line",
		"production_line": "Line 2 - Large PET",
		"priority": 10,
		"default_separator": "-",
		"force_uppercase": 1,
		"max_length": 24,
		"set_expiry_from_shelf_life": 1,
		"description": "Readable separated code for the slower laser coder on Line 2.",
		"segments": [
			{"segment_type": "Item Batch Code", "length": 4, "is_mandatory": 1},
			{"segment_type": "Date (YYMMDD)"},
			{"segment_type": "Production Line Code", "length": 2, "use_value_map": 1, "value_map": LINE_MAP},
			{"segment_type": "Sequence Counter", "length": 3, "pad_char": "0",
			 "counter_scope": "Per Line per Day", "counter_start": 1},
		],
	},
	{
		"rule_name": "Five Gallon Refill",
		"applies_to": "Production Line",
		"production_line": "Line 3 - 5 Gallon",
		"priority": 10,
		"default_separator": "-",
		"force_uppercase": 1,
		"max_length": 26,
		"set_expiry_from_shelf_life": 1,
		"description": "Carries the expiry date explicitly - the 180-day shelf life is what the "
		               "delivery driver checks at the customer door.",
		"segments": [
			{"segment_type": "Fixed Text", "fixed_text": "5G"},
			{"segment_type": "Date (YYMMDD)"},
			{"segment_type": "Expiry (YYMMDD)"},
			{"segment_type": "Sequence Counter", "length": 3, "pad_char": "0",
			 "counter_scope": "Per Day", "counter_start": 1},
		],
	},
	{
		"rule_name": "Default Batch Code",
		"applies_to": "All Items",
		"priority": 0,
		"default_separator": "-",
		"force_uppercase": 1,
		"max_length": 30,
		"set_expiry_from_shelf_life": 1,
		"description": "Catch-all fallback for any batched item without a more specific rule.",
		"segments": [
			{"segment_type": "Item Batch Code", "length": 6},
			{"segment_type": "Date (YYMMDD)"},
			{"segment_type": "Sequence Counter", "length": 3, "pad_char": "0",
			 "counter_scope": "Per Item per Day", "counter_start": 1},
		],
	},
]


def set_item_batch_codes():
	for item_code, short in ITEM_BATCH_CODES.items():
		if frappe.db.exists("Item", item_code):
			frappe.db.set_value("Item", item_code, "neoaqua_batch_code", short, update_modified=False)


def create_rules(company=None):
	from neoaqua.setup.brand import get_brand_code

	company = company or frappe.defaults.get_global_default("company")
	brand_code = get_brand_code(company)
	created = []
	for spec in RULES:
		if frappe.db.exists("Batch Naming Rule", spec["rule_name"]):
			continue
		doc = frappe.new_doc("Batch Naming Rule")
		payload = {k: v for k, v in spec.items() if k != "segments"}
		doc.update(payload)
		doc.company = company
		doc.is_active = 1
		for seg in spec["segments"]:
			payload = {k: v for k, v in seg.items() if k != "value_map"}
			# the 5-gallon rule opens with a literal; use the brand's code
			if payload.get("segment_type") == "Fixed Text" and payload.get("fixed_text") == "5G":
				payload["fixed_text"] = f"{brand_code}5G"
			row = doc.append("segments", payload)
			for m in seg.get("value_map", []):
				row.append("value_map", m)
			row.use_value_map = 1 if seg.get("value_map") else 0
		doc.flags.ignore_permissions = True
		doc.insert()
		created.append(doc.name)
	return created


def run(company=None):
	set_item_batch_codes()
	created = create_rules(company)
	settings = frappe.get_single("NeoAqua Settings")
	if not settings.auto_create_batch_on_work_order:
		settings.auto_create_batch_on_work_order = 1
	if not settings.plant_code:
		settings.plant_code = "RUH"
	if not settings.default_batch_naming_rule and frappe.db.exists("Batch Naming Rule", "Default Batch Code"):
		settings.default_batch_naming_rule = "Default Batch Code"
	settings.flags.ignore_permissions = True
	settings.save()
	frappe.db.commit()
	return created
