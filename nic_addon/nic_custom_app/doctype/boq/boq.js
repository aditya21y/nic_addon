// Copyright (c) 2026, aditya&bagas and contributors
// For license information, please see license.txt

frappe.ui.form.on("BoQ", {
	setup(frm) {
		frm.set_query("direct_cost", () => ({
			filters: { project: frm.doc.project || "", docstatus: 1 },
		}));
	},

	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.project) {
			frm.add_custom_button(__("Get Sections"), () => {
				frm.call("get_sections").then((r) => {
					frappe.show_alert({
						message: __("{0} section(s) linked to this BoQ", [r.message || 0]),
						indicator: "green",
					});
					frm.reload_doc();
				});
			});
		}
	},
});
