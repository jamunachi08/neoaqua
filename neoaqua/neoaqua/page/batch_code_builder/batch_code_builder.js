// Copyright (c) 2026, Neotec Integrated Solutions
/* eslint-disable no-console */

frappe.pages["batch-code-builder"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Batch Code Builder"),
		single_column: true,
	});
	new BatchCodeBuilder(page);
};

class BatchCodeBuilder {
	constructor(page) {
		this.page = page;
		this.segments = [];
		this.palette = [];
		this.rule = null;
		this.settings = {
			default_separator: "-",
			force_uppercase: 1,
			max_length: 0,
			set_expiry_from_shelf_life: 1,
		};
		this.sample = { item_code: null, production_line: "Line 1 - Small PET", shift: "A" };
		this.setup();
	}

	async setup() {
		this.build_toolbar();
		this.build_layout();
		this.palette = await frappe
			.call("neoaqua.manufacturing.batch_naming.get_segment_palette")
			.then((r) => r.message || []);
		this.render_palette();
		this.render_segments();
		this.refresh_preview();
	}

	// ------------------------------------------------------------ toolbar
	build_toolbar() {
		this.rule_field = this.page.add_field({
			fieldname: "rule",
			label: __("Load Existing Rule"),
			fieldtype: "Link",
			options: "Batch Naming Rule",
			change: () => this.load_rule(this.rule_field.get_value()),
		});

		this.item_field = this.page.add_field({
			fieldname: "sample_item",
			label: __("Sample Item"),
			fieldtype: "Link",
			options: "Item",
			get_query: () => ({ filters: { has_batch_no: 1 } }),
			change: () => {
				this.sample.item_code = this.item_field.get_value();
				this.refresh_preview();
			},
		});

		this.line_field = this.page.add_field({
			fieldname: "sample_line",
			label: __("Sample Line"),
			fieldtype: "Select",
			options: ["Line 1 - Small PET", "Line 2 - Large PET", "Line 3 - 5 Gallon", "RO Plant"],
			default: "Line 1 - Small PET",
			change: () => {
				this.sample.production_line = this.line_field.get_value();
				this.refresh_preview();
			},
		});

		this.page.set_primary_action(__("Save as Rule"), () => this.save_rule(), "add");
		this.page.add_menu_item(__("Test All Combinations"), () => this.show_combinations());
		this.page.add_menu_item(__("Load a Preset"), () => this.show_presets());
		this.page.add_menu_item(__("Decode an Existing Batch"), () => this.show_decoder());
		this.page.add_menu_item(__("Clear Canvas"), () => {
			this.segments = [];
			this.rule = null;
			this.render_segments();
			this.refresh_preview();
		});
	}

	build_layout() {
		this.page.main.html(`
			<div class="na-builder">
				<div class="na-preview-bar">
					<div class="na-preview-label">${__("Live Preview")}</div>
					<div class="na-preview-code" id="na-code">${__("Add a segment to begin")}</div>
					<div class="na-preview-meta" id="na-meta"></div>
				</div>
				<div class="na-grid">
					<div class="na-col">
						<div class="na-col-title">${__("Segment Palette")}</div>
						<div class="na-hint">${__("Click a segment to append it to the code.")}</div>
						<div id="na-palette" class="na-palette"></div>
					</div>
					<div class="na-col na-col-wide">
						<div class="na-col-title">${__("Code Composition")}</div>
						<div class="na-hint">${__("Segments are concatenated left to right.")}</div>
						<div id="na-segments" class="na-segments"></div>
						<div class="na-col-title" style="margin-top:20px">${__("Rule Options")}</div>
						<div id="na-options" class="na-options"></div>
					</div>
				</div>
			</div>
		`);
		this.inject_styles();
		this.render_options();
	}

