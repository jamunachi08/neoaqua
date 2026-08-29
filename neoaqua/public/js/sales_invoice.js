// Van sales extensions on Sales Invoice
frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.doc.neoaqua_van_trip) {
			frm.add_custom_button(__("Van Trip"), () =>
				frappe.set_route("Form", "Van Trip", frm.doc.neoaqua_van_trip), __("View"));
		}
		if (frm.doc.customer && frm.doc.docstatus === 0) frm.trigger("show_container_balance");
	},

	customer(frm) { frm.trigger("show_container_balance"); },

	show_container_balance(frm) {
		if (!frm.doc.customer) return;
		frappe.call({
			method: "neoaqua.neoaqua.doctype.container_ledger_entry.container_ledger_entry.customer_container_summary",
			args: { customer: frm.doc.customer },
			callback(r) {
				if (!r.message || !r.message.containers_held) return;
				frm.dashboard.add_comment(
					__("Customer currently holds {0} returnable containers ({1} deposit).", [
						r.message.containers_held,
						format_currency(r.message.deposit_liability, "SAR"),
					]),
					"blue", true
				);
			},
		});
	},

	before_save(frm) {
		if (!frm.doc.neoaqua_van_trip || frm.doc.neoaqua_latitude) return;
		if (!navigator.geolocation) return;
		navigator.geolocation.getCurrentPosition((pos) => {
			frm.doc.neoaqua_latitude = pos.coords.latitude;
			frm.doc.neoaqua_longitude = pos.coords.longitude;
		});
	},
});
