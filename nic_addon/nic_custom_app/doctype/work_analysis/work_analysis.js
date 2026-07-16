// Copyright (c) 2026, aditya&bagas and contributors
// For license information, please see license.txt

frappe.ui.form.on("Work Analysis", {
	setup(frm) {
		// analysis_code (Composite only) may only point at non-stock items.
		frm.set_query("analysis_code", () => ({
			filters: { is_stock_item: 0 },
		}));
		// A component may not be the assembly item itself (no self-reference).
		frm.set_query("item_code", "components", () => ({
			filters: { name: ["!=", frm.doc.analysis_code || ""] },
		}));
	},
	analysis_type(frm) {
		recalc_amounts(frm);
	},
	posting_date(frm) {
		// Re-price by posting date: the header item (Simple) or each component.
		if (frm.doc.analysis_type === "Simple") {
			fetch_simple_price(frm);
		} else {
			(frm.doc.components || []).forEach((row) => {
				fetch_component_price(frm, row.doctype, row.name);
			});
		}
	},

	// --- Composite: assembly keyed by analysis_code ---
	analysis_code(frm) {
		if (frm.doc.analysis_code) {
			frappe.db.get_value("Item", frm.doc.analysis_code, "stock_uom").then((r) => {
				if (r.message && r.message.stock_uom) {
					frm.set_value("uom", r.message.stock_uom);
					frm.refresh_field("uom");
				}
			});
		}
	},

	// --- Simple: header-driven single item ---
	item_code(frm) {
		if (frm.doc.item_code) {
			frappe.db.get_value("Item", frm.doc.item_code, "stock_uom").then((r) => {
				if (r.message && r.message.stock_uom) {
					frm.set_value("uom", r.message.stock_uom);
				}
			});
		}
		fetch_simple_price(frm);
	},
	material_rate(frm) {
		recalc_amounts(frm);
	},
	labor_rate(frm) {
		recalc_amounts(frm);
	},
	material_percentage(frm) {
		recalc_amounts(frm);
	},
	labor_percentage(frm) {
		recalc_amounts(frm);
	},
});

frappe.ui.form.on("Work Analysis Component", {
	item_code(frm, cdt, cdn) {
		fetch_component_price(frm, cdt, cdn);
	},
	qty(frm) {
		recalc_amounts(frm);
	},
	material_rate(frm) {
		recalc_amounts(frm);
	},
	labor_rate(frm) {
		recalc_amounts(frm);
	},
	material_percentage(frm) {
		recalc_amounts(frm);
	},
	labor_percentage(frm) {
		recalc_amounts(frm);
	},
	components_remove(frm) {
		recalc_amounts(frm);
	},
});

// Mirror of WorkAnalysis.calculate_amounts (server is authoritative on save).
function recalc_amounts(frm) {
	let out_material = 0;
	let out_labor = 0;

	if (frm.doc.analysis_type === "Simple") {
		out_material = flt(frm.doc.material_rate) * (1 + flt(frm.doc.material_percentage) / 100);
		out_labor = flt(frm.doc.labor_rate) * (1 + flt(frm.doc.labor_percentage) / 100);
	} else {
		const rows = frm.doc.components || [];
		let material_base = 0;
		let labor_base = 0;
		rows.forEach((c) => {
			material_base += flt(c.qty) * flt(c.material_rate);
			labor_base += flt(c.qty) * flt(c.labor_rate);
		});
		rows.forEach((c) => {
			c.amount_material = flt(flt(c.qty) * flt(c.material_rate) + (flt(c.material_percentage) / 100) * material_base);
			c.amount_labor = flt(flt(c.qty) * flt(c.labor_rate) + (flt(c.labor_percentage) / 100) * labor_base);
		});
		out_material = rows.reduce((s, c) => s + flt(c.amount_material), 0);
		out_labor = rows.reduce((s, c) => s + flt(c.amount_labor), 0);
		frm.refresh_field("components");
	}

	frm.set_value("out_material_rate", flt(out_material));
	frm.set_value("out_labor_rate", flt(out_labor));
	frm.set_value("out_total_rate", flt(out_material) + flt(out_labor));
}

// Simple: fetch the header material_rate from the valid Item Price on posting_date.
function fetch_simple_price(frm) {
	if (frm.doc.analysis_type !== "Simple" || !frm.doc.item_code) {
		return;
	}
	if (!frm.doc.posting_date) {
		frappe.msgprint(__("Please set the Posting Date first so the correct price can be fetched."));
		return;
	}
	frappe.call({
		method: "nic_addon.nic_custom_app.doctype.work_analysis.work_analysis.get_item_price",
		args: { item_code: frm.doc.item_code, posting_date: frm.doc.posting_date },
		callback(r) {
			if (r.message) {
				frm.set_value("item_price", r.message.item_price);
				frm.set_value("item_price_rate", r.message.price_list_rate);
				frm.set_value("material_rate", r.message.price_list_rate).then(() => recalc_amounts(frm));
			} else {
				frm.set_value("item_price", null);
				frm.set_value("item_price_rate", 0);
				frappe.show_alert({
					message: __("No valid buying price found for {0} on {1}", [
						frm.doc.item_code,
						frappe.datetime.str_to_user(frm.doc.posting_date),
					]),
					indicator: "orange",
				});
			}
		},
	});
}

// Composite: fetch a component's material_rate from the valid Item Price on posting_date.
function fetch_component_price(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item_code) {
		return;
	}
	if (!frm.doc.posting_date) {
		frappe.msgprint(__("Please set the Posting Date first so the correct price can be fetched."));
		return;
	}
	frappe.call({
		method: "nic_addon.nic_custom_app.doctype.work_analysis.work_analysis.get_item_price",
		args: { item_code: row.item_code, posting_date: frm.doc.posting_date },
		callback(r) {
			if (r.message) {
				frappe.model.set_value(cdt, cdn, "item_price", r.message.item_price);
				frappe.model.set_value(cdt, cdn, "item_price_rate", r.message.price_list_rate);
				frappe.model.set_value(cdt, cdn, "material_rate", r.message.price_list_rate).then(() => {
					recalc_amounts(frm);
				});
			} else {
				frappe.model.set_value(cdt, cdn, "item_price", null);
				frappe.model.set_value(cdt, cdn, "item_price_rate", 0);
				frappe.show_alert({
					message: __("No valid buying price found for {0} on {1}", [
						row.item_code,
						frappe.datetime.str_to_user(frm.doc.posting_date),
					]),
					indicator: "orange",
				});
			}
		},
	});
}
