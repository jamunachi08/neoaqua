# Copyright (c) 2026, Neotec Integrated Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

# SASO / GSO 1025 & SFDA potable bottled water reference ranges
DEFAULT_PARAMETERS = [
	{"parameter": "pH", "unit": "", "min_value": 6.5, "max_value": 8.5, "method": "Electrometric"},
	{"parameter": "TDS", "unit": "mg/L", "min_value": 50, "max_value": 500, "method": "Conductivity"},
	{"parameter": "Conductivity", "unit": "uS/cm", "min_value": 50, "max_value": 800, "method": "Probe"},
	{"parameter": "Turbidity", "unit": "NTU", "min_value": 0, "max_value": 1, "method": "Nephelometric"},
	{"parameter": "Residual Ozone", "unit": "mg/L", "min_value": 0.1, "max_value": 0.4, "method": "Colorimetric"},
	{"parameter": "Total Hardness", "unit": "mg/L CaCO3", "min_value": 0, "max_value": 300, "method": "EDTA Titration"},
	{"parameter": "Nitrate", "unit": "mg/L", "min_value": 0, "max_value": 50, "method": "Ion Chromatography"},
	{"parameter": "Fill Volume Deviation", "unit": "%", "min_value": -2, "max_value": 2, "method": "Gravimetric"},
	{"parameter": "Cap Torque", "unit": "in-lb", "min_value": 12, "max_value": 22, "method": "Torque Meter"},
]


class WaterQualityCheck(Document):
	def validate(self):
		self.load_default_parameters()
		self.evaluate_parameters()
		self.evaluate_overall()

	def on_submit(self):
		self.update_batch()

	def load_default_parameters(self):
		if self.parameters or self.is_new() is False:
			return
		for p in DEFAULT_PARAMETERS:
			self.append("parameters", p)

	def evaluate_parameters(self):
		for row in self.parameters:
			if row.observed_value is None:
				row.result = "N/A"
				continue
			lo, hi = flt(row.min_value), flt(row.max_value)
			row.result = "Pass" if lo <= flt(row.observed_value) <= hi else "Fail"

	def evaluate_overall(self):
		micro_fail = any(
			(self.get(f) == "Present") for f in ("coliform", "pseudomonas", "yeast_mould")
		)
		param_fail = any(r.result == "Fail" for r in self.parameters)
		if micro_fail:
			self.overall_result = "Fail"
			self.sfda_reportable = 1
		elif param_fail and self.overall_result != "Conditional Release":
			self.overall_result = "Fail"
		elif not param_fail:
			self.overall_result = self.overall_result or "Pass"

	def update_batch(self):
		if self.batch_no and self.overall_result == "Fail":
			frappe.db.set_value("Batch", self.batch_no, "disabled", 1)
			frappe.msgprint(
				_("Batch {0} has been disabled following a failed quality check.").format(self.batch_no),
				indicator="red",
			)


@frappe.whitelist()
def get_batch_qc_status(batch_no):
	res = frappe.db.get_value(
		"Water Quality Check",
		{"batch_no": batch_no, "docstatus": 1, "check_type": "Finished Goods"},
		["name", "overall_result"],
		as_dict=True,
	)
	return res or {}
