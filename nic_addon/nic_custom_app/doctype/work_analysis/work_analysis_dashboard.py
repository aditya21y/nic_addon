from frappe import _


def get_data():
	return {
		"fieldname": "source_type",
		"transactions": [
			{"label": _("BoQ"), "items": ["BOQ Section"]},
		],
	}
