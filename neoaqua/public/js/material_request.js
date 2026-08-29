frappe.ui.form.on("Material Request", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || frm.doc.material_request_type !== "Purchase") return;
		frm.add_custom_button(__("Supplier Compliance"), () => {
			frappe.set_route("List", "Supplier", { neoaqua_supplier_rating: "A - Approved" });
		}, __("View"));
	},
});
