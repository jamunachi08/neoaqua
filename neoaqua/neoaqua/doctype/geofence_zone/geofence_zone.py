# Copyright (c) 2026, Neotec Integrated Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class GeofenceZone(Document):
	def validate(self):
		if self.zone_type == "Circle":
			if not (self.center_latitude and self.center_longitude):
				frappe.throw(_("Centre coordinates are mandatory for a circular zone."))
			if not self.radius_m:
				self.radius_m = frappe.db.get_single_value("NeoAqua Settings", "default_geofence_radius") or 150
		else:
			if len(self.points or []) < 3:
				frappe.throw(_("A polygon zone needs at least three points."))
		self.validate_coordinates()

	def validate_coordinates(self):
		pairs = []
		if self.center_latitude or self.center_longitude:
			pairs.append((self.center_latitude, self.center_longitude))
		pairs += [(p.latitude, p.longitude) for p in (self.points or [])]
		for lat, lng in pairs:
			if lat is not None and not (-90 <= lat <= 90):
				frappe.throw(_("Latitude {0} is out of range.").format(lat))
			if lng is not None and not (-180 <= lng <= 180):
				frappe.throw(_("Longitude {0} is out of range.").format(lng))
