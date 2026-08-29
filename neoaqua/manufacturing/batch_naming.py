# Copyright (c) 2026, Neotec Integrated Solutions
"""Batch code composition engine.

A batch code is built by concatenating ordered segments defined on a
`Batch Naming Rule`. Each segment resolves a value from one of four places:

    * a literal typed into the rule           (Fixed Text, Plant Code)
    * a derived date part                     (Year, Julian Day, Expiry ...)
    * a field on the context document         (Item, Work Order, Batch)
    * a monotonic counter with a scope key    (Sequence Counter)

and is then optionally passed through a value map (so "Line 1 - Small PET"
becomes "L1"), truncated or padded to a fixed length, case-transformed, and
joined with a separator.

Rules are resolved by specificity: an Item-specific rule beats an Item Group
rule, which beats a Production Line rule, which beats All Items. Ties break on
the `priority` field, highest first.

Counters are allocated inside a row lock on `Batch Sequence Counter` so two
concurrent Manufacture stock entries on the same line cannot take the same
number. Preview never allocates - it renders the counter as a run of #.
"""

import re

import frappe
from frappe import _
from frappe.utils import add_days, cint, cstr, flt, getdate, nowdate

MONTH_LETTERS = "ABCDEFGHIJKL"

DATE_SEGMENTS = {
	"Year (YY)": lambda d: d.strftime("%y"),
	"Year (YYYY)": lambda d: d.strftime("%Y"),
	"Month (MM)": lambda d: d.strftime("%m"),
	"Month (Letter A-L)": lambda d: MONTH_LETTERS[d.month - 1],
	"Day (DD)": lambda d: d.strftime("%d"),
	"Julian Day (DDD)": lambda d: f"{d.timetuple().tm_yday:03d}",
	"Week (WW)": lambda d: d.strftime("%V"),
	"Date (YYMMDD)": lambda d: d.strftime("%y%m%d"),
}

EXPIRY_SEGMENTS = {
	"Expiry Year (YY)": lambda d: d.strftime("%y"),
	"Expiry Month (MM)": lambda d: d.strftime("%m"),
	"Expiry Day (DD)": lambda d: d.strftime("%d"),
	"Expiry (YYMMDD)": lambda d: d.strftime("%y%m%d"),
}

COUNTER_PLACEHOLDER = "#"


# ================================================================== context
def build_context(item_code=None, work_order=None, batch=None, stock_entry=None,
                  posting_date=None, production_line=None, shift=None, company=None):
	"""Assemble everything a segment might need into one flat dict."""
	ctx = frappe._dict(
		{
			"item_code": item_code,
			"work_order": work_order,
			"batch": batch,
			"stock_entry": stock_entry,
			"posting_date": getdate(posting_date or nowdate()),
			"production_line": production_line,
			"shift": shift,
			"company": company,
		}
	)

	if work_order and not (item_code and production_line):
		wo = frappe.db.get_value(
			"Work Order",
			work_order,
			["production_item", "neoaqua_production_line", "neoaqua_shift", "company"],
			as_dict=True,
		)
		if wo:
			ctx.item_code = ctx.item_code or wo.production_item
			ctx.production_line = ctx.production_line or wo.neoaqua_production_line
			ctx.shift = ctx.shift or wo.neoaqua_shift
			ctx.company = ctx.company or wo.company

	if ctx.item_code:
		item = frappe.get_cached_doc("Item", ctx.item_code)
		ctx.item = item
		ctx.item_group = item.item_group
		ctx.shelf_life_in_days = cint(item.shelf_life_in_days)
		ctx.fill_volume_ml = cint(item.get("neoaqua_fill_volume_ml"))
		ctx.item_batch_code = item.get("neoaqua_batch_code")

	ctx.company = ctx.company or frappe.defaults.get_global_default("company")
	if ctx.company:
		ctx.company_abbr = frappe.get_cached_value("Company", ctx.company, "abbr")

	if not ctx.production_line and ctx.item_code:
		from neoaqua.manufacturing.wo_hooks import LINE_BY_GROUP

		ctx.production_line = LINE_BY_GROUP.get(ctx.item_group)

	return ctx


