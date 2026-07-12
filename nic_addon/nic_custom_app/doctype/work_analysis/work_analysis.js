// Copyright (c) 2026, aditya&bagas and contributors
// For license information, please see license.txt

frappe.ui.form.on("Work Analysis", {
	setup(frm) {
		// analysis_code (Composite only) may only point at non-stock items.
		frm.set_query("analysis_code", () => ({
			filters: { is_stock_item: 0 },
		}));
	},
	posting_date(frm) {
		(frm.doc.components || []).forEach((row) => {
			fetch_component_price(frm, row.doctype, row.name);
		});
	},
	analysis_type(frm) {
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

function recalc_amounts(frm) {
	const rows = frm.doc.components || [];
	const is_simple = frm.doc.analysis_type === "Simple";

	// First pass: qty × rate subtotals are the bases the percentages apply to.
	let material_base = 0;
	let labor_base = 0;
	rows.forEach((c) => {
		const qty = is_simple ? 1 : flt(c.qty);
		material_base += qty * flt(c.material_rate);
		labor_base += qty * flt(c.labor_rate);
	});

	// Second pass: each row is qty × rate PLUS its percentage of the base.
	rows.forEach((c) => {
		const qty = is_simple ? 1 : flt(c.qty);
		c.amount_material = flt(qty * flt(c.material_rate) + (flt(c.material_percentage) / 100) * material_base);
		c.amount_labor = flt(qty * flt(c.labor_rate) + (flt(c.labor_percentage) / 100) * labor_base);
	});

	const total_material = rows.reduce((s, c) => s + flt(c.amount_material), 0);
	const total_labor = rows.reduce((s, c) => s + flt(c.amount_labor), 0);
	frm.set_value("out_material_rate", total_material);
	frm.set_value("out_labor_rate", total_labor);
	frm.set_value("out_total_rate", total_material + total_labor);
	frm.refresh_field("components");
}

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
		args: {
			item_code: row.item_code,
			posting_date: frm.doc.posting_date,
		},
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
