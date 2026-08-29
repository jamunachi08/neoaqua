// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("Batch Naming Rule", {
	refresh(frm) {
		frm.add_custom_button(__("Open in Builder"), () => {
			frappe.set_route("batch-code-builder").then(() => {
				frappe.pages["batch-code-builder"] &&
					frappe.msgprint(__("Select {0} in the Load Existing Rule field.", [frm.doc.name]));
			});
		}).addClass("btn-primary");

		if (!frm.is_new()) {
			frm.add_custom_button(__("Test Combinations"), () => frm.trigger("test_combinations"), __("Tools"));
			frm.add_custom_button(__("Reset Counters"), () => {
				frappe.confirm(
					__("This resets every sequence counter for this rule. New batches will restart from the beginning. Continue?"),
					() => frm.call("reset_counters").then((r) => frappe.show_alert({ message: r.message, indicator: "orange" }))
				);
			}, __("Tools"));
			frm.add_custom_button(__("Sequence Counters"), () =>
				frappe.set_route("List", "Batch Sequence Counter", { naming_rule: frm.doc.name }), __("View"));
		}

		frm.trigger("render_preview_banner");
	},

	render_preview_banner(frm) {
		frm.dashboard.clear_headline();
		if (!frm.doc.sample_code) return;
		frm.dashboard.set_headline(
			`<div style="font-family:Consolas,monospace;font-size:20px;font-weight:600;color:#1B98E0">
				${frappe.utils.escape_html(frm.doc.sample_code)}
			</div>
			<div class="text-muted small">${frappe.utils.escape_html(frm.doc.pattern || "")}</div>`
		);
	},

	test_combinations(frm) {
		frm.call("test_combinations").then((r) => {
			const m = r.message || {};
			const rows = (m.rows || [])
				.map(
					(x) => `<tr${x.collides_with ? ' style="background:#FEF3F2"' : ""}>
						<td>${frappe.utils.escape_html(x.item_code)}</td>
						<td>${frappe.utils.escape_html(x.production_line)}</td>
						<td>${frappe.utils.escape_html(x.shift)}</td>
						<td style="font-family:Consolas,monospace">${frappe.utils.escape_html(x.batch_code)}</td>
					</tr>`
				)
				.join("");
			frappe.msgprint({
				title: __("Combination Matrix"),
				wide: true,
				message: `${m.warning ? `<p style="color:#B54708">⚠ ${frappe.utils.escape_html(m.warning)}</p>` : ""}
					<p class="text-muted small">${__("{0} combinations, {1} distinct codes", [m.total, m.distinct])}</p>
					<table class="table table-bordered" style="font-size:12px">
					<thead><tr><th>${__("Item")}</th><th>${__("Line")}</th><th>${__("Shift")}</th><th>${__("Code")}</th></tr></thead>
					<tbody>${rows}</tbody></table>`,
			});
		});
	},

	applies_to(frm) { frm.trigger("refresh"); },
});

frappe.ui.form.on("Batch Naming Segment", {
	segment_type(frm) { frm.save_or_update && frm.dirty(); },
});
