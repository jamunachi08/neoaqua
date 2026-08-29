# Copyright (c) 2026, Neotec Integrated Solutions
"""Geofencing engine for van salesman check-ins.

Supports two zone shapes:
  * Circle  - centre lat/lng + radius in metres (haversine distance)
  * Polygon - ordered vertex list (ray-casting point-in-polygon + edge distance)

Enforcement level is read from NeoAqua Settings:
  Warn Only      -> a comment is added, nothing is blocked
  Block Check-in -> Salesman Check In cannot be submitted outside the fence
  Block Invoice  -> Sales Invoice against the customer is blocked without a
                    valid in-fence check-in for the same day
"""

import math

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, nowdate, time_diff_in_seconds

EARTH_RADIUS_M = 6_371_008.8


# ------------------------------------------------------------------ geometry
def haversine_m(lat1, lon1, lat2, lon2):
	"""Great-circle distance in metres between two WGS-84 points."""
	if None in (lat1, lon1, lat2, lon2):
		return None
	p1, p2 = math.radians(lat1), math.radians(lat2)
	dp = math.radians(lat2 - lat1)
	dl = math.radians(lon2 - lon1)
	a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
	return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def point_in_polygon(lat, lng, vertices):
	"""Ray-casting algorithm. `vertices` is a list of (lat, lng) tuples."""
	inside = False
	n = len(vertices)
	if n < 3:
		return False
	j = n - 1
	for i in range(n):
		yi, xi = vertices[i]
		yj, xj = vertices[j]
		if (xi > lng) != (xj > lng):
			x_int = (xj - xi) * (lng - xi) / ((xj - xi) or 1e-12)
			if lat < (yj - yi) * (lng - xi) / ((xj - xi) or 1e-12) + yi:
				inside = not inside
		j = i
	return inside


def distance_to_polygon_m(lat, lng, vertices):
	"""Shortest distance from a point to any polygon vertex (approximation
	sufficient for a 50-200 m urban fence)."""
	if not vertices:
		return None
	return min(haversine_m(lat, lng, v[0], v[1]) for v in vertices)


# ------------------------------------------------------------------ settings
def get_settings():
	return frappe.get_cached_doc("NeoAqua Settings")


def geofencing_enabled():
	s = get_settings()
	return bool(s.enable_geofencing)


# ------------------------------------------------------------------ resolve
def resolve_zone(customer, territory=None):
	"""Return the applicable Geofence Zone name for a customer."""
	zone = frappe.db.get_value(
		"Geofence Zone", {"customer": customer, "is_active": 1}, "name"
	)
	if zone:
		return zone
	if not territory:
		territory = frappe.db.get_value("Customer", customer, "territory")
	if territory:
		return frappe.db.get_value(
			"Geofence Zone", {"territory": territory, "is_active": 1, "customer": ""}, "name"
		)
	return None


def evaluate(latitude, longitude, zone_name):
	"""Evaluate a coordinate against a zone.

	Returns dict(within, distance_m, zone, radius_m).
	"""
	result = {"within": 0, "distance_m": None, "zone": zone_name, "radius_m": None}
	if not zone_name:
		return result

	zone = frappe.get_cached_doc("Geofence Zone", zone_name)
	settings = get_settings()
	radius = zone.radius_m or settings.default_geofence_radius or 150
	result["radius_m"] = radius

	if zone.zone_type == "Polygon" and zone.points:
		verts = [(p.latitude, p.longitude) for p in zone.points]
		inside = point_in_polygon(latitude, longitude, verts)
		result["within"] = 1 if inside else 0
		result["distance_m"] = 0 if inside else distance_to_polygon_m(latitude, longitude, verts)
	else:
		dist = haversine_m(latitude, longitude, zone.center_latitude, zone.center_longitude)
		result["distance_m"] = dist
		result["within"] = 1 if (dist is not None and dist <= radius) else 0

	return result


def enforce(doc):
	"""Called from Salesman Check In validate. Mutates the doc with geofence
	results and raises when the enforcement level demands it."""
	if not geofencing_enabled():
		doc.within_geofence = 1
		return

	zone = doc.geofence_zone or resolve_zone(doc.customer)
	doc.geofence_zone = zone
	res = evaluate(doc.latitude, doc.longitude, zone)
	doc.distance_from_zone_m = round(res["distance_m"], 2) if res["distance_m"] is not None else None
	doc.within_geofence = res["within"]

	if res["within"]:
		return

	level = get_settings().geofence_enforcement or "Warn Only"
	msg = _("Check-in is {0} m away from the geofence of {1} (allowed {2} m).").format(
		doc.distance_from_zone_m, doc.customer, res["radius_m"]
	)

	if level == "Warn Only" or doc.geofence_override_reason:
		if not doc.geofence_override_reason and not zone:
			return
		frappe.msgprint(msg, title=_("Outside Geofence"), indicator="orange")
		return

	frappe.throw(msg + " " + _("Enter an Override Reason to proceed."), title=_("Outside Geofence"))


def has_valid_checkin(customer, salesman, date=None):
	"""True when the salesman has an in-fence check-in for the customer today."""
	date = date or nowdate()
	return bool(
		frappe.db.exists(
			"Salesman Check In",
			{
				"customer": customer,
				"salesman": salesman,
				"docstatus": 1,
				"within_geofence": 1,
				"checkin_datetime": ["between", [f"{date} 00:00:00", f"{date} 23:59:59"]],
			},
		)
	)


# ------------------------------------------------------------------ scheduled
def flag_missed_visits():
	"""Every 15 minutes: mark planned stops as at-risk when the salesman has
	not checked in and the planned window has elapsed."""
	trips = frappe.get_all(
		"Van Trip",
		filters={"docstatus": 1, "status": "In Progress", "trip_date": nowdate()},
		pluck="name",
	)
	for name in trips:
		trip = frappe.get_doc("Van Trip", name)
		pending = [s for s in trip.stops if s.status == "Pending"]
		if not pending:
			continue
		if trip.start_time and time_diff_in_seconds(get_datetime(), trip.start_time) > 8 * 3600:
			frappe.publish_realtime(
				"neoaqua_missed_visits",
				{"trip": name, "pending": len(pending), "salesman": trip.salesman},
				user=frappe.db.get_value("Sales Person", trip.salesman, "employee") or None,
			)


@frappe.whitelist()
def get_route_geojson(route):
	"""Return a GeoJSON FeatureCollection of a route's stops - consumed by the
	Van Sales map dashboard."""
	features = []
	stops = frappe.get_all(
		"Van Route Stop",
		filters={"parent": route},
		fields=["customer", "customer_name", "sequence", "geofence_zone"],
		order_by="sequence asc",
	)
	for s in stops:
		if not s.geofence_zone:
			continue
		z = frappe.get_cached_doc("Geofence Zone", s.geofence_zone)
		if z.zone_type == "Polygon":
			coords = [[[p.longitude, p.latitude] for p in z.points]]
			geom = {"type": "Polygon", "coordinates": coords}
		else:
			geom = {"type": "Point", "coordinates": [z.center_longitude, z.center_latitude]}
		features.append(
			{
				"type": "Feature",
				"geometry": geom,
				"properties": {
					"customer": s.customer,
					"customer_name": s.customer_name,
					"sequence": s.sequence,
					"radius": z.radius_m,
				},
			}
		)
	return {"type": "FeatureCollection", "features": features}
