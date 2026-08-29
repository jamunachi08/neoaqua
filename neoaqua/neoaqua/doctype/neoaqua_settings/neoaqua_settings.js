// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("NeoAqua Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Run Plant Setup"), () => frm.trigger("run_setup")).addClass("btn-primary");
		frm.add_custom_button(__("Refresh Checklist"), () => frm.trigger("load_status"));
		if (frm.doc.brand_name) {
			frm.add_custom_button(__("Rename Brand"), () => frm.trigger("rename_brand"), __("Tools"));
			frm.add_custom_button(__("Fix Product Names"), () => {
				frappe.call({
					method: "neoaqua.setup.brand.resync_brand_names",
					freeze: true,
					freeze_message: __("Rebuilding product names..."),
					callback(r) {
						frappe.msgprint({
							title: __("Product Names Repaired"),
							indicator: "green",
							message: (r.message || {}).message,
						});
					},
				});
			}, __("Tools"));
		}
		frm.add_custom_button(__("NeoAqua Hub"), () =>
			frappe.set_route("neoaqua-hub"), __("Tools"));
		frm.add_custom_button(__("Control Tower"), () =>
			frappe.set_route("neoaqua-control-tower"), __("Tools"));
		frm.add_custom_button(__("Demo Data"), () =>
			frappe.set_route("Form", "NeoAqua Demo Tool"), __("Tools"));
		frm.add_custom_button(__("Batch Code Builder"), () =>
			frappe.set_route("batch-code-builder"), __("Tools"));
		frm.trigger("load_status");
	},

	run_setup(frm) {
		// The brand names every finished-goods item, so it must be settled
		// before anything is created rather than corrected afterwards.
		if (!frm.doc.brand_name) {
			frm.trigger("ask_brand");
			return;
		}
		frappe.confirm(
			__("This creates the item master, chart of accounts, BOM tree, vans, routes and dashboards. It is safe to run more than once — existing records are left alone. Continue?"),
			() => {
				frappe.dom.freeze(__("Setting up the plant. This takes a minute..."));
				frappe.call({
					method: "neoaqua.setup.orchestrator.run_setup",
					args: { company: frm.doc.company },
					callback(r) {
						frappe.dom.unfreeze();
						frm.trigger("show_report", r.message);
						frm.reload_doc();
					},
					error() {
						frappe.dom.unfreeze();
					},
				});
			}
		);
	},

	show_report(frm, report) {
		const rep = report || {};
		const rows = (rep.stages || [])
			.map((s) => {
				const color = { Done: "green", Failed: "red", Skipped: "orange" }[s.status] || "grey";
				const detail = s.error || s.detail || (s.result ? JSON.stringify(s.result) : "");
				return `<tr>
					<td><span class="indicator-pill ${color}">${frappe.utils.escape_html(s.status)}</span></td>
					<td>${frappe.utils.escape_html(s.label)}</td>
					<td style="font-size:11px;color:var(--text-muted)">${frappe.utils.escape_html(detail)}</td>
				</tr>`;
			})
			.join("");

		frappe.msgprint({
			title: rep.ok ? __("Setup Complete") : __("Setup Finished with Problems"),
			indicator: rep.ok ? "green" : "orange",
			wide: true,
			message: `<table class="table table-bordered" style="font-size:12px">
				<thead><tr><th style="width:90px">${__("Status")}</th><th>${__("Stage")}</th>
				<th>${__("Detail")}</th></tr></thead><tbody>${rows}</tbody></table>
				${rep.ok ? "" : `<p class="text-muted small">${__("Failed stages are safe to retry — re-run the setup once the cause is fixed. Full tracebacks are in the Error Log.")}</p>`}`,
		});
	},

	ask_brand(frm) {
		const d = new frappe.ui.Dialog({
			title: __("Name your water brand"),
			fields: [
				{
					fieldtype: "HTML",
					options: `<p class="text-muted small">${__(
						"Every finished-goods item is named from this, for example <b>&lt;brand&gt; 600 ml Bottle</b>. Item codes never contain the brand, so it can be changed later without affecting any transaction."
					)}</p>`,
				},
				{
					fieldname: "brand", fieldtype: "Data", label: __("Brand Name"), reqd: 1,
					default: frm.doc.brand_name || frm.doc.company,
				},
				{ fieldname: "brand_ar", fieldtype: "Data", label: __("Brand Name (Arabic)") },
				{
					fieldname: "brand_code", fieldtype: "Data", label: __("Short Code"),
					description: __("Used in batch numbers. Left empty, it is derived from the brand."),
				},
				{ fieldtype: "Section Break" },
				{ fieldname: "preview", fieldtype: "HTML" },
			],
			primary_action_label: __("Use this brand and run setup"),
			primary_action: (v) => {
				d.hide();
				frm.set_value("brand_name", v.brand);
				if (v.brand_ar) frm.set_value("brand_name_ar", v.brand_ar);
				if (v.brand_code) frm.set_value("brand_code", v.brand_code);
				frm.save().then(() => frm.trigger("run_setup"));
			},
		});

		const refresh_preview = () => {
			frappe.call({
				method: "neoaqua.setup.brand.preview_brand",
				args: { brand: d.get_value("brand") },
				callback(r) {
					const m = r.message || {};
					d.fields_dict.preview.$wrapper.html(`
						<div class="text-muted small">${__("Items will be created as:")}</div>
						<table class="table table-bordered" style="font-size:12px;margin-top:6px">
							${(m.sample || [])
								.map(
									(x) => `<tr><td style="font-family:Consolas,monospace">${frappe.utils.escape_html(x.item_code)}</td>
									<td>${frappe.utils.escape_html(x.item_name)}</td></tr>`
								)
								.join("")}
						</table>
						<div class="text-muted small">${__("Batch short code:")}
							<b style="font-family:Consolas,monospace">${frappe.utils.escape_html(m.brand_code || "")}</b></div>
					`);
				},
			});
		};
		d.fields_dict.brand.$input && d.fields_dict.brand.$input.on("keyup", frappe.utils.debounce(refresh_preview, 250));
		d.show();
		setTimeout(refresh_preview, 150);
	},

	rename_brand(frm) {
		const d = new frappe.ui.Dialog({
			title: __("Rename the brand"),
			fields: [
				{
					fieldtype: "HTML",
					options: `<p class="text-muted small">${__(
						"Only display names change. Item codes, BOMs, batches, stock and every posted transaction are untouched."
					)}</p>`,
				},
				{ fieldname: "current", fieldtype: "Data", label: __("Current"), read_only: 1,
				  default: frm.doc.brand_name },
				{ fieldname: "brand", fieldtype: "Data", label: __("New Brand Name"), reqd: 1 },
				{ fieldname: "brand_ar", fieldtype: "Data", label: __("Brand Name (Arabic)"),
				  default: frm.doc.brand_name_ar },
				{ fieldname: "brand_code", fieldtype: "Data", label: __("Short Code") },
			],
			primary_action_label: __("Rename"),
			primary_action: (v) => {
				frappe.call({
					method: "neoaqua.setup.brand.rename_brand",
					args: { new_brand: v.brand, new_brand_ar: v.brand_ar, new_brand_code: v.brand_code },
					freeze: true,
					freeze_message: __("Renaming items..."),
					callback(r) {
						d.hide();
						frappe.msgprint({
							title: __("Brand Renamed"),
							indicator: "green",
							message: (r.message || {}).message,
						});
						frm.reload_doc();
					},
				});
			},
		});
		d.show();
	},

	load_status(frm) {
		frappe.call({
			method: "neoaqua.setup.orchestrator.status",
			args: { company: frm.doc.company },
			callback(r) {
				const res = r.message || {};
				const rows = (res.checks || [])
					.map(
						(c) => `<tr>
							<td style="width:22px">${c.ok ? "&#10003;" : "&#10007;"}</td>
							<td>${frappe.utils.escape_html(c.check)}</td>
							<td style="text-align:right;font-variant-numeric:tabular-nums">
								<b style="color:${c.ok ? "var(--green-600)" : "var(--red-600)"}">${c.actual}</b>
								<span class="text-muted"> / ${c.expected}</span></td>
						</tr>`
					)
					.join("");

				const banner = res.complete
					? `<div class="alert alert-success" style="margin-bottom:10px">
							<b>${__("Plant setup is complete.")}</b> ${__("You can start transacting.")}</div>`
					: `<div class="alert alert-warning" style="margin-bottom:10px">
							<b>${__("Plant setup is incomplete.")}</b>
							${__("Use <b>Run Plant Setup</b> above to create what is missing.")}</div>`;

				$(frm.fields_dict.setup_board.wrapper).html(`
					${banner}
					<table class="table table-bordered" style="font-size:12px;max-width:520px">
						<tbody>${rows}</tbody>
					</table>
				`);
			},
		});
	},
});
