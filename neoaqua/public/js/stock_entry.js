frappe.ui.form.on("Stock Entry", {
	refresh(frm) {
		if (frm.doc.neoaqua_van_trip) {
			frm.add_custom_button(__("Van Trip"), () =>
				frappe.set_route("Form", "Van Trip", frm.doc.neoaqua_van_trip), __("View"));
		}
	},
});