# ================================================================== resolution
def resolve_rule(ctx):
	"""Return the most specific active rule for this context."""
	filters = {"is_active": 1}
	if ctx.get("company"):
		filters["company"] = ctx.company

	rules = frappe.get_all(
		"Batch Naming Rule",
		filters=filters,
		fields=["name", "applies_to", "item_code", "item_group", "production_line", "priority"],
	)
	if not rules:
		return None

	specificity = {"Item": 4, "Item Group": 3, "Production Line": 2, "All Items": 1}
	candidates = []
	for r in rules:
		if r.applies_to == "Item" and r.item_code != ctx.get("item_code"):
			continue
		if r.applies_to == "Item Group" and r.item_group != ctx.get("item_group"):
			continue
		if r.applies_to == "Production Line" and r.production_line != ctx.get("production_line"):
			continue
		candidates.append(r)

	if not candidates:
		return None
	candidates.sort(key=lambda r: (specificity.get(r.applies_to, 0), cint(r.priority)), reverse=True)
	return frappe.get_cached_doc("Batch Naming Rule", candidates[0].name)


# ================================================================== segments
def _apply_map(segment, value):
	if not segment.use_value_map or not segment.value_map:
		return value
	for row in segment.value_map:
		if cstr(row.source_value).strip().lower() == cstr(value).strip().lower():
			return row.code
	return value


def _shape(segment, value, rule):
	value = cstr(value or "")

	if segment.transform == "UPPERCASE":
		value = value.upper()
	elif segment.transform == "lowercase":
		value = value.lower()
	elif segment.transform == "Strip Non-Alphanumeric":
		value = re.sub(r"[^A-Za-z0-9]", "", value)

	length = cint(segment.length)
	if length:
		if len(value) > length:
			value = value[:length]
		elif len(value) < length:
			value = value.rjust(length, (segment.pad_char or "0")[:1])

	if rule and rule.force_uppercase:
		value = value.upper()
	return value


def resolve_segment(segment, ctx, rule, preview=False):
	st = segment.segment_type
	value = None

	if st == "Fixed Text":
		value = segment.fixed_text

	elif st == "Item Code":
		value = ctx.get("item_code")

	elif st == "Item Batch Code":
		value = ctx.get("item_batch_code") or ctx.get("item_code")

	elif st == "Item Group Code":
		value = ctx.get("item_group")

	elif st == "Fill Volume":
		value = ctx.get("fill_volume_ml")

	elif st == "Production Line Code":
		value = ctx.get("production_line")

	elif st == "Shift Code":
		value = ctx.get("shift")

	elif st == "Plant Code":
		value = segment.fixed_text or frappe.db.get_single_value("NeoAqua Settings", "plant_code")

	elif st == "Company Abbreviation":
		value = ctx.get("company_abbr")

	elif st in DATE_SEGMENTS:
		value = DATE_SEGMENTS[st](ctx.posting_date)

	elif st in EXPIRY_SEGMENTS:
		days = cint(rule.expiry_override_days) or cint(ctx.get("shelf_life_in_days")) or 365
		value = EXPIRY_SEGMENTS[st](getdate(add_days(ctx.posting_date, days)))

	elif st == "Work Order Suffix":
		wo = cstr(ctx.get("work_order") or "")
		n = cint(segment.length) or 4
		value = wo[-n:] if wo else ""

	elif st == "Sequence Counter":
		if preview:
			value = COUNTER_PLACEHOLDER * (cint(segment.length) or 3)
			return value  # never shaped, never mapped
		value = allocate_counter(rule, segment, ctx)

	elif st == "Custom Field":
		value = _read_source_field(segment, ctx)

	if value in (None, ""):
		if segment.is_mandatory and not preview:
			frappe.throw(
				_("Batch naming rule {0}: segment {1} ({2}) resolved to an empty value.").format(
					rule.name, segment.idx, st
				)
			)
		value = segment.fallback or ""

	value = _apply_map(segment, value)
	return _shape(segment, value, rule)


def _read_source_field(segment, ctx):
	if not segment.source_fieldname:
		return None
	dt = segment.source_doctype or "Item"
	name = {
		"Item": ctx.get("item_code"),
		"Work Order": ctx.get("work_order"),
		"Batch": ctx.get("batch"),
		"Stock Entry": ctx.get("stock_entry"),
	}.get(dt)
	if not name:
		return None
	return frappe.db.get_value(dt, name, segment.source_fieldname)


