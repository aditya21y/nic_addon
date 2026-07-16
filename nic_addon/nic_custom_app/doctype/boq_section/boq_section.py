# Copyright (c) 2026, aditya&bagas and contributors
# For license information, please see license.txt

import math

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

SELL_RATE_PRECISION = 2


class BOQSection(Document):
	def validate(self):
		self.calculate_items()

	def calculate_items(self):
		"""Price every BoQ line and roll them up into the section sub total.

		For each line:
		    net_material / net_labor  ← snapshot from the linked Work Analysis
		    material_margin / labor_margin ← looked up from the active Margin Profile
		    sell_*_rate = roundup(net / (1 - margin))      (margin-on-selling)
		    amount      = (sell_material + sell_labor) × volume
		    cost_amount = (net_material  + net_labor)  × volume
		"""
		margins = get_margin_lookup(self.project)

		sell_material = sell_labor = 0.0
		cost_material = cost_labor = 0.0
		for item in self.items:
			# Pull the net rates from the Work Analysis while linked; this keeps a
			# draft live and freezes the numbers once the section is submitted.
			#   Composite → the assembled unit rate (out_*_rate)
			#   Simple    → the matching component's amount_material / amount_labor
			if item.source_type:
				self.set_net_rates_from_work_analysis(item)

			code = cint(item.margin_category)
			item.material_margin = flt(margins.get((code, "Material")))
			item.labor_margin = flt(margins.get((code, "Upah")))

			item.sell_material_rate = _roundup(
				sell_rate(item.net_material, item.material_margin, item.idx), SELL_RATE_PRECISION
			)
			item.sell_labor_rate = _roundup(
				sell_rate(item.net_labor, item.labor_margin, item.idx), SELL_RATE_PRECISION
			)

			volume = flt(item.volume)
			item.amount = flt((flt(item.sell_material_rate) + flt(item.sell_labor_rate)) * volume)
			item.cost_amount = flt((flt(item.net_material) + flt(item.net_labor)) * volume)

			sell_material += flt(item.sell_material_rate) * volume
			sell_labor += flt(item.sell_labor_rate) * volume
			cost_material += flt(item.net_material) * volume
			cost_labor += flt(item.net_labor) * volume

		self.subtotal_sell_material = flt(sell_material)
		self.subtotal_sell_labor = flt(sell_labor)
		self.sub_total = flt(sell_material) + flt(sell_labor)
		self.subtotal_cost_material = flt(cost_material)
		self.subtotal_cost_labor = flt(cost_labor)
		self.subtotal_cost = flt(cost_material) + flt(cost_labor)

	def set_net_rates_from_work_analysis(self, item):
		"""Snapshot net_material / net_labor from the linked Work Analysis.

		Both Simple (one header-priced item) and Composite (an assembly) expose
		their net unit rate as out_material_rate / out_labor_rate.
		"""
		wa = frappe.db.get_value(
			"Work Analysis",
			item.source_type,
			["out_material_rate", "out_labor_rate"],
			as_dict=True,
		)
		if wa:
			item.net_material = flt(wa.out_material_rate)
			item.net_labor = flt(wa.out_labor_rate)


def sell_rate(net, margin_percent, idx=None):
	"""Margin-on-selling-price: net / (1 - margin). Not a cost markup."""
	divisor = 1 - flt(margin_percent) / 100.0
	if divisor <= 0:
		frappe.throw(
			_("Row {0}: margin of {1}% is not valid (must be below 100%).").format(
				idx, flt(margin_percent)
			)
		)
	return flt(net) / divisor


def _roundup(value, digits):
	"""ROUNDUP — always rounds away from zero, like Excel's ROUNDUP()."""
	factor = 10**digits
	# round() first absorbs float noise (e.g. 66606.0000001) before ceil.
	return math.ceil(round(flt(value) * factor, 6)) / factor


def get_margin_lookup(project=None):
	"""Return {(category_code, kode): percentage} from the active Margin Profile.

	Prefers an active profile scoped to `project`, then a project-less active
	profile, then any active profile.
	"""
	base = {"is_active": 1, "docstatus": ["<", 2]}
	name = None
	if project:
		name = frappe.db.get_value("Margin Profile", {**base, "project": project}, "name")
	if not name:
		name = frappe.db.get_value("Margin Profile", {**base, "project": ["in", ["", None]]}, "name")
	if not name:
		name = frappe.db.get_value("Margin Profile", base, "name")
	if not name:
		return {}

	rows = frappe.get_all(
		"Margin Profile Component",
		filters={"parent": name, "parenttype": "Margin Profile"},
		fields=["number", "kode", "percentage"],
	)
	return {(cint(r.number), r.kode): flt(r.percentage) for r in rows}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def work_analysis_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link query for BoQ Item.source_type.

	Shows only Work Analyses that price the chosen item — matching item_code for
	Simple analyses and analysis_code for Composite ones — optionally scoped to
	the section's project (plus shared, project-less analyses).
	"""
	filters = filters or {}
	item_code = filters.get("item_code")
	project = filters.get("project")

	conditions = ["wa.docstatus < 2"]
	values = {"txt": f"%{txt}%", "start": start, "page_len": page_len}

	if item_code:
		conditions.append(
			"((wa.analysis_type = 'Simple' AND wa.item_code = %(item_code)s)"
			" OR (wa.analysis_type = 'Composite' AND wa.analysis_code = %(item_code)s))"
		)
		values["item_code"] = item_code

	if project:
		conditions.append("(wa.project = %(project)s OR wa.project IS NULL OR wa.project = '')")
		values["project"] = project

	if txt:
		conditions.append(
			"(wa.name LIKE %(txt)s OR wa.alias LIKE %(txt)s"
			" OR wa.analysis_name LIKE %(txt)s OR wa.item_name LIKE %(txt)s)"
		)

	return frappe.db.sql(
		"""
		select wa.name, wa.analysis_type, wa.alias
		from `tabWork Analysis` wa
		where {conditions}
		order by wa.modified desc
		limit %(page_len)s offset %(start)s
		""".format(conditions=" and ".join(conditions)),
		values,
	)
