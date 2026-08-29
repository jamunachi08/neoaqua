// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("Salesman Check In", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.doc.latitude) {
			frm.add_custom_button(__("Capture My Location"), () => frm.trigger("capture_location"))
				.addClass("btn-primary");
		}
		if (frm.doc.docstatus === 1 && frm.doc.latitude) {
			frm.add_custom_button(__("Open in Maps"), () => {
				window.open(`https://www.google.com/maps?q=${frm.doc.latitude},${frm.doc.longitude}`, "_blank");
			}, __("View"));
		}
		if (frm.doc.within_geofence === 0 && frm.doc.geofence_zone) {
			frm.dashboard.set_headline(
				`<span class="indicator-pill red">${__("Outside geofence by {0} m", [frm.doc.distance_from_zone_m])}</span>`);
		}
	},

	capture_location(frm) {
		if (!navigator.geolocation) {
			frappe.msgprint(__("Geolocation is not available on this device."));
			return;
		}
		frappe.show_alert({ message: __("Acquiring GPS fix..."), indicator: "blue" });
		navigator.geolocation.getCurrentPosition(
			(pos) => {
				frm.set_value({
					latitude: pos.coords.latitude,
					longitude: pos.coords.longitude,
					accuracy_m: pos.coords.accuracy,
					checkin_datetime: frappe.datetime.now_datetime(),
				});
				frappe.show_alert({ message: __("Location captured"), indicator: "green" });
			},
			() => frappe.msgprint(__("Unable to read the device location. Enable location permission.")),
			{ enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
		);
	},

	customer(frm) {
		if (!frm.doc.customer) return;
		frappe.db.get_value("Customer", frm.doc.customer, "neoaqua_geofence_zone")
			.then((r) => { if (r.message) frm.set_value("geofence_zone", r.message.neoaqua_geofence_zone); });
	},
});
