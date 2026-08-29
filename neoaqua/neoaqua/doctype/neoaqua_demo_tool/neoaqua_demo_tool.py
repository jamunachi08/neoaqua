# Copyright (c) 2026, Neotec Integrated Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from neoaqua.setup import demo, demo_cleanup


class NeoAquaDemoTool(Document):
	@frappe.whitelist()
	def generate_demo_data(self):
		return demo.generate(
			company=self.company,
			demo_days=self.demo_days or 7,
			include_procurement=self.include_procurement,
			include_production=self.include_production,
			include_van_sales=self.include_van_sales,
		)

	@frappe.whitelist()
	def remove_demo_data(self):
		result = demo_cleanup.delete_demo_data(
			run_id=None,
			delete_masters=self.delete_masters_too,
			confirm=self.confirm_text,
		)
		self.db_set("confirm_text", None)
		return result

	@frappe.whitelist()
	def run_plant_setup(self):
		"""Run the full plant setup from the browser, so a user never has to
		reach for a bench command to get started."""
		from neoaqua.setup import orchestrator

		return orchestrator.run_setup(self.company)

	@frappe.whitelist()
	def diagnose(self):
		from neoaqua.setup import orchestrator

		return orchestrator.diagnose(self.company)

	@frappe.whitelist()
	def summary(self):
		return demo_cleanup.demo_summary()