	inject_styles() {
		if (document.getElementById("na-builder-styles")) return;
		const css = `
		.na-builder { padding: 4px 0 40px; }
		.na-preview-bar { background: linear-gradient(135deg,#13293D,#1B98E0); color:#fff;
			border-radius:10px; padding:18px 22px; margin-bottom:20px; }
		.na-preview-label { font-size:11px; text-transform:uppercase; letter-spacing:.08em; opacity:.75; }
		.na-preview-code { font-family: Consolas,Menlo,monospace; font-size:32px; font-weight:600;
			letter-spacing:.02em; margin:6px 0 4px; word-break:break-all; }
		.na-preview-meta { font-size:12px; opacity:.85; }
		.na-grid { display:flex; gap:20px; align-items:flex-start; flex-wrap:wrap; }
		.na-col { flex:1 1 260px; min-width:260px; }
		.na-col-wide { flex:2 1 480px; }
		.na-col-title { font-weight:600; font-size:13px; margin-bottom:2px; color:#13293D; }
		.na-hint { font-size:11px; color:var(--text-muted); margin-bottom:10px; }
		.na-palette { display:flex; flex-direction:column; gap:4px; max-height:620px; overflow-y:auto;
			border:1px solid var(--border-color); border-radius:8px; padding:8px; }
		.na-chip { border:1px solid var(--border-color); border-radius:6px; padding:7px 10px;
			cursor:pointer; background:var(--card-bg); transition:.12s; }
		.na-chip:hover { border-color:#1B98E0; background:#E8F4FB; }
		.na-chip .t { font-size:12px; font-weight:600; }
		.na-chip .s { font-family:Consolas,monospace; font-size:11px; color:#1B98E0; }
		.na-chip .d { font-size:11px; color:var(--text-muted); }
		.na-segments { display:flex; flex-direction:column; gap:8px; }
		.na-seg { border:1px solid var(--border-color); border-left:3px solid #1B98E0;
			border-radius:8px; padding:10px 12px; background:var(--card-bg); }
		.na-seg-head { display:flex; align-items:center; gap:8px; }
		.na-seg-idx { font-size:11px; color:var(--text-muted); width:18px; }
		.na-seg-type { font-weight:600; font-size:13px; flex:1; }
		.na-seg-val { font-family:Consolas,monospace; font-size:13px; color:#1B98E0;
			background:#E8F4FB; padding:1px 7px; border-radius:4px; }
		.na-seg-opts { display:flex; gap:10px; flex-wrap:wrap; margin-top:8px; }
		.na-seg-opts label { font-size:10px; text-transform:uppercase; letter-spacing:.04em;
			color:var(--text-muted); display:block; margin-bottom:2px; }
		.na-seg-opts .f { min-width:110px; }
		.na-seg-opts input, .na-seg-opts select { width:100%; font-size:12px; padding:3px 6px;
			border:1px solid var(--border-color); border-radius:4px; background:var(--control-bg); }
		.na-btn-mini { border:none; background:none; cursor:pointer; color:var(--text-muted);
			font-size:14px; padding:0 4px; }
		.na-btn-mini:hover { color:#13293D; }
		.na-empty { border:1px dashed var(--border-color); border-radius:8px; padding:28px;
			text-align:center; color:var(--text-muted); font-size:12px; }
		.na-options { display:flex; gap:14px; flex-wrap:wrap; border:1px solid var(--border-color);
			border-radius:8px; padding:12px; }
		.na-options .f { min-width:130px; }
		.na-options label { font-size:10px; text-transform:uppercase; letter-spacing:.04em;
			color:var(--text-muted); display:block; margin-bottom:2px; }
		.na-options input, .na-options select { width:100%; font-size:12px; padding:3px 6px;
			border:1px solid var(--border-color); border-radius:4px; background:var(--control-bg); }
		.na-warn { color:#B54708; font-size:12px; margin-top:6px; }
		`;
		$(`<style id="na-builder-styles">${css}</style>`).appendTo("head");
	}

	// ------------------------------------------------------------ palette
	render_palette() {
		const $p = $("#na-palette").empty();
		this.palette.forEach((seg) => {
			$(`
				<div class="na-chip">
					<div class="t">${frappe.utils.escape_html(seg.type)}
						<span class="s">${frappe.utils.escape_html(seg.sample)}</span></div>
					<div class="d">${frappe.utils.escape_html(seg.description)}</div>
				</div>
			`)
				.appendTo($p)
				.on("click", () => this.add_segment(seg));
		});
	}

	add_segment(paletteEntry) {
		const seg = {
			segment_type: paletteEntry.type,
			fixed_text: paletteEntry.type === "Fixed Text" ? "NAQ" : "",
			length: paletteEntry.type === "Sequence Counter" ? 3 : 0,
			pad_char: "0",
			transform: "None",
			separator_after: null,
			counter_scope: paletteEntry.type === "Sequence Counter" ? "Per Line per Shift per Day" : null,
			counter_start: 1,
			source_doctype: "Item",
			source_fieldname: "",
			fallback: "",
			is_mandatory: 0,
			use_value_map: 0,
			value_map: [],
			_options: paletteEntry.options || [],
		};
		this.segments.push(seg);
		this.render_segments();
		this.refresh_preview();
	}

