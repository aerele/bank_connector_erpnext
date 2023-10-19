import frappe
from frappe.utils import nowdate
import json
import uuid, requests
import random
from base64 import b64decode, b64encode
from frappe.utils import today

# from bank_connector_erpnext.erpnext___bank_connector.payments.payment import process_payment

# * api to call the otp sender
@frappe.whitelist()
def call_otp_sender(docname, bank_account, total_amount):
	unique_id = random.randint(100000000000,999999999999)
	frappe.db.set_value('Payment Order', docname, 'custom_unique_id', unique_id)
	connector_doc = frappe.get_doc("Bank Connector", bank_account)
	if not connector_doc:
		frappe.throw("Please configure Bank Connector")
	
	api_key = connector_doc.api_key
	api_secret = connector_doc.get_password("api_secret")
	url = f"{connector_doc.url}/api/method/icici_integration_server.api.generate_otp"
	headers = {
		"Authorization": f"token {api_key}:{api_secret}",
		"Content-Type": "application/json",
	}

	payment_payload = {
		'CORPID': connector_doc.corpid,
		'USERID': connector_doc.userid,
		'AGGRID': connector_doc.aggrid,
		'AGGRNAME': connector_doc.aggrname,
		'URN': connector_doc.urn,
		'UNIQUEID': str(unique_id),
		'AMOUNT': str(float(total_amount))
	}

	response = requests.request("POST", url, headers=headers, data=json.dumps({"payload": payment_payload}))
	res_json = json.loads(json.loads(response.text)['message'])

	if 'RESPONSE' in res_json.keys() and res_json['RESPONSE'].lower() == 'failure':
		frappe.throw(
			title= 'Error',
			msg=res_json['MESSAGE']
		)
	elif 'RESPONSE' in res_json.keys() and res_json['RESPONSE'].lower() == 'success':
		pass


def int_float(amt):
	val = int(amt) if amt.is_integer() else amt
	return val


# * api to make bulk payment
@frappe.whitelist()
def make_bank_payment(docname, bank_account, otp=None):
	payment_order_doc = frappe.get_doc("Payment Order", docname)
	doc_name = docname.replace("-", "")
	bank_ac = frappe.get_doc("Bank Account", payment_order_doc.company_bank_account)
	connector_doc = frappe.get_doc("Bank Connector", bank_account)
	api_key = connector_doc.api_key
	api_secret = connector_doc.api_secret
	url = f"{connector_doc.url}/api/method/icici_integration_server.api.make_payment"
	headers = {
		"Authorization": f"token {api_key}:{api_secret}",
		"Content-Type": "application/json",
	}

	ls = []
	
	first_line = "{}|{}|{}|{}|{}|{}|{}|{}^".format("FHR",len(payment_order_doc.summary)+1,payment_order_doc.posting_date.strftime('%m/%d/%Y'), doc_name,int_float(payment_order_doc.total),"INR",bank_ac.bank_account_no,"0011")
	ls.append(first_line)
	second_line ="{}|{}|{}|{}|{}|{}|{}|{}|{}^".format("MDR",bank_ac.bank_account_no,"0011",payment_order_doc.company.replace(" ","")[:30],int_float(payment_order_doc.total),'INR', doc_name,"ICIC0000011","WIB")
	ls.append(second_line)
	my_ba = frappe.get_doc("Bank Account", payment_order_doc.company_bank_account)
	for i in payment_order_doc.summary:
		ba = frappe.get_doc("Bank Account", i.bank_account)
		if(ba.bank == my_ba.bank):
			d = frappe.get_doc("Bank Account", i.bank_account)
			mcw_st = "{}|{}|{}|{}|{}|{}|{}|{}|{}^".format("MCW",d.bank_account_no,d.bank_account_no[:4],d.party.replace(" ","")[:30],int_float(i.amount),"INR",i.name,d.branch_code,"WIB")
			ls.append(mcw_st)
		else:
			d = frappe.get_doc("Bank Account", i.bank_account)
			mco_st = "{}|{}|{}|{}|{}|{}|{}|{}|{}^".format("MCO", d.bank_account_no,"0011",d.party.replace(" ","")[:30],int_float(i.amount),"INR",i.name,"NFT",d.branch_code)
			ls.append(mco_st)
	result = '\n'.join(ls)
	byte_like = str.encode(result)
	encode_result = b64encode(byte_like).decode('utf-8')
	data = {
		"FILE_DESCRIPTION": str(doc_name),
		"CORP_ID": str(connector_doc.corpid),
		"USER_ID": str(connector_doc.userid),
		"AGGR_ID": str(connector_doc.aggrid),
		"AGGR_NAME": str(connector_doc.aggrname),
		"URN": str(connector_doc.urn),
		"UNIQUE_ID": str(payment_order_doc.custom_unique_id), 
		"AGOTP": str(otp),
		"FILE_NAME": str(doc_name+".txt"),
		"FILE_CONTENT": str(encode_result)
	}

	response = requests.request("POST", url, headers=headers, data=json.dumps({"payload": data}))
	res_json = json.loads(json.loads(response.text)['message'])

