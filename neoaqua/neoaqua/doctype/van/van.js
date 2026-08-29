frappe.ui.form.on("Van", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Van Stock"), () =>
			frappe.set_route("query-report", "Van Stock Position", { van: frm.doc.name }), __("View"));
		frm.add_custom_button(__("New Trip"), () =>
			frappe.new_doc("Van Trip", { van: frm.doc.name }), __("Create"));
	},
});
