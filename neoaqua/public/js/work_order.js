frappe.ui.form.on("Work Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		frm.add_custom_button(__("Water Quality Check"), () => {
			frappe.new_doc("Water Quality Check", {
				work_order: frm.doc.name,
				item_code: frm.doc.production_item,
				production_line: frm.doc.neoaqua_production_line,
				check_type: "In-Process (Filler)",
				company: frm.doc.company,
			});
		}, __("Create"));

		if (!frm.doc.neoaqua_batch_no) {
			frm.add_custom_button(__("Reserve Batch"), () => {
				frappe.call({
					method: "neoaqua.manufacturing.batch_hooks.create_batch_now",
					args: { work_order: frm.doc.name },
					callback(r) {
						if (r.message) {
							frappe.show_alert({ message: __("Batch {0} reserved", [r.message]), indicator: "green" });
							frm.reload_doc();
						}
					},
				});
			}, __("Create"));
		} else {
			frm.add_custom_button(__("Batch {0}", [frm.doc.neoaqua_batch_no]), () =>
				frappe.set_route("Form", "Batch", frm.doc.neoaqua_batch_no), __("View"));
		}

		frm.add_custom_button(__("QC Register"), () =>
			frappe.set_route("query-report", "Batch QC Register", { work_order: frm.doc.name }), __("View"));
	},
});
