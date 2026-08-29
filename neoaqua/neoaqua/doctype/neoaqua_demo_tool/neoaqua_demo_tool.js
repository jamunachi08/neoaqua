// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("NeoAqua Demo Tool", {
	refresh(frm) {
		frm.disable_save();

		if (!frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}

		frm.add_custom_button(__("Run Plant Setup"), () => frm.trigger("run_plant_setup"));
		frm.add_custom_button(__("Diagnose Setup"), () => frm.trigger("diagnose"), __("View"));
		frm.trigger("check_readiness");

		frm.add_custom_button(__("Generate Demo Data"), () => {
			frappe.confirm(
				__("This creates suppliers, customers, a procurement cycle, a five-level production run and three van sales days. Continue?"),
				() => {
					frappe.dom.freeze(__("Building demo data. This takes a minute..."));
					frm.call("generate_demo_data")
						.then((r) => {
							frappe.dom.unfreeze();
							const m = r.message || {};
							frappe.msgprint({
								title: __("Demo Data Created"),
								indicator: "green",
								message: __("Run {0} created {1} documents.", [m.run_id, m.documents]),
							});
							frm.reload_doc();
						})
						.catch(() => frappe.dom.unfreeze());
				}
			);
		}).addClass("btn-primary");

		frm.add_custom_button(__("What's on this site?"), () => {
			frm.call("summary").then((r) => {
				const runs = r.message || {};
				if (!Object.keys(runs).length) {
					frappe.msgprint(__("No demo data on this site."));
					return;
				}
				let html = "";
				for (const [run, rows] of Object.entries(runs)) {
					html += `<h5 style="margin-top:12px">${frappe.utils.escape_html(run)}</h5>
						<table class="table table-bordered" style="font-size:12px">
						<thead><tr><th>${__("DocType")}</th><th style="text-align:right">${__("Count")}</th></tr></thead>
						<tbody>${rows
							.map((x) => `<tr><td>${frappe.utils.escape_html(x.doctype)}</td>
								<td style="text-align:right">${x.count}</td></tr>`)
							.join("")}</tbody></table>`;
				}
				frappe.msgprint({ title: __("Demo Data on This Site"), message: html, wide: true });
			});
		}, __("View"));

		frm.add_custom_button(__("Delete Demo Data"), () => {
			if ((frm.doc.confirm_text || "").trim().toUpperCase() !== "DELETE") {
				frappe.msgprint({
					title: __("Confirmation Required"),
					indicator: "orange",
					message: __("Type DELETE in the confirmation field before running this."),
				});
				return;
			}
			frappe.confirm(
				__("Every document created by the demo runs will be cancelled and deleted, along with its ledger entries. Anything you entered yourself is untouched. Proceed?"),
				() => {
					frappe.dom.freeze(__("Removing demo data..."));
					frm.call("remove_demo_data")
						.then((r) => {
							frappe.dom.unfreeze();
							const m = r.message || {};
							let msg = `<p>${frappe.utils.escape_html(m.message || "")}</p>`;
							if (m.failures && m.failures.length) {
								msg += `<p class="text-muted small">${__("Could not remove:")}</p><ul style="font-size:12px">${m.failures
									.map((f) => `<li>${frappe.utils.escape_html(f)}</li>`)
									.join("")}</ul>`;
							}
							frappe.msgprint({
								title: __("Demo Data Removed"),
								indicator: m.failed ? "orange" : "green",
								message: msg,
								wide: true,
							});
							frm.reload_doc();
						})
						.catch(() => frappe.dom.unfreeze());
				}
			);
		}, __("Danger Zone")).addClass("btn-danger");

		frm.add_custom_button(__("Tidy Demo Log"), () => {
			frappe.call("neoaqua.setup.demo_cleanup.clear_demo_log").then((r) =>
				frappe.show_alert({
					message: __("{0} stale log rows removed", [(r.message || {}).removed || 0]),
					indicator: "blue",
				})
			);
		}, __("Danger Zone"));

	},

	// ---------------------------------------------------------------- setup
	check_readiness(frm) {
		frappe.call({
			method: "neoaqua.setup.orchestrator.status",
			args: { company: frm.doc.company },
			callback(r) {
				const res = r.message || {};
				frm.dashboard.clear_headline();
				if (res.complete) {
					frm.dashboard.set_headline(
						`<span class="indicator-pill green">${__("Plant is set up — demo data can be generated")}</span>`
					);
					return;
				}
				const missing = (res.checks || []).filter((c) => !c.ok);
				frm.dashboard.set_headline(
					`<div>
						<span class="indicator-pill orange">${__("Plant not set up")}</span>
						<span class="text-muted" style="margin-left:8px">
							${__("{0} of {1} checks failing — use Run Plant Setup first.", [
								missing.length, (res.checks || []).length,
							])}
						</span>
					</div>`
				);
			},
		});
	},

	run_plant_setup(frm) {
		if (!frm.doc.company) {
			frappe.msgprint(__("Select a Company first."));
			return;
		}
		frappe.confirm(
			__("This creates the item master, chart of accounts, BOM tree, vans, routes and dashboards for {0}. Safe to re-run. Continue?", [frm.doc.company]),
			() => {
				frappe.dom.freeze(__("Setting up the plant. This takes a minute..."));
				frm.call("run_plant_setup")
					.then((r) => {
						frappe.dom.unfreeze();
						const rep = r.message || {};
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
							title: rep.ok ? __("Plant Setup Complete") : __("Setup Finished with Problems"),
							indicator: rep.ok ? "green" : "orange",
							wide: true,
							message: `<table class="table table-bordered" style="font-size:12px">
								<thead><tr><th style="width:90px">${__("Status")}</th><th>${__("Stage")}</th>
								<th>${__("Detail")}</th></tr></thead><tbody>${rows}</tbody></table>
								${rep.ok ? `<p>${__("You can now generate demo data.")}</p>`
									: `<p class="text-muted small">${__("Use Diagnose Setup to see the underlying errors.")}</p>`}`,
						});
						frm.trigger("check_readiness");
					})
					.catch(() => frappe.dom.unfreeze());
			}
		);
	},

	diagnose(frm) {
		frm.call("diagnose").then((r) => {
			const d = r.message || {};
			const checks = ((d.status || {}).checks || [])
				.map(
					(c) => `<tr>
						<td style="width:22px">${c.ok ? "&#10003;" : "&#10007;"}</td>
						<td>${frappe.utils.escape_html(c.check)}</td>
						<td style="text-align:right">
							<b style="color:${c.ok ? "var(--green-600)" : "var(--red-600)"}">${c.actual}</b>
							<span class="text-muted"> / ${c.expected}</span></td>
					</tr>`
				)
				.join("");

			const failed = (d.failed_stages || [])
				.map(
					(s) => `<tr><td>${frappe.utils.escape_html(s.status)}</td>
						<td>${frappe.utils.escape_html(s.label)}</td>
						<td style="font-size:11px">${frappe.utils.escape_html(s.error || s.detail || "")}</td></tr>`
				)
				.join("");

			const errs = (d.errors || [])
				.map(
					(e) => `<tr><td style="white-space:nowrap;font-size:11px">${frappe.utils.escape_html(e.when.slice(0, 19))}</td>
						<td style="font-size:11px">${frappe.utils.escape_html(e.last_line)}</td></tr>`
				)
				.join("");

			let html = `<h5>${__("Checklist")}</h5>
				<table class="table table-bordered" style="font-size:12px">${checks}</table>`;
			if (failed) {
				html += `<h5 style="margin-top:16px">${__("Stages that did not complete")}</h5>
					<table class="table table-bordered" style="font-size:12px">${failed}</table>`;
			}
			if (errs) {
				html += `<h5 style="margin-top:16px">${__("Recent NeoAqua errors")}</h5>
					<table class="table table-bordered" style="font-size:12px">${errs}</table>`;
			}
			if ((d.companies || []).length > 1) {
				html += `<p class="text-muted small" style="margin-top:12px">${__(
					"This site has {0} companies: {1}. Setup applies to the one selected above.",
					[d.companies.length, d.companies.join(", ")]
				)}</p>`;
			}

			frappe.msgprint({ title: __("Setup Diagnosis"), message: html, wide: true });
		});
	},
});
