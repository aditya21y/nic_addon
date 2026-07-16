// Copyright (c) 2026, aditya&bagas and contributors
// For license information, please see license.txt

frappe.ui.form.on("Discipline", {
	setup(frm) {
		// The Sales Order line item must be a non-stock (service) item.
		frm.set_query("item", () => ({
			filters: { is_stock_item: 0 },
		}));
	},
});
