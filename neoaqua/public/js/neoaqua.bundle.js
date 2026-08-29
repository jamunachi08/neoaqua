// NeoAqua global desk extensions
import "./sales_invoice";
import "./work_order";
import "./stock_entry";
import "./material_request";

frappe.provide("neoaqua");

neoaqua.capture_position = function () {
	return new Promise((resolve, reject) => {
		if (!navigator.geolocation) return reject(new Error("geolocation unavailable"));
		navigator.geolocation.getCurrentPosition(
			(p) => resolve({
				latitude: p.coords.latitude,
				longitude: p.coords.longitude,
				accuracy: p.coords.accuracy,
			}),
			reject,
			{ enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
		);
	});
};

neoaqua.quick_check_in = function (customer, purpose) {
	return neoaqua.capture_position().then((pos) =>
		frappe.call({
			method: "neoaqua.neoaqua.doctype.salesman_check_in.salesman_check_in.quick_check_in",
			args: { customer, purpose, ...pos },
		})
	);
};

import "./batch";
