# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

# ERPNext - web based ERP (http://erpnext.com)
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe, json
import http.client
import mimetypes
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.utils import get_url, cint
from frappe.utils.background_jobs import enqueue
from frappe import msgprint
from frappe.model.document import Document
import datetime
from frappe.utils import cint, flt, cstr, now
from datetime import date, datetime

class SMSApi(Document):
	pass
@frappe.whitelist(allow_guest=True)
def send_message(payload_to_send):
	msgprint(payload_to_send)
	#payload_to_use = json.loads(payload_to_send)
	msgparameters = []
	msgparameters.append(payload_to_send)
	conn = http.client.HTTPSConnection("api.onfonmedia.co.ke")
	payload ={}
	payload["SenderId"] ="MTRH"
	payload["MessageParameters"] = msgparameters
	"""[
		{
			"Number":number,
			"Text":message,

		}
	]"""
	payload["ApiKey"] = "69pJq6iTBSwfAaoL4BU7yHi361dGLkqQ1MJYHQF/lJI="
	payload["ClientId"] ="8055c2c9-489b-4440-b761-a0cc27d1e119"
	msgprint(payload)
	headers ={}
	headers['Content-Type']= 'application/json'
	headers['AccessKey']= 'FKINNX9pwrBDzGHxgQ2EB97pXMz6vVgd'
	headers['Content-Type']= 'application/json'
	headers['Cookie']= 'AWSALBTG=cWN78VX7OjvsWtCKpI8+ZTJuLfqNCOqRtmN6tRa4u47kdC/G4k7L3TdKrzftl6ni4LspFPErGdwg/iDlloajVm0LoGWChohiR07jljLMz/a8tduH+oHvptQVo1DgCplIyjCC+SyvnUjS2vrFiLN5E+OvP9KwWIjvmHjRiNJZSVJ4MageyKQ=; AWSALBTGCORS=cWN78VX7OjvsWtCKpI8+ZTJuLfqNCOqRtmN6tRa4u47kdC/G4k7L3TdKrzftl6ni4LspFPErGdwg/iDlloajVm0LoGWChohiR07jljLMz/a8tduH+oHvptQVo1DgCplIyjCC+SyvnUjS2vrFiLN5E+OvP9KwWIjvmHjRiNJZSVJ4MageyKQ='
	conn.request("POST", "/v1/sms/SendBulkSMS", payload, headers)
	res = conn.getresponse()
	data = res.read()
    #print(data.decode("utf-8"))
	frappe.response["payload"] = payload
	frappe.response["response"] =data