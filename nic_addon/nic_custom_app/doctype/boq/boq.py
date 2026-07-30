# Copyright (c) 2026, aditya&bagas and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from nic_addon.nic_custom_app.doctype.direct_cost.direct_cost import get_direct_cost_totals


class BoQ(Document):
	def onload(self):
		self.apply_settings_defaults()

	def validate(self):
		self.apply_settings_defaults()
		self.build_recap()

	def apply_settings_defaults(self):
		"""Fill blank parameters from BoQ Settings."""
		settings = frappe.get_cached_doc("BoQ Settings")
		if not self.ppn_percent:
			self.ppn_percent = settings.default_ppn_percent
		if not self.x_factor:
			self.x_factor = settings.default_x_factor
		if not self.dp_percent:
			self.dp_percent = settings.default_dp_percent

	@frappe.whitelist()
	def get_sections(self):
		"""Attach every BoQ Section of this project that isn't yet owned by a BoQ."""
		if not self.project:
			frappe.throw(_("Set the Project first."))

		sections = frappe.get_all(
			"BOQ Section",
			filters={
				"project": self.project,
				"docstatus": ["<", 2],
				"boq": ["in", ["", None]],
			},
			pluck="name",
		)
		for name in sections:
			frappe.db.set_value("BOQ Section", name, "boq", self.name)

		self.reload()
		self.build_recap()
		self.save()
		return len(sections)

	def build_recap(self):
		"""Rebuild the per-discipline recap (RAPP APP.1/2/3, profit) from the
		sections owned by this BoQ, the Direct Cost, and BoQ Settings."""
		settings = frappe.get_cached_doc("BoQ Settings")
		ppn = flt(self.ppn_percent) / 100.0
		dp = flt(self.dp_percent) / 100.0
		x_factor = flt(self.x_factor) / 100.0

		# 1) Aggregate the owned sections per discipline.
		rows = frappe.get_all(
			"BOQ Section",
			filters={"boq": self.name, "docstatus": ["<", 2]},
			fields=[
				"discipline",
				"subtotal_cost_material",
				"subtotal_cost_labor",
				"subtotal_sell_material",
				"subtotal_sell_labor",
			],
		)

		disciplines = {}
		for r in rows:
			d = disciplines.setdefault(
				r.discipline,
				{"cost_material": 0.0, "cost_labor": 0.0, "sell_material": 0.0, "sell_labor": 0.0},
			)
			d["cost_material"] += flt(r.subtotal_cost_material)
			d["cost_labor"] += flt(r.subtotal_cost_labor)
			d["sell_material"] += flt(r.subtotal_sell_material)
			d["sell_labor"] += flt(r.subtotal_sell_labor)

		# 2) Direct Cost (APP.2 pool) and the total offer that drives allocation.
		dc = get_direct_cost_totals(
			project=self.project, boq=self.name, direct_cost=self.direct_cost
		)
		total_offer = sum(flt(d["sell_material"]) + flt(d["sell_labor"]) for d in disciplines.values())

		# 3) One recap row per discipline.
		self.recap = []
		tot = {"cost": 0.0, "offer": 0.0, "app2": 0.0, "app3": 0.0, "total_app": 0.0, "profit": 0.0}
		for discipline, d in disciplines.items():
			cost_total = flt(d["cost_material"]) + flt(d["cost_labor"])
			sell_total = flt(d["sell_material"]) + flt(d["sell_labor"])
			share = (sell_total / total_offer) if total_offer else 0.0

			# APP.2 — each Direct Cost group allocated by offer share, plus x-factor.
			app2_persiapan = flt(flt(dc.get("total_persiapan")) * share)
			app2_mobdemob = flt(flt(dc.get("total_mobdemob")) * share)
			app2_alat = flt(flt(dc.get("total_alat")) * share)
			app2_management = flt(flt(dc.get("total_management")) * share)
			app2_xfactor = flt(sell_total * x_factor)
			app2 = flt(app2_persiapan + app2_mobdemob + app2_alat + app2_management + app2_xfactor)

			# APP.3 — financing. Bank Garansi & Jaminan are against DP (incl. PPN).
			dp_base = sell_total * dp * (1 + ppn)
			app3_bunga = flt(sell_total * flt(settings.bunga_kmk) / 100.0)
			app3_pph = flt(sell_total * flt(settings.pph) / 100.0)
			app3_bank_garansi = flt(dp_base * flt(settings.bank_garansi) / 100.0)
			app3_jaminan = flt(dp_base * flt(settings.jaminan) / 100.0)
			app3_asuransi = flt(sell_total * flt(settings.asuransi) / 100.0)
			app3 = flt(app3_bunga + app3_pph + app3_bank_garansi + app3_jaminan + app3_asuransi)

			total_app = flt(cost_total + app2 + app3)
			profit = flt(sell_total - total_app)

			self.append(
				"recap",
				{
					"discipline": discipline,
					"discipline_name": frappe.db.get_value("Discipline", discipline, "discipline_name"),
					"cost_material": flt(d["cost_material"]),
					"cost_labor": flt(d["cost_labor"]),
					"cost_total": cost_total,
					"sell_material": flt(d["sell_material"]),
					"sell_labor": flt(d["sell_labor"]),
					"sell_total": sell_total,
					"app2_persiapan": app2_persiapan,
					"app2_mobdemob": app2_mobdemob,
					"app2_alat": app2_alat,
					"app2_management": app2_management,
					"app2_xfactor": app2_xfactor,
					"app2": app2,
					"app3_bunga": app3_bunga,
					"app3_pph": app3_pph,
					"app3_bank_garansi": app3_bank_garansi,
					"app3_jaminan": app3_jaminan,
					"app3_asuransi": app3_asuransi,
					"app3": app3,
					"total_app": total_app,
					"profit": profit,
				},
			)

			tot["cost"] += cost_total
			tot["offer"] += sell_total
			tot["app2"] += app2
			tot["app3"] += app3
			tot["total_app"] += total_app
			tot["profit"] += profit

		# 4) Header totals.
		self.subtotal_cost = flt(tot["cost"])
		self.subtotal_offer = flt(tot["offer"])
		self.total_app2 = flt(tot["app2"])
		self.total_app3 = flt(tot["app3"])
		self.total_app = flt(tot["total_app"])
		self.total_profit = flt(tot["profit"])
		self.offer_with_ppn = flt(tot["offer"] * (1 + ppn))
