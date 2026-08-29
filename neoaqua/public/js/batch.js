// Batch extensions - decode, QC status, work order traceability
frappe.ui.form.on("Batch", {
	refresh(frm) {
		if (frm.doc.neoaqua_qc_status) {
			const map = { Pass: "green", Fail: "red", Pending: "orange", "Conditional Release": "blue" };
			frm.page.set_indicator(__("QC: {0}", [frm.doc.neoaqua_qc_status]),
				map[frm.doc.neoaqua_qc_status] || "grey");
		}

		if (frm.doc.neoaqua_naming_rule) {
			frm.add_custom_button(__("Decode Batch Code"), () => frm.trigger("decode"), __("Tools"));
			frm.add_custom_button(__("Naming Rule"), () =>
				frappe.set_route("Form", "Batch Naming Rule", frm.doc.neoaqua_naming_rule), __("View"));
		}

		if (frm.doc.neoaqua_work_order) {
			frm.add_custom_button(__("Work Order"), () =>
				frappe.set_route("Form", "Work Order", frm.doc.neoaqua_work_order), __("View"));
		}

		if (!frm.is_new()) {
			frm.add_custom_button(__("Quality Check"), () => {
				frappe.new_doc("Water Quality Check", {
					batch_no: frm.doc.name,
					item_code: frm.doc.item,
					work_order: frm.doc.neoaqua_work_order,
					production_line: frm.doc.neoaqua_production_line,
					check_type: "Finished Goods",
				});
			}, __("Create"));
		}
	},

	decode(frm) {
		frappe.call({
			method: "neoaqua.manufacturing.batch_naming.decode_batch",
			args: { batch_id: frm.doc.name },
			callback(r) {
				const m = r.message || {};
				if (!m.decoded) {
					frappe.msgprint(m.message || __("Nothing to decode."));
					return;
				}
				frappe.msgprint({
					title: __("Batch Code Breakdown"),
					message: `<table class="table table-bordered" style="font-size:12px">
						<thead><tr><th>${__("Segment")}</th><th>${__("Value")}</th></tr></thead>
						<tbody>${m.decoded
							.map((s) => `<tr><td>${frappe.utils.escape_html(s.segment)}</td>
								<td style="font-family:Consolas,monospace">${frappe.utils.escape_html(s.value || "—")}</td></tr>`)
							.join("")}</tbody></table>`,
				});
			},
		});
	},
});
