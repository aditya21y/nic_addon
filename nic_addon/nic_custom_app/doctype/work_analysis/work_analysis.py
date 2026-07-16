# Copyright (c) 2026, aditya&bagas and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate


class WorkAnalysis(Document):
	def validate(self):
		self.validate_analysis_code()
		self.calculate_amounts()

	def validate_analysis_code(self):
		"""A Composite analysis_code must be a non-stock Item and must not appear
		among its own components (an assembly cannot contain itself)."""
		if self.analysis_type != "Composite" or not self.analysis_code:
			return

		if frappe.db.get_value("Item", self.analysis_code, "is_stock_item"):
			frappe.throw(
				_("Analysis Code {0} must be a non-stock Item (is_stock_item = 0).").format(
					frappe.bold(self.analysis_code)
				)
			)

		for c in self.components:
			if c.item_code and c.item_code == self.analysis_code:
				frappe.throw(
					_("Row {0}: component cannot be the assembly item {1} itself.").format(
						c.idx, frappe.bold(self.analysis_code)
					)
				)

	def calculate_amounts(self):
		"""Roll up the out_* rates.

		Simple    -> one item priced in the header: rate * (1 + pct).
		Composite -> components build one assembly; each row is qty * rate PLUS
		             its percentage of the qty * rate subtotal (a "Waste 2%" row
		             applies against the whole subtotal).
		"""
		if self.analysis_type == "Simple":
			total_material = flt(flt(self.material_rate) * (1 + flt(self.material_percentage) / 100))
			total_labor = flt(flt(self.labor_rate) * (1 + flt(self.labor_percentage) / 100))
		else:
			# First pass: qty × rate subtotals are the bases the percentages apply to.
			material_base = 0.0
			labor_base = 0.0
			for c in self.components:
				material_base += flt(c.qty) * flt(c.material_rate)
				labor_base += flt(c.qty) * flt(c.labor_rate)

			# Second pass: each row is qty × rate PLUS its percentage of the base.
			for c in self.components:
				c.amount_material = flt(flt(c.qty) * flt(c.material_rate) + flt(c.material_percentage) / 100 * material_base)
				c.amount_labor = flt(flt(c.qty) * flt(c.labor_rate) + flt(c.labor_percentage) / 100 * labor_base)

			total_material = sum(flt(c.amount_material) for c in self.components)
			total_labor = sum(flt(c.amount_labor) for c in self.components)

		self.out_material_rate = flt(total_material)
		self.out_labor_rate = flt(total_labor)
		self.out_total_rate = flt(total_material) + flt(total_labor)


@frappe.whitelist()
def get_item_price(item_code, posting_date=None):
	"""Return the buying Item Price for `item_code` that is valid on `posting_date`.

	Picks the most recent price whose `valid_from` is on or before the posting
	date (latest valid_from wins), ignoring any price whose validity window has
	already closed (`valid_upto` before the posting date). Only buying price
	lists are considered.
	"""
	if not item_code:
		return None

	posting_date = getdate(posting_date or nowdate())

	row = frappe.db.sql(
		"""
		select name, price_list, price_list_rate, supplier, valid_from
		from `tabItem Price`
		where item_code = %(item_code)s
			and buying = 1
			and (valid_from is null or valid_from <= %(date)s)
			and (valid_upto is null or valid_upto = '' or valid_upto >= %(date)s)
		order by valid_from desc, modified desc
		limit 1
		""",
		{"item_code": item_code, "date": posting_date},
		as_dict=True,
	)

	if not row:
		return None

	return {
		"item_price": row[0].name,
		"price_list_rate": row[0].price_list_rate,
		"price_list": row[0].price_list,
		"supplier": row[0].supplier,
		"valid_from": row[0].valid_from,
	}
