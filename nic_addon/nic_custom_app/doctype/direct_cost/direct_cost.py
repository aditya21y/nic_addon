# Copyright (c) 2026, aditya&bagas and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt

# Category -> the header total field it rolls up into (RAPP APP.2 columns).
CATEGORY_TOTALS = {
	"Persiapan": "total_persiapan",
	"Mob-Demob & Test Com": "total_mobdemob",
	"Alat & Perlengkapan": "total_alat",
	"Management Proyek": "total_management",
}


class DirectCost(Document):
	def validate(self):
		self.calculate_totals()

	def calculate_totals(self):
		"""Value each line (qty x rate) and roll up per category into the four
		group totals that feed RAPP APP.2, plus the grand total."""
		totals = dict.fromkeys(CATEGORY_TOTALS.values(), 0.0)

		for line in self.lines:
			line.amount = flt(flt(line.qty) * flt(line.rate))
			field = CATEGORY_TOTALS.get(line.category)
			if field:
				totals[field] += line.amount

		for field, value in totals.items():
			self.set(field, flt(value))

		self.total_direct_cost = flt(sum(totals.values()))


@frappe.whitelist()
def get_direct_cost_totals(project=None, boq=None, direct_cost=None):
	"""Return the four APP.2 group totals for a submitted Direct Cost.

	Resolution priority: explicit `direct_cost` -> the one linked to `boq` ->
	the latest one for `project`. Consumed by the BoQ / RAPP engine."""
	name = direct_cost
	if not name and boq:
		name = frappe.db.get_value(
			"Direct Cost", {"docstatus": 1, "boq": boq}, "name", order_by="posting_date desc"
		)
	if not name and project:
		name = frappe.db.get_value(
			"Direct Cost", {"docstatus": 1, "project": project}, "name", order_by="posting_date desc"
		)
	if not name:
		return {}

	doc = frappe.db.get_value(
		"Direct Cost",
		name,
		["total_persiapan", "total_mobdemob", "total_alat", "total_management"],
		as_dict=True,
	)
	return doc or {}
