import frappe
from frappe.utils import nowdate
import json
import uuid, requests
import random

# from bank_connector_erpnext.erpnext___bank_connector.payments.payment import process_payment


@frappe.whitelist()
def call_otp_sender(bank_account, total_amount):
	connector_doc = frappe.get_doc("Bank Connector", bank_account)
	if not connector_doc:
		frappe.throw("Please configure Bank Connector")
	
	api_key = connector_doc.api_key
	api_secret = connector_doc.get_password("api_secret")
	url = f"{connector_doc.url}/api/method/icici_integration_server.api.generate_otp"
	headers = headers = {
		"Authorization": f"token {api_key}:{api_secret}",
		"Content-Type": "application/json",
	}

	payment_payload = {
        'CORPID': connector_doc.corpid,
        'USERID': connector_doc.userid,
        'AGGRID': connector_doc.aggrid,
        'AGGRNAME': connector_doc.aggrname,
        'URN': connector_doc.urn,
        'UNIQUEID': random.randint(100000000000,999999999999),
        'AMOUNT': total_amount
	}

	response = requests.request("POST", url, headers=headers, data=json.dumps({"payload": payment_payload}))
	print(response.text)

	# if response.status_code == 200:
	# 	response_data = json.loads(response.text)

@frappe.whitelist()
def make_bank_payment(docname, otp=None):
	payment_order_doc = frappe.get_doc("Payment Order", docname)
	count = 0
	for i in payment_order_doc.summary:
		if not i.payment_initiated:
			invoices = []
			payment_response = process_payment(i, payment_order_doc.company_bank_account, invoices=invoices)
			if "payment_status" in payment_response and payment_response["payment_status"] == "Initiated":
				frappe.db.set_value("Payment Order Summary", i.name, "payment_initiated", 1)
				frappe.db.set_value("Payment Order Summary", i.name, "payment_status", "Initiated")
				count += 1
			else:
				frappe.db.set_value("Payment Order Summary", i.name, "payment_status", "Failed")
				if "message" in payment_response:
					frappe.db.set_value("Payment Order Summary", i.name, "message", payment_response["message"])

	payment_order_doc.reload()
	processed_count = 0
	for i in payment_order_doc.summary:
		if i.payment_initiated:
			processed_count += 1
	
	if processed_count == len(payment_order_doc.summary):
		frappe.db.set_value("Payment Order", docname, "status", "Initiated")

	return {"message": f"{count} payments initiated"}


@frappe.whitelist()
def get_payment_status(docname):
	payment_order_doc = frappe.get_doc("Payment Order", docname)
	for i in payment_order_doc.summary:
		if i.payment_initiated and i.payment_status in ["Initiated"]:
			get_response(i, payment_order_doc.company_bank_account)
	payment_order_doc.reload()


@frappe.whitelist()
def modify_approval_status(items, approval_status):
	if not items:
		return
	
	if isinstance(items, str):
		items = json.loads(items)
	line_item_status = {}
	for item in items:
		line_item_status[item] = {"status": None, "message": ""}
		pos_doc = frappe.get_doc("Payment Order Summary", item)
		if pos_doc.payment_initiated:
			line_item_status[item] = {"status": 0, "message": f"Payment already initiated for {pos_doc.supplier} - {pos_doc.amount}"}
			continue
		if pos_doc.payment_rejected:
			line_item_status[item] = {"status": 0, "message": f"Payment already rejected for {pos_doc.supplier} - {pos_doc.amount}"}
			continue
		frappe.db.set_value("Payment Order Summary", item, "approval_status", approval_status)
		line_item_status[item] = {
			"status": 1, 
			"message": approval_status
		}

	return line_item_status


@frappe.whitelist()
def make_payment_entries(docname):
	payment_order_doc = frappe.get_doc("Payment Order", docname)
	"""create entry"""
	frappe.flags.ignore_account_permission = True

	for row in payment_order_doc.summary:
		pe = frappe.new_doc("Payment Entry")
		pe.payment_type = "Pay"
		pe.payment_entry_type = "Pay"
		pe.company = payment_order_doc.company
		pe.cost_center = row.cost_center
		pe.project = row.project
		pe.posting_date = nowdate()
		pe.mode_of_payment = "Wire Transfer"
		pe.party_type = row.party_type
		pe.party = row.party
		pe.bank_account = payment_order_doc.company_bank_account
		pe.party_bank_account = row.bank_account
		if pe.party_type == "Supplier":
			pe.ensure_supplier_is_not_blocked()
		pe.payment_order = payment_order_doc.name

		pe.paid_from = payment_order_doc.account
		if row.account:
			pe.paid_to = row.account
		pe.paid_from_account_currency = "INR"
		pe.paid_to_account_currency = "INR"
		pe.paid_amount = row.amount
		pe.received_amount = row.amount
		pe.letter_head = frappe.db.get_value("Letter Head", {"is_default": 1}, "name")

		if row.tax_withholding_category:
			net_total = 0
			for reference in payment_order_doc.references:
				if reference.party_type == row.party_type and \
						reference.party == row.party and \
						reference.cost_center == row.cost_center and \
						reference.project == row.project and \
						reference.bank_account == row.bank_account and \
						reference.account == row.account and \
						reference.tax_withholding_category == row.tax_withholding_category and \
						reference.reference_doctype == row.reference_doctype:
					net_total += frappe.db.get_value("Payment Request", reference.payment_request, "net_total")
			pe.paid_amount = net_total
			pe.received_amount = net_total
			pe.apply_tax_withholding_amount = 1
			pe.tax_withholding_category = row.tax_withholding_category
		for reference in payment_order_doc.references:
			if not reference.is_adhoc:
				if reference.party_type == row.party_type and \
						reference.party == row.party and \
						reference.cost_center == row.cost_center and \
						reference.project == row.project and \
						reference.bank_account == row.bank_account and \
						reference.account == row.account and \
						reference.tax_withholding_category == row.tax_withholding_category and \
						reference.reference_doctype == row.reference_doctype:
					pe.append(
						"references",
						{
							"reference_doctype": reference.reference_doctype,
							"reference_name": reference.reference_name,
							"total_amount": reference.amount,
							"allocated_amount": reference.amount,
						},
					)

		pe.update(
			{
				"reference_no": payment_order_doc.name,
				"reference_date": nowdate(),
				"remarks": "Payment Entry from Payment Order - {0}".format(
					payment_order_doc.name
				),
			}
		)
		pe.setup_party_account_field()
		pe.set_missing_values()
		pe.insert(ignore_permissions=True)
		pe.submit()
		frappe.db.set_value("Payment Order Summary", row.name, "payment_entry", pe.name)


