import frappe, re
from frappe import _

def validate_ifsc_code(self, method):
	if self.branch_code and not self.custom_is_import:
		pattern = re.compile("^[A-Z]{4}0[A-Z0-9]{6}$")
		if not pattern.match(self.branch_code):
			frappe.throw(_("IFSC Code is not valid"))