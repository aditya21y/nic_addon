// Copyright (c) 2026, aditya&bagas and contributors
// For license information, please see license.txt

frappe.ui.form.on("BOQ Section", {
	setup(frm) {
		// Disciplines belong to a project; only show this project's active ones.
		frm.set_query("discipline", () => ({
			filters: {
				project: frm.doc.project || "",
				is_active: 1,
			},
		}));

		// Only offer Work Analyses that price the row's item, scoped to the project.
		frm.set_query("source_type", "items", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return {
				query: "nic_addon.nic_custom_app.doctype.boq_section.boq_section.work_analysis_query",
				filters: {
					project: frm.doc.project,
					item_code: row.item_code,
				},
			};
		});
	},
});

frappe.ui.form.on("Boq Item", {
	source_type(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.source_type) {
			return;
		}
		frappe.db
			.get_value("Work Analysis", row.source_type, [
				"analysis_type",
				"item_code",
				"analysis_code",
				"alias",
				"uom",
				"out_material_rate",
				"out_labor_rate",
			])
			.then((r) => {
				const wa = r.message;
				if (!wa) {
					return;
				}
				// Backfill item_code from whichever field the analysis uses.
				if (!row.item_code) {
					const resolved = wa.analysis_type === "Composite" ? wa.analysis_code : wa.item_code;
					frappe.model.set_value(cdt, cdn, "item_code", resolved);
				}
				frappe.model.set_value(cdt, cdn, "alias", wa.alias);
				frappe.model.set_value(cdt, cdn, "uom", wa.uom);
				frappe.model.set_value(cdt, cdn, "net_material", wa.out_material_rate);
				frappe.model.set_value(cdt, cdn, "net_labor", wa.out_labor_rate);
			});
	},
});
