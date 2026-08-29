// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("Water Quality Check", {
	refresh(frm) {
		if (frm.doc.overall_result) {
			const map = { Pass: "green", Fail: "red", "Conditional Release": "orange" };
			frm.page.set_indicator(__(frm.doc.overall_result), map[frm.doc.overall_result]);
		}
		if (frm.doc.docstatus === 1 && frm.doc.overall_result === "Fail") {
			frm.dashboard.set_headline(
				`<span class="indicator-pill red">${__("Batch blocked from release")}</span>`);
		}
	},
	work_order(frm) {
		if (!frm.doc.work_order) return;
		frappe.db.get_value("Work Order", frm.doc.work_order, ["production_item", "neoaqua_production_line"])
			.then((r) => frm.set_value({
				item_code: r.message.production_item,
				production_line: r.message.neoaqua_production_line,
			}));
	},
});