	// ------------------------------------------------------------ segments
	render_segments() {
		const $s = $("#na-segments").empty();
		if (!this.segments.length) {
			$s.html(`<div class="na-empty">${__("No segments yet. Pick one from the palette on the left.")}</div>`);
			return;
		}

		this.segments.forEach((seg, i) => {
			const $row = $(`
				<div class="na-seg">
					<div class="na-seg-head">
						<span class="na-seg-idx">${i + 1}</span>
						<span class="na-seg-type">${frappe.utils.escape_html(seg.segment_type)}</span>
						<span class="na-seg-val" data-preview="${i}">…</span>
						<button class="na-btn-mini" data-up="${i}" title="${__("Move up")}">&#9650;</button>
						<button class="na-btn-mini" data-down="${i}" title="${__("Move down")}">&#9660;</button>
						<button class="na-btn-mini" data-del="${i}" title="${__("Remove")}">&#10005;</button>
					</div>
					<div class="na-seg-opts" data-opts="${i}"></div>
				</div>
			`).appendTo($s);

			this.render_segment_options($row.find(`[data-opts="${i}"]`), seg, i);
		});

		$s.find("[data-del]").on("click", (e) => {
			this.segments.splice(+$(e.currentTarget).data("del"), 1);
			this.render_segments();
			this.refresh_preview();
		});
		$s.find("[data-up]").on("click", (e) => this.move(+$(e.currentTarget).data("up"), -1));
		$s.find("[data-down]").on("click", (e) => this.move(+$(e.currentTarget).data("down"), 1));
	}

	move(i, delta) {
		const j = i + delta;
		if (j < 0 || j >= this.segments.length) return;
		[this.segments[i], this.segments[j]] = [this.segments[j], this.segments[i]];
		this.render_segments();
		this.refresh_preview();
	}

	render_segment_options($c, seg, i) {
		const opts = seg._options || [];
		const field = (label, key, type, choices) => {
			const id = `seg-${i}-${key}`;
			let input;
			if (type === "select") {
				input = `<select id="${id}">${choices
					.map((c) => `<option value="${c}" ${seg[key] === c ? "selected" : ""}>${c}</option>`)
					.join("")}</select>`;
			} else if (type === "check") {
				input = `<input type="checkbox" id="${id}" ${seg[key] ? "checked" : ""}>`;
			} else {
				input = `<input type="${type}" id="${id}" value="${seg[key] == null ? "" : seg[key]}">`;
			}
			$(`<div class="f"><label>${label}</label>${input}</div>`).appendTo($c);
			$c.find(`#${id}`).on("change keyup", (e) => {
				const el = e.currentTarget;
				seg[key] = type === "check" ? (el.checked ? 1 : 0) : type === "number" ? cint(el.value) : el.value;
				this.refresh_preview();
			});
		};

		if (opts.includes("fixed_text")) field(__("Text"), "fixed_text", "text");
		if (opts.includes("length")) field(__("Length"), "length", "number");
		if (opts.includes("pad_char")) field(__("Pad"), "pad_char", "text");
		if (opts.includes("transform"))
			field(__("Transform"), "transform", "select", ["None", "UPPERCASE", "lowercase", "Strip Non-Alphanumeric"]);
		if (opts.includes("counter_scope"))
			field(__("Counter Scope"), "counter_scope", "select", [
				"Global", "Per Year", "Per Month", "Per Day", "Per Item",
				"Per Item per Day", "Per Line per Day", "Per Line per Shift per Day",
			]);
		if (opts.includes("counter_start")) field(__("Starts At"), "counter_start", "number");
		if (opts.includes("source_doctype"))
			field(__("Source"), "source_doctype", "select", ["Item", "Work Order", "Batch", "Stock Entry"]);
		if (opts.includes("source_fieldname")) field(__("Fieldname"), "source_fieldname", "text");
		if (opts.includes("fallback")) field(__("Fallback"), "fallback", "text");

		field(__("Separator After"), "separator_after", "text");

		if (opts.includes("use_value_map")) {
			field(__("Use Map"), "use_value_map", "check");
			$(`<div class="f"><label>&nbsp;</label>
				<button class="btn btn-xs btn-default">${__("Edit Map")} (${(seg.value_map || []).length})</button></div>`)
				.appendTo($c)
				.find("button")
				.on("click", () => this.edit_value_map(seg));
		}
	}

	edit_value_map(seg) {
		const d = new frappe.ui.Dialog({
			title: __("Value Map — {0}", [seg.segment_type]),
			size: "large",
			fields: [
				{
					fieldtype: "HTML",
					options: `<p class="text-muted small">${__(
						"Map the raw source value to the short code that should appear in the batch. Anything not mapped passes through unchanged."
					)}</p>`,
				},
				{
					fieldname: "rows",
					fieldtype: "Table",
					cannot_add_rows: false,
					in_place_edit: true,
					data: seg.value_map || [],
					get_data: () => seg.value_map || [],
					fields: [
						{ fieldname: "source_value", fieldtype: "Data", label: __("Source Value"), in_list_view: 1, columns: 5 },
						{ fieldname: "code", fieldtype: "Data", label: __("Code"), in_list_view: 1, columns: 3 },
						{ fieldname: "description", fieldtype: "Data", label: __("Note"), in_list_view: 1, columns: 3 },
					],
				},
			],
			primary_action_label: __("Apply"),
			primary_action: () => {
				seg.value_map = (d.get_value("rows") || []).map((r) => ({
					source_value: r.source_value,
					code: r.code,
					description: r.description,
				}));
				seg.use_value_map = seg.value_map.length ? 1 : 0;
				d.hide();
				this.render_segments();
				this.refresh_preview();
			},
		});

		if (seg.segment_type === "Production Line Code" && !(seg.value_map || []).length) {
			d.fields_dict.rows.df.data = [
				{ source_value: "Line 1 - Small PET", code: "L1" },
				{ source_value: "Line 2 - Large PET", code: "L2" },
				{ source_value: "Line 3 - 5 Gallon", code: "L3" },
				{ source_value: "RO Plant", code: "RO" },
			];
		}
		d.show();
	}

	// ------------------------------------------------------------ options
	render_options() {
		const $o = $("#na-options").empty();
		const field = (label, key, type, choices) => {
			const id = `opt-${key}`;
			let input;
			if (type === "check") {
				input = `<input type="checkbox" id="${id}" ${this.settings[key] ? "checked" : ""}>`;
			} else if (type === "select") {
				input = `<select id="${id}">${choices
					.map((c) => `<option ${this.settings[key] === c ? "selected" : ""}>${c}</option>`)
					.join("")}</select>`;
			} else {
				input = `<input type="${type}" id="${id}" value="${this.settings[key] ?? ""}">`;
			}
			$(`<div class="f"><label>${label}</label>${input}</div>`).appendTo($o);
			$o.find(`#${id}`).on("change keyup", (e) => {
				const el = e.currentTarget;
				this.settings[key] = type === "check" ? (el.checked ? 1 : 0) : type === "number" ? cint(el.value) : el.value;
				this.refresh_preview();
			});
		};
		field(__("Default Separator"), "default_separator", "text");
		field(__("Max Length"), "max_length", "number");
		field(__("Force Uppercase"), "force_uppercase", "check");
		field(__("Expiry from Shelf Life"), "set_expiry_from_shelf_life", "check");
	}

	// ------------------------------------------------------------ preview
	as_rule_doc(name) {
		// No `name` key: this is an unsaved draft, and sending a placeholder
		// primary key invites the server to treat it as a stored record.
		return {
			doctype: "Batch Naming Rule",
			rule_name: name || "Draft Rule",
			company: frappe.defaults.get_user_default("Company"),
			is_active: 1,
			priority: 0,
			applies_to: "All Items",
			default_separator: this.settings.default_separator,
			max_length: this.settings.max_length,
			force_uppercase: this.settings.force_uppercase,
			set_expiry_from_shelf_life: this.settings.set_expiry_from_shelf_life,
			segments: this.segments.map((s, i) => ({
				doctype: "Batch Naming Segment",
				idx: i + 1,
				segment_type: s.segment_type,
				fixed_text: s.fixed_text,
				length: s.length,
				pad_char: s.pad_char,
				transform: s.transform,
				separator_after: s.separator_after,
				counter_scope: s.counter_scope,
				counter_start: s.counter_start,
				source_doctype: s.source_doctype,
				source_fieldname: s.source_fieldname,
				fallback: s.fallback,
				is_mandatory: s.is_mandatory,
				use_value_map: s.use_value_map,
				value_map: (s.value_map || []).map((v) => ({
					doctype: "Batch Segment Value Map",
					source_value: v.source_value,
					code: v.code,
					description: v.description,
				})),
			})),
		};
	}

	refresh_preview() {
		if (!this.segments.length) {
			$("#na-code").text(__("Add a segment to begin"));
			$("#na-meta").text("");
			return;
		}
		// The preview fires on every keystroke; debounce so a long value does
		// not queue a dozen round trips.
		clearTimeout(this._preview_timer);
		this._preview_timer = setTimeout(() => this._do_preview(), 180);
	}

	_do_preview() {
		frappe.call({
			method: "neoaqua.manufacturing.batch_naming.preview_rule",
			args: {
				rule: this.as_rule_doc(),
				item_code: this.sample.item_code,
				production_line: this.sample.production_line,
				shift: this.sample.shift,
			},
			error: () => {
				$("#na-code").text("—");
				$("#na-meta").text(__("Preview unavailable — check the segment options."));
			},
			callback: (r) => {
				const m = r.message || {};
				$("#na-code").text(m.code || "—");
				let meta = __("{0} characters", [m.length || 0]);
				if (m.item_code) meta += ` · ${m.item_code}`;
				if (m.expiry) meta += ` · ${__("expires")} ${m.expiry}`;
				if (m.max_length_exceeded) meta += ` · ⚠ ${__("exceeds max length")}`;
				$("#na-meta").text(meta);
				(m.segments || []).forEach((s, i) => {
					$(`[data-preview="${i}"]`).text(s.value || "∅");
				});
			},
		});
	}

	// ------------------------------------------------------------ combinations
	show_combinations() {
		if (!this.segments.length) {
			frappe.msgprint(__("Compose a code first."));
			return;
		}
		const d = new frappe.ui.Dialog({
			title: __("Combination Explorer"),
			size: "extra-large",
			fields: [
				{ fieldname: "items", fieldtype: "MultiSelectList", label: __("Items"),
				  get_data: (txt) => frappe.db.get_link_options("Item", txt, { has_batch_no: 1 }) },
				{ fieldname: "cb", fieldtype: "Column Break" },
				{ fieldname: "lines", fieldtype: "MultiSelectPills", label: __("Production Lines"),
				  get_data: () => ["Line 1 - Small PET", "Line 2 - Large PET", "Line 3 - 5 Gallon", "RO Plant"] },
				{ fieldname: "shifts", fieldtype: "MultiSelectPills", label: __("Shifts"),
				  get_data: () => ["A", "B", "C"] },
				{ fieldname: "sb", fieldtype: "Section Break" },
				{ fieldname: "result", fieldtype: "HTML" },
			],
			primary_action_label: __("Generate Matrix"),
			primary_action: () => {
				frappe.call({
					method: "neoaqua.manufacturing.batch_naming.generate_combinations",
					args: {
						rule: this.as_rule_doc(),
						items: d.get_value("items") || [],
						production_lines: d.get_value("lines") || [],
						shifts: d.get_value("shifts") || [],
					},
					error: () => {
						d.fields_dict.result.$wrapper.html(
							`<p class="text-muted">${__("Could not build the matrix. Check the segment options and try again.")}</p>`
						);
					},
					callback: (r) => this.render_matrix(d.fields_dict.result.$wrapper, r.message || {}),
				});
			},
		});
		d.show();
		setTimeout(() => d.get_primary_btn().trigger("click"), 250);
	}

	render_matrix($wrapper, data) {
		const rows = (data.rows || [])
			.map(
				(r) => `<tr${r.collides_with ? ' style="background:#FEF3F2"' : ""}>
					<td>${frappe.utils.escape_html(r.item_code)}</td>
					<td>${frappe.utils.escape_html(r.production_line)}</td>
					<td style="text-align:center">${frappe.utils.escape_html(r.shift)}</td>
					<td style="font-family:Consolas,monospace;font-weight:600">${frappe.utils.escape_html(r.batch_code)}</td>
					<td style="text-align:center">${r.length}</td>
					<td style="color:#B42318;font-size:11px">${r.collides_with ? frappe.utils.escape_html(r.collides_with) : ""}</td>
				</tr>`
			)
			.join("");

		$wrapper.html(`
			<div style="margin-bottom:10px">
				<span class="indicator-pill blue">${__("{0} combinations", [data.total || 0])}</span>
				<span class="indicator-pill ${data.collisions ? "red" : "green"}">
					${__("{0} distinct codes", [data.distinct || 0])}</span>
			</div>
			${data.warning ? `<div class="na-warn">⚠ ${frappe.utils.escape_html(data.warning)}</div>` : ""}
			<div style="max-height:420px;overflow:auto;margin-top:10px">
				<table class="table table-bordered" style="font-size:12px">
					<thead><tr>
						<th>${__("Item")}</th><th>${__("Line")}</th><th>${__("Shift")}</th>
						<th>${__("Batch Code")}</th><th>${__("Len")}</th><th>${__("Collides With")}</th>
					</tr></thead>
					<tbody>${rows}</tbody>
				</table>
			</div>
		`);
	}

	// ------------------------------------------------------------ presets
	show_presets() {
		const presets = {
			"Plant · Date · Line · Shift · Counter": [
				{ type: "Plant Code", fixed_text: "RUH" },
				{ type: "Date (YYMMDD)" },
				{ type: "Production Line Code", length: 2, use_value_map: 1, map: "line" },
				{ type: "Shift Code", length: 1 },
				{ type: "Sequence Counter", length: 3, counter_scope: "Per Line per Shift per Day" },
			],
			"Item · Julian Day · Year · Counter": [
				{ type: "Item Batch Code", length: 4 },
				{ type: "Julian Day (DDD)" },
				{ type: "Year (YY)" },
				{ type: "Sequence Counter", length: 3, counter_scope: "Per Item per Day" },
			],
			"Compact coder line (no separators)": [
				{ type: "Month (Letter A-L)" },
				{ type: "Day (DD)" },
				{ type: "Year (YY)" },
				{ type: "Production Line Code", length: 1, use_value_map: 1, map: "line" },
				{ type: "Sequence Counter", length: 4, counter_scope: "Per Day" },
			],
			"Manufacture + Expiry encoded": [
				{ type: "Item Batch Code", length: 4 },
				{ type: "Date (YYMMDD)" },
				{ type: "Expiry (YYMMDD)" },
				{ type: "Sequence Counter", length: 2, counter_scope: "Per Item per Day" },
			],
		};

		const d = new frappe.ui.Dialog({
			title: __("Load a Preset"),
			fields: [
				{
					fieldname: "preset",
					fieldtype: "Select",
					label: __("Preset"),
					options: Object.keys(presets),
					reqd: 1,
				},
				{
					fieldtype: "HTML",
					options: `<p class="text-muted small">${__(
						"Loading a preset replaces whatever is on the canvas."
					)}</p>`,
				},
			],
			primary_action_label: __("Load"),
			primary_action: (v) => {
				const spec = presets[v.preset];
				this.settings.default_separator = v.preset.includes("no separators") ? "" : "-";
				this.segments = spec.map((s) => {
					const p = this.palette.find((x) => x.type === s.type) || { options: [] };
					return {
						segment_type: s.type,
						fixed_text: s.fixed_text || "",
						length: s.length || 0,
						pad_char: "0",
						transform: "None",
						separator_after: null,
						counter_scope: s.counter_scope || null,
						counter_start: 1,
						source_doctype: "Item",
						source_fieldname: "",
						fallback: "",
						is_mandatory: 0,
						use_value_map: s.use_value_map || 0,
						value_map:
							s.map === "line"
								? [
										{ source_value: "Line 1 - Small PET", code: "L1" },
										{ source_value: "Line 2 - Large PET", code: "L2" },
										{ source_value: "Line 3 - 5 Gallon", code: "L3" },
										{ source_value: "RO Plant", code: "RO" },
								  ]
								: [],
						_options: p.options,
					};
				});
				d.hide();
				this.render_options();
				this.render_segments();
				this.refresh_preview();
			},
		});
		d.show();
	}

	// ------------------------------------------------------------ decoder
	show_decoder() {
		const d = new frappe.ui.Dialog({
			title: __("Decode a Batch Code"),
			fields: [
				{ fieldname: "batch", fieldtype: "Link", options: "Batch", label: __("Batch"), reqd: 1 },
				{ fieldname: "out", fieldtype: "HTML" },
			],
			primary_action_label: __("Decode"),
			primary_action: (v) => {
				frappe.call({
					method: "neoaqua.manufacturing.batch_naming.decode_batch",
					args: { batch_id: v.batch },
					callback: (r) => {
						const m = r.message || {};
						if (!m.decoded) {
							d.fields_dict.out.$wrapper.html(
								`<p class="text-muted">${frappe.utils.escape_html(m.message || "")}</p>`
							);
							return;
						}
						d.fields_dict.out.$wrapper.html(`
							<table class="table table-bordered" style="font-size:12px">
								<thead><tr><th>${__("Segment")}</th><th>${__("Value")}</th></tr></thead>
								<tbody>${m.decoded
									.map(
										(s) =>
											`<tr><td>${frappe.utils.escape_html(s.segment)}</td>
											<td style="font-family:Consolas,monospace">${frappe.utils.escape_html(s.value || "—")}</td></tr>`
									)
									.join("")}</tbody>
							</table>
						`);
					},
				});
			},
		});
		d.show();
	}

	// ------------------------------------------------------------ persistence
	async load_rule(name) {
		if (!name) return;
		const doc = await frappe.db.get_doc("Batch Naming Rule", name);
		this.rule = name;
		this.settings = {
			default_separator: doc.default_separator,
			force_uppercase: doc.force_uppercase,
			max_length: doc.max_length,
			set_expiry_from_shelf_life: doc.set_expiry_from_shelf_life,
		};
		this.segments = (doc.segments || []).map((s) => {
			const p = this.palette.find((x) => x.type === s.segment_type) || { options: [] };
			return { ...s, value_map: s.value_map || [], _options: p.options };
		});
		this.render_options();
		this.render_segments();
		this.refresh_preview();
		frappe.show_alert({ message: __("Loaded {0}", [name]), indicator: "green" });
	}

	save_rule() {
		if (!this.segments.length) {
			frappe.msgprint(__("Nothing to save."));
			return;
		}
		const d = new frappe.ui.Dialog({
			title: __("Save Batch Naming Rule"),
			fields: [
				{ fieldname: "rule_name", fieldtype: "Data", label: __("Rule Name"), reqd: 1, default: this.rule },
				{ fieldname: "applies_to", fieldtype: "Select", label: __("Applies To"), reqd: 1,
				  options: ["All Items", "Item", "Item Group", "Production Line"], default: "All Items" },
				{ fieldname: "item_code", fieldtype: "Link", options: "Item", label: __("Item"),
				  depends_on: 'eval:doc.applies_to=="Item"' },
				{ fieldname: "item_group", fieldtype: "Link", options: "Item Group", label: __("Item Group"),
				  depends_on: 'eval:doc.applies_to=="Item Group"' },
				{ fieldname: "production_line", fieldtype: "Select", label: __("Production Line"),
				  options: ["", "Line 1 - Small PET", "Line 2 - Large PET", "Line 3 - 5 Gallon", "RO Plant"],
				  depends_on: 'eval:doc.applies_to=="Production Line"' },
				{ fieldname: "priority", fieldtype: "Int", label: __("Priority"), default: 0 },
			],
			primary_action_label: __("Save"),
			primary_action: async (v) => {
				const payload = this.as_rule_doc(v.rule_name);
				Object.assign(payload, v);
				delete payload.name;
				try {
					const existing = await frappe.db.exists("Batch Naming Rule", v.rule_name);
					if (existing) {
						const doc = await frappe.db.get_doc("Batch Naming Rule", v.rule_name);
						Object.assign(doc, payload);
						await frappe.call("frappe.client.save", { doc });
					} else {
						await frappe.call("frappe.client.insert", { doc: payload });
					}
					d.hide();
					this.rule = v.rule_name;
					frappe.show_alert({ message: __("Saved {0}", [v.rule_name]), indicator: "green" });
					frappe.set_route("Form", "Batch Naming Rule", v.rule_name);
				} catch (e) {
					frappe.msgprint({ title: __("Could not save"), message: e.message, indicator: "red" });
				}
			},
		});
		d.show();
	}
}
