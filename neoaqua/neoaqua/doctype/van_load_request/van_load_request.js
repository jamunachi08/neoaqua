// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("Van Load Request", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Suggest from 30-Day Average"), () => {
				frappe.call({
					method: "neoaqua.neoaqua.doctype.van_load_request.van_load_request.get_suggested_load",
					args: { van: frm.doc.van, coverage_days: 1 },
					callback(r) {
						frm.clear_table("items");
						(r.message || []).forEach((row) =>
							frm.add_child("items", { item_code: row.item_code, qty: row.qty }));
						frm.refresh_field("items");
						frm.trigger("recalc");
					},
				});
			});
		}
		if (frm.doc.stock_entry) {
			frm.add_custom_button(__("Stock Entry"), () =>
				frappe.set_route("Form", "Stock Entry", frm.doc.stock_entry), __("View"));
		}
	},
	recalc(frm) { frm.save(); },
	onload(frm) {
		frm.set_query("van", () => ({ filters: { status: "Active" } }));
	},
});