# ================================================================== counters
def allocate_counter(rule, segment, ctx):
	"""Take the next number under a lock. Returns a zero-padded string."""
	scope_key = counter_scope_key(segment, ctx)
	start = cint(segment.counter_start) or 1

	name = frappe.db.get_value(
		"Batch Sequence Counter",
		{"naming_rule": rule.name, "scope_key": scope_key},
		"name",
		for_update=True,
	)

	if name:
		current = cint(frappe.db.get_value("Batch Sequence Counter", name, "current_value")) + 1
		frappe.db.set_value("Batch Sequence Counter", name, "current_value", current, update_modified=False)
	else:
		current = start
		doc = frappe.new_doc("Batch Sequence Counter")
		doc.update({"naming_rule": rule.name, "scope_key": scope_key, "current_value": current})
		doc.flags.ignore_permissions = True
		doc.insert()

	return cstr(current)


def counter_scope_key(segment, ctx):
	scope = segment.counter_scope or "Per Day"
	d = ctx.posting_date
	parts = [scope]
	if scope == "Per Year":
		parts.append(d.strftime("%Y"))
	elif scope == "Per Month":
		parts.append(d.strftime("%Y-%m"))
	elif scope == "Per Day":
		parts.append(d.strftime("%Y-%m-%d"))
	elif scope == "Per Item":
		parts.append(cstr(ctx.get("item_code")))
	elif scope == "Per Item per Day":
		parts += [cstr(ctx.get("item_code")), d.strftime("%Y-%m-%d")]
	elif scope == "Per Line per Day":
		parts += [cstr(ctx.get("production_line")), d.strftime("%Y-%m-%d")]
	elif scope == "Per Line per Shift per Day":
		parts += [cstr(ctx.get("production_line")), cstr(ctx.get("shift")), d.strftime("%Y-%m-%d")]
	return "::".join(p for p in parts if p)


# ================================================================== build
def build_code(rule, ctx, preview=False):
	"""Concatenate every segment of a rule into a batch code."""
	pieces = []
	for seg in rule.segments:
		value = resolve_segment(seg, ctx, rule, preview=preview)
		if value == "" and not seg.is_mandatory:
			continue
		sep = seg.separator_after
		if sep is None:
			sep = rule.default_separator or ""
		pieces.append((value, sep))

	code = ""
	for i, (value, sep) in enumerate(pieces):
		code += value
		if i < len(pieces) - 1:
			code += sep

	if rule.force_uppercase:
		code = code.upper()
	if cint(rule.max_length) and len(code) > cint(rule.max_length):
		code = code[: cint(rule.max_length)]
	return code


def generate(item_code=None, work_order=None, posting_date=None, production_line=None,
             shift=None, company=None, batch=None):
	"""Public entry point. Returns (code, rule_name) or (None, None) when no
	rule applies - the caller then falls back to the ERPNext batch series."""
	ctx = build_context(
		item_code=item_code, work_order=work_order, posting_date=posting_date,
		production_line=production_line, shift=shift, company=company, batch=batch,
	)
	rule = resolve_rule(ctx)
	if not rule:
		return None, None

	code = build_code(rule, ctx, preview=False)
	code = _ensure_unique(code)
	return code, rule.name


def _ensure_unique(code):
	if not frappe.db.exists("Batch", code):
		return code
	for suffix in range(1, 100):
		candidate = f"{code}-{suffix}"
		if not frappe.db.exists("Batch", candidate):
			return candidate
	frappe.throw(_("Could not generate a unique batch code from {0}.").format(code))


def compute_expiry(rule, ctx):
	days = cint(rule.expiry_override_days) if rule else 0
	if not days:
		days = cint(ctx.get("shelf_life_in_days"))
	if not days:
		days = cint(frappe.db.get_single_value("NeoAqua Settings", "default_batch_shelf_life_days"))
	return add_days(ctx.posting_date, days) if days else None


# ================================================================== tooling
def resolve_rule_argument(rule):
	"""Accept a saved rule name, a dict, or a JSON string, and return a
	Batch Naming Rule document.

	The JSON-string case is the one that matters: `frappe.call` serialises a
	dict argument to JSON before it crosses the wire, so a whitelisted method
	that only checks `isinstance(rule, dict)` receives a string and falls
	through to loading a rule whose NAME is the entire JSON blob. That is the
	"Batch Naming Rule {...} not found" error - the payload was being used as
	a primary key.

	Unsaved drafts are built with `get_doc(dict)`, which never touches the
	database, so the builder can preview a rule that does not exist yet.
	"""
	if isinstance(rule, str):
		stripped = rule.strip()
		if stripped.startswith("{"):
			try:
				rule = frappe.parse_json(stripped)
			except Exception:
				frappe.throw(_("Could not read the batch naming rule payload."))
		else:
			return frappe.get_doc("Batch Naming Rule", stripped)

	if isinstance(rule, dict):
		payload = dict(rule)
		if payload.get("doctype") not in (None, "Batch Naming Rule"):
			frappe.throw(_("Expected a Batch Naming Rule, received {0}.").format(payload["doctype"]))
		payload["doctype"] = "Batch Naming Rule"
		# an unsaved draft carries a placeholder name; drop it so nothing
		# mistakes this for a stored record
		payload.pop("name", None)
		payload.pop("__islocal", None)
		payload.pop("__unsaved", None)
		return frappe.get_doc(payload)

	if hasattr(rule, "doctype"):
		return rule

	frappe.throw(_("Could not resolve the batch naming rule."))


@frappe.whitelist()
def preview_rule(rule, item_code=None, production_line=None, shift=None, posting_date=None):
	"""Render a sample code and a human-readable pattern without touching
	any counter. Used by the Batch Code Builder tool."""
	doc = resolve_rule_argument(rule)

	if not item_code:
		item_code = doc.item_code or frappe.db.get_value(
			"Item", {"has_batch_no": 1, "item_group": doc.item_group or ["!=", ""]}, "name"
		) or frappe.db.get_value("Item", {"has_batch_no": 1}, "name")

	ctx = build_context(
		item_code=item_code,
		production_line=production_line or doc.production_line,
		shift=shift or "A",
		posting_date=posting_date,
		company=doc.company,
	)

	segments = []
	for seg in doc.segments:
		value = resolve_segment(seg, ctx, doc, preview=True)
		segments.append(
			{
				"idx": seg.idx,
				"type": seg.segment_type,
				"value": value,
				"length": len(value),
				"separator": seg.separator_after if seg.separator_after is not None else (doc.default_separator or ""),
			}
		)

	code = build_code(doc, ctx, preview=True)
	pattern = " + ".join(f"[{s['type']}]" for s in segments)
	return {
		"code": code,
		"length": len(code),
		"pattern": pattern,
		"segments": segments,
		"expiry": cstr(compute_expiry(doc, ctx) or ""),
		"item_code": item_code,
		"max_length_exceeded": bool(cint(doc.max_length) and len(code) > cint(doc.max_length)),
	}


@frappe.whitelist()
def generate_combinations(rule, items=None, production_lines=None, shifts=None,
                          posting_date=None, limit=60):
	"""Render the full matrix of batch codes a rule will produce across the
	given items, lines and shifts. This is the combination explorer - it shows
	an operator exactly what will be printed on the bottle before the rule goes
	live, and flags any collision between two different combinations."""
	doc = resolve_rule_argument(rule)

	items = frappe.parse_json(items) if isinstance(items, str) else items
	production_lines = frappe.parse_json(production_lines) if isinstance(production_lines, str) else production_lines
	shifts = frappe.parse_json(shifts) if isinstance(shifts, str) else shifts

	if not items:
		items = frappe.get_all(
			"Item",
			filters={"has_batch_no": 1, "is_sales_item": 1},
			pluck="name",
			limit=6,
		)
	if not production_lines:
		production_lines = ["Line 1 - Small PET", "Line 2 - Large PET", "Line 3 - 5 Gallon"]
	if not shifts:
		shifts = ["A", "B", "C"]

	rows = []
	seen = {}
	for item in items:
		for line in production_lines:
			for shift in shifts:
				if len(rows) >= cint(limit):
					break
				ctx = build_context(
					item_code=item, production_line=line, shift=shift,
					posting_date=posting_date, company=doc.company,
				)
				code = build_code(doc, ctx, preview=True)
				key = code
				collision = key in seen
				seen.setdefault(key, f"{item} / {line} / {shift}")
				rows.append(
					{
						"item_code": item,
						"item_name": frappe.get_cached_value("Item", item, "item_name"),
						"production_line": line,
						"shift": shift,
						"batch_code": code,
						"length": len(code),
						"collides_with": seen[key] if collision else None,
					}
				)

	collisions = [r for r in rows if r["collides_with"]]
	return {
		"rows": rows,
		"total": len(rows),
		"distinct": len(seen),
		"collisions": len(collisions),
		"warning": (
			_("{0} of {1} combinations produce an identical code. Add a Sequence Counter, "
			  "a Production Line Code or a Shift Code segment to separate them.").format(
				len(collisions), len(rows)
			)
			if collisions
			else None
		),
	}


@frappe.whitelist()
def get_segment_palette():
	"""Metadata driving the builder UI: what each segment type produces and
	which options are relevant to it."""
	def s(t, sample, desc, opts):
		return {"type": t, "sample": sample, "description": desc, "options": opts}

	return [
		s("Fixed Text", "NAQ", "A literal prefix or code you type in.", ["fixed_text", "length"]),
		s("Item Batch Code", "B600", "Short code held on the item (falls back to item code).", ["length", "use_value_map"]),
		s("Item Code", "FG-BOT-600", "The full item code.", ["length", "transform", "use_value_map"]),
		s("Item Group Code", "SPET", "Item group, usually via a value map.", ["length", "use_value_map"]),
		s("Fill Volume", "0600", "Fill volume in ml, zero padded.", ["length", "pad_char"]),
		s("Production Line Code", "L1", "The line, usually mapped to one or two characters.", ["length", "use_value_map"]),
		s("Shift Code", "A", "Shift A, B or C.", ["length", "use_value_map"]),
		s("Plant Code", "RUH", "Site code from NeoAqua Settings or typed in.", ["fixed_text", "length"]),
		s("Company Abbreviation", "NWF", "Company abbreviation.", ["length"]),
		s("Year (YY)", "26", "Two-digit year of manufacture.", []),
		s("Year (YYYY)", "2026", "Four-digit year of manufacture.", []),
		s("Month (MM)", "08", "Two-digit month.", []),
		s("Month (Letter A-L)", "H", "Month as a letter, A=January.", []),
		s("Day (DD)", "24", "Two-digit day.", []),
		s("Julian Day (DDD)", "236", "Day of year, 001-366. Common on bottle coders.", []),
		s("Week (WW)", "35", "ISO week number.", []),
		s("Date (YYMMDD)", "260824", "Compact manufacture date.", []),
		s("Expiry Year (YY)", "27", "Year of expiry from shelf life.", []),
		s("Expiry Month (MM)", "08", "Month of expiry.", []),
		s("Expiry Day (DD)", "24", "Day of expiry.", []),
		s("Expiry (YYMMDD)", "270824", "Compact expiry date.", []),
		s("Work Order Suffix", "0142", "Last n characters of the work order name.", ["length"]),
		s("Sequence Counter", "001", "Monotonic counter under a scope you choose.", ["length", "counter_scope", "counter_start", "pad_char"]),
		s("Custom Field", "-", "Any field on Item, Work Order, Batch or Stock Entry.", ["source_doctype", "source_fieldname", "length", "fallback"]),
	]


@frappe.whitelist()
def decode_batch(batch_id):
	"""Reverse lookup - split an existing batch code back into its segments so
	a QA auditor can read a code off a bottle and know the line, shift and date."""
	rule_name = frappe.db.get_value("Batch", batch_id, "neoaqua_naming_rule")
	if not rule_name:
		return {"batch": batch_id, "decoded": None, "message": _("No naming rule recorded for this batch.")}

	doc = frappe.get_doc("Batch Naming Rule", rule_name)
	sep = doc.default_separator or ""
	parts = batch_id.split(sep) if sep else [batch_id]
	decoded = []
	for i, seg in enumerate(doc.segments):
		decoded.append(
			{
				"segment": seg.segment_type,
				"value": parts[i] if i < len(parts) else None,
			}
		)
	return {"batch": batch_id, "rule": rule_name, "decoded": decoded}
