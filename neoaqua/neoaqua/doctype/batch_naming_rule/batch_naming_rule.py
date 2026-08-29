# Copyright (c) 2026, Neotec Integrated Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from neoaqua.manufacturing import batch_naming


class BatchNamingRule(Document):
	def validate(self):
		self.validate_scope()
		self.validate_segments()
		self.refresh_preview()

	def on_update(self):
		frappe.clear_cache(doctype="Batch Naming Rule")

	# ------------------------------------------------------------ validation
	def validate_scope(self):
		required = {
			"Item": "item_code",
			"Item Group": "item_group",
			"Production Line": "production_line",
		}.get(self.applies_to)
		if required and not self.get(required):
			frappe.throw(
				_("Set {0} when the rule applies to {1}.").format(
					frappe.bold(self.meta.get_label(required)), self.applies_to
				)
			)
		# clear the fields that do not belong to the chosen scope
		if self.applies_to != "Item":
			self.item_code = None
		if self.applies_to != "Item Group":
			self.item_group = None
		if self.applies_to != "Production Line":
			self.production_line = None

		dup = frappe.db.get_value(
			"Batch Naming Rule",
			{
				"is_active": 1,
				"company": self.company,
				"applies_to": self.applies_to,
				"item_code": self.item_code,
				"item_group": self.item_group,
				"production_line": self.production_line,
				"priority": cint(self.priority),
				"name": ["!=", self.name],
			},
			"name",
		)
		if dup and self.is_active:
			frappe.throw(
				_("Rule {0} already covers the same scope at priority {1}. Change the priority "
				  "or deactivate one of them.").format(frappe.bold(dup), cint(self.priority))
			)

	def validate_segments(self):
		if not self.segments:
			frappe.throw(_("Add at least one segment."))

		counters = [s for s in self.segments if s.segment_type == "Sequence Counter"]
		if len(counters) > 1:
			frappe.throw(_("A rule can hold only one Sequence Counter segment."))

		for seg in self.segments:
			if seg.segment_type in ("Fixed Text", "Plant Code") and not seg.fixed_text:
				if seg.segment_type == "Fixed Text":
					frappe.throw(_("Row {0}: Fixed Text segment needs text.").format(seg.idx))
			if seg.segment_type == "Custom Field" and not seg.source_fieldname:
				frappe.throw(_("Row {0}: Custom Field segment needs a source fieldname.").format(seg.idx))
			if seg.segment_type == "Sequence Counter":
				if not seg.counter_scope:
					seg.counter_scope = "Per Day"
				if not seg.length:
					seg.length = 3
				if not seg.pad_char:
					seg.pad_char = "0"
			if seg.use_value_map and not seg.value_map:
				frappe.throw(
					_("Row {0}: Use Value Map is ticked but no mappings are defined.").format(seg.idx)
				)

		# a rule with no counter and no date part will collide on every run
		has_counter = bool(counters)
		has_date = any(
			s.segment_type in batch_naming.DATE_SEGMENTS or s.segment_type == "Work Order Suffix"
			for s in self.segments
		)
		if not has_counter and not has_date:
			frappe.msgprint(
				_("This rule has neither a Sequence Counter nor a date segment. Every batch of "
				  "the same item will generate the same code and be suffixed automatically."),
				indicator="orange",
				title=_("Likely Collisions"),
			)

	# ------------------------------------------------------------ preview
	def refresh_preview(self):
		try:
			result = batch_naming.preview_rule(self.as_dict())
		except Exception:
			self.sample_code = None
			self.pattern = None
			return
		self.sample_code = result.get("code")
		self.pattern = result.get("pattern")
		for seg in self.segments:
			match = next((s for s in result["segments"] if s["idx"] == seg.idx), None)
			seg.segment_preview = match["value"] if match else None
		if result.get("max_length_exceeded"):
			frappe.msgprint(
				_("The composed code is longer than the maximum length and will be truncated."),
				indicator="orange",
			)

	# ------------------------------------------------------------ actions
	@frappe.whitelist()
	def test_combinations(self, items=None, production_lines=None, shifts=None):
		return batch_naming.generate_combinations(
			self.as_dict(), items=items, production_lines=production_lines, shifts=shifts
		)

	@frappe.whitelist()
	def reset_counters(self):
		"""Clear every sequence counter belonging to this rule."""
		frappe.db.delete("Batch Sequence Counter", {"naming_rule": self.name})
		frappe.db.commit()
		return _("Counters reset.")
