# Copyright (c) 2026, Neotec Integrated Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class NeoAquaSettings(Document):
	def validate(self):
		if self.enable_geofencing and not self.default_geofence_radius:
			self.default_geofence_radius = 150
		if self.track_containers and not self.container_item:
			frappe.throw(_("Set the Empty Container Item to enable container tracking."))
		if self.track_containers and not self.container_deposit_account:
			frappe.msgprint(
				_("Container deposits will not post to the ledger until a liability account is set."),
				indicator="orange",
			)

	def on_update(self):
		frappe.clear_cache(doctype="NeoAqua Settings")