@frappe.whitelist()
def log_payload(docname):
	payment_order_doc = frappe.get_doc("Payment Order", docname)
	for row in payment_order_doc.summary:
		short_code = frappe.db.get_value("Bank Integration Mode", {"parent": payment_order_doc.company_bank_account, "mode_of_transfer": row.mode_of_transfer}, "short_code")
		bank_account = frappe.get_doc("Bank Account", row.bank_account)
		brl = frappe.new_doc("Bank API Request Log")
		brl.payment_order = payment_order_doc.name
		brl.payload = json.dumps()
		brl.status = "Initiated"
		brl.save()
		brl.submit()

def process_payment(payment_info, company_bank_account, invoices = None):
	connector_doc = frappe.get_doc("Bank Connector", company_bank_account)
	if not connector_doc:
		frappe.throw("Please configure Bank Connector")
	
	api_key = connector_doc.api_key
	api_secret = connector_doc.get_password("api_secret")
	url = f"{connector_doc.url}/api/method/bank_connector.bank_connector.doctype.bank_request_log.bank_request_log.make_payment"
	headers = headers = {
		"Authorization": f"token {api_key}:{api_secret}",
		"Content-Type": "application/json",
	}

	payment_payload = {}
	bank_account = frappe.get_doc("Bank Account", payment_info.bank_account)
	payment_payload["branch_code"] = bank_account.branch_code
	payment_payload["account_number"] = bank_account.bank_account_no
	payment_payload["name"] = payment_info.name
	payment_payload["amount"] = payment_info.amount
	payment_payload["party"] = payment_info.party
	payment_payload["mode_of_transfer"] = payment_info.mode_of_transfer


	payload = {
		"doc": payment_payload
	}


	response = requests.request("POST", url, headers=headers, data=json.dumps(payload))
	print(response.text)

	if response.status_code == 200:
		response_data = json.loads(response.text)
		if "message" in response_data and response_data["message"]:
			if "payment_status" in response_data["message"] and response_data["message"]["payment_status"] == "Initiated":
				return {"payment_status": "Initiated", "message": ""}
			else:
				return {"payment_status": "Failed", "message": ""}

def get_response(payment_info, company_bank_account):
	connector_doc = frappe.get_doc("Bank Connector", company_bank_account)
	if not connector_doc:
		frappe.throw("Please configure Bank Connector")
	
	api_key = connector_doc.api_key
	api_secret = connector_doc.get_password("api_secret")
	url = f"{connector_doc.url}/api/method/bank_connector.bank_connector.doctype.bank_request_log.bank_request_log.get_payment_status"
	headers = headers = {
		"Authorization": f"token {api_key}:{api_secret}",
		"Content-Type": "application/json",
	}
	payload = {
		"doc": {
			"request_id": payment_info.name
		}
	}

	print(payload)
	response = requests.request("POST", url, headers=headers, data=json.dumps(payload))
	if response.status_code not in [201, 200]:
		return
	
	response_data = json.loads(response.text)
	if "message" in response_data and response_data["message"]:
		if "payment_status" in response_data["message"] and response_data["message"]["payment_status"] == "Processed":
			if response_data["message"]["reference_number"]:
				frappe.db.set_value("Payment Order Summary", payment_info.name, "reference_number", response_data["message"]["reference_number"])
				frappe.db.set_value("Payment Entry", payment_info.payment_entry, "reference_no", response_data["message"]["reference_number"])
			frappe.db.set_value("Payment Order Summary", payment_info.name, "payment_status", "Processed")
		elif "payment_status" in response_data["message"] and response_data["message"]["payment_status"] in ["Rejected", "Failed"]:
			frappe.db.set_value("Payment Order Summary", payment_info.name, "payment_status", response_data["message"]["payment_status"])
			payment_entry_doc = frappe.get_doc("Payment Entry", payment_info.payment_entry)
			payment_entry_doc.cancel()
		elif "reference_number" in response_data["message"] and response_data["message"]["reference_number"]:
			frappe.db.set_value("Payment Order Summary", payment_info.name, "reference_number", response_data["message"]["reference_number"])
			frappe.db.set_value("Payment Entry", payment_info.payment_entry, "reference_no", response_data["message"]["reference_number"])