frappe.ui.form.on("Geofence Zone", {
	refresh(frm) {
		if (frm.doc.center_latitude) {
			frm.add_custom_button(__("Open in Maps"), () => {
				window.open(`https://www.google.com/maps?q=${frm.doc.center_latitude},${frm.doc.center_longitude}`, "_blank");
			});
		}
		frm.add_custom_button(__("Use My Current Location"), () => {
			navigator.geolocation.getCurrentPosition((pos) => {
				frm.set_value({
					center_latitude: pos.coords.latitude,
					center_longitude: pos.coords.longitude,
				});
			});
		});
	},
	zone_type(frm) {
		frm.toggle_reqd("center_latitude", frm.doc.zone_type === "Circle");
		frm.toggle_reqd("center_longitude", frm.doc.zone_type === "Circle");
	},
});