#	action for failure response - works perfect
	if 'Response' in res_json.keys() and res_json['Response'] == 'Failure':
		frappe.log_error(
			title="bulk payment api error", message="Payment Order Number : "+ str(docname) +"\n"+ res_json['Message']
		)
		frappe.throw(
			title= 'Error',
			msg=res_json['Message']
		)
	
#	action for success response
	if 'FILE_SEQUENCE_NUM' in res_json.keys() and payment_order_doc.custom_unique_id == str(res_json['UNIQUE_ID']): 
		frappe.db.sql("update `tabPayment Order` set custom_file_sequence_no={} where name='{}' ".format(res_json['FILE_SEQUENCE_NUM'], docname))
		for i in payment_order_doc.summary:
			if not i.payment_initiated:
				frappe.db.set_value("Payment Order Summary", i.name, "payment_initiated", 1)
				frappe.db.set_value("Payment Order Summary", i.name, "payment_status", "Initiated")
		frappe.db.set_value("Payment Order", docname, "status", "Initiated")

# * Used by get_payment_status() to check and update status of every row in payment order summary
def check_summary_status(docname, response_text):
	result_dic = {}
	failure_dic = {}
	po_doc = frappe.get_doc("Payment Order", docname)
	res_json = response_text['XML'] if 'XML' in response_text.keys() else ''
	if not res_json:
		frappe.log_error(
			title="Reverse MOS", message="Payment Order Number : "+ str(docname) +"\n"+ str(response_text)
		)

	if ("RESPONSE" in res_json.keys()) and res_json["RESPONSE"] == "SUCCESS" and po_doc.custom_file_sequence_no == str(res_json['FILE_SEQUENCE_NUM']):
		if 'Record' in res_json['FILEUPLOAD_BINARY_OUTPUT']['Records'].keys():
			records = res_json['FILEUPLOAD_BINARY_OUTPUT']['Records']['Record']
			for i in range(1, len(records)):
				if records[i].split("|")[-3] == 'Payment Success':
					result_dic[records[i].split("|")[2]+"@#$%"+records[i].split("|")[6]] = records[i].split("|")[-5]+"@#$%"+today()
				else:
					failure_dic[records[i].split("|")[2]] = records[i].split("|")[6]

			for i in po_doc.summary:
				po_bank = frappe.get_doc("Bank Account", i.bank_account)
				if po_bank.bank_account_no+"@#$%"+str(i.amount) in result_dic.keys() and not i.payment_status == 'Processed':
					if frappe.db.exists({"doctype": "Payment Entry", "name": i.payment_entry}):
						frappe.db.set_value("Payment Entry", i.payment_entry, 'reference_no', result_dic[po_bank.bank_account_no+"@#$%"+str(i.amount)].split('@#$%')[0])
						frappe.db.set_value("Payment Entry", i.payment_entry, 'reference_date', result_dic[po_bank.bank_account_no+"@#$%"+str(i.amount)].split('@#$%')[1])
						frappe.db.set_value(i.doctype, i.name, 'payment_status', "Processed")

				if po_bank.bank_account_no in failure_dic.keys() and failure_dic[po_bank.bank_account_no] == i.amount:
					frappe.db.set_value(i.doctype, i.name, 'payment_status', "Failed")

# * api to get status of payment summary
@frappe.whitelist()
def get_payment_status(docname, bank_account):
	payment_order_doc = frappe.get_doc("Payment Order", docname)
	connector_doc = frappe.get_doc("Bank Connector", bank_account)
	api_key = connector_doc.api_key
	api_secret = connector_doc.api_secret
	url = f"{connector_doc.url}/api/method/icici_integration_server.api.get_status"
	headers = {
		"Authorization": f"token {api_key}:{api_secret}",
		"Content-Type": "application/json",
	}

	data = {
	  "CORPID": connector_doc.corpid,
	  "USERID": connector_doc.corpid+"."+connector_doc.userid,
	  "AGGRID": connector_doc.aggrid,
	  "URN": connector_doc.urn,
	  "FILESEQNUM": payment_order_doc.custom_file_sequence_no,
	  "ISENCRYPTED":"N"
  	}

	response = requests.request("POST", url, headers=headers, data=json.dumps({"payload": data}))
	res_json = json.loads(json.loads(response.text)['message'])
	frappe.db.set_value("Payment Order", docname, 'custom_response', str(res_json))

	check_summary_status(docname, res_json)

# * continous status check for every 10 minutes
def recursive_status_check():
	po = frappe.get_list("Payment Order Summary", {'docstatus': 1, 'payment_status': 'Initiated'}, pluck='parent')
	po = list(set(po))
	for i in po:
		po_doc = frappe.get_doc('Payment Order', i)
		get_payment_status(po_doc.name, po_doc.company_bank_account)

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