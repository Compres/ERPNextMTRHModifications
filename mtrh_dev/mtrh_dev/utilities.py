import frappe, json
from frappe import _
from frappe.utils.file_manager import check_max_file_size, get_content_hash, get_file_name, get_file_data_from_hash
from frappe.utils import get_files_path, get_hook_method, call_hook_method, random_string, get_fullname, today
import os, base64
from six import text_type, string_types
import mimetypes
from copy import copy
from mtrh_dev.mtrh_dev.tqe_on_submit_operations import raise_po_based_on_direct_purchase

from frappe.model.workflow import get_workflow_name, get_workflow_state_field

from erpnext.accounts.utils import get_fiscal_year
from datetime import date, datetime

@frappe.whitelist()
def attach_file_to_doc(filedata, doc_type, doc_name, file_name):
	if filedata:
		file_path = get_files_path(is_private = 0)
		folder = doc_name + "-" + random_string(7)
		frappe.create_folder(file_path + "/" + folder)
		#folder = get_files_path(folder, is_private = 1) #"/private/files/" + folder + "/"
		fd_json = json.loads(filedata)
		fd_list = list(fd_json["files_data"])
		for fd in fd_list:
			content_type = mimetypes.guess_type(fd["filename"])[0]
			filedoc = save_file_on_filesystem(fd["filename"], fd["dataurl"], folder= folder, content_type=content_type, is_private=0)
	return filedoc

def save_file_on_filesystem(fname, content, folder=None, content_type=None, is_private=0):
	fpath = write_file(content, fname, folder, is_private)
	#frappe.msgprint(_("Path: " + fpath + ", Folder: " + folder)
	if folder:
		if is_private:
			file_url = "/private/files/{0}/{1}".format(folder, fname)
		else:
			file_url = "/files/{0}/{1}".format(folder, fname)
	else:
		if is_private:
			file_url = "/private/files/{0}".format(fname)
		else:
			file_url = "/files/{0}".format(fname)
	return file_url
	#return {
	#	'file_name': os.path.basename(fpath),
	#	'file_url': file_url
	#}

def write_file(content, fname, folder=None, is_private=0):
	"""write file to disk with a random name (to compare)"""
	file_path = get_files_path(folder, is_private=is_private)

	# create directory (if not exists)
	frappe.create_folder(file_path)
	# write the file
	#if isinstance(content, text_type):
	#content = content.encode()
	#content = base64.b64decode(content)
	if isinstance(content, text_type):
		content = content.encode("utf-8")

	if b"," in content:
		content = content.split(b",")[1]
	content = base64.b64decode(content)
	
	with open(os.path.join(file_path.encode('utf-8'), fname.encode('utf-8')), 'wb+') as f:
		f.write(content)

	return get_files_path(folder, fname, is_private=is_private)
	
#====================================================================================================================================================
#SUPPLIER QUOTATION GENERATION
#====================================================================================================================================================

# This method is used to make supplier quotation from supplier's portal.
@frappe.whitelist()
def create_supplier_quotation(doc):
	if isinstance(doc, string_types):
		doc = json.loads(doc)
	rfq = doc.get('name')
	try:
		sq_doc = frappe.get_doc({
			"doctype": "Supplier Quotation",
			"supplier": doc.get('supplier'),
			"terms": doc.get("terms"),
			"company": doc.get("company"),
			"currency": doc.get('currency') or get_party_account_currency('Supplier', doc.get('supplier'), doc.get('company')),
			"buying_price_list": doc.get('buying_price_list') or frappe.db.get_value('Buying Settings', None, 'buying_price_list')
		})
		add_items(sq_doc, doc.get('supplier'), doc.get('items'))
		sq_doc.flags.ignore_permissions = True
		sq_doc.run_method("set_missing_values")
		sq_doc.save()
		raise_po_based_on_direct_purchase(rfq)
		#frappe.msgprint(_("Your submission of Quotation {0} was successful. You will be alerted once it is opened and evaluated.").format(sq_doc.name))
		return sq_doc.name
	except Exception:
		return None

def add_items(sq_doc, supplier, items):
	for data in items:
		if data.get("qty") > 0:
			if isinstance(data, dict):
				data = frappe._dict(data)

			create_rfq_items(sq_doc, supplier, data)

def create_rfq_items(sq_doc, supplier, data):
	sq_doc.append('items', {
		"item_code": data.item_code,
		"item_name": data.item_name,
		"description": data.description,
		"qty": data.qty,
		"rate": data.rate,
		"attachments": data.attachments,
		"files": data.attachments,
		"supplier_part_no": frappe.db.get_value("Item Supplier", {'parent': data.item_code, 'supplier': supplier}, "supplier_part_no"),
		"warehouse": data.warehouse or '',
		"request_for_quotation_item": data.name,
		"request_for_quotation": data.parent
	})
#====================================================================================================================================================
# ADD IMPORTANT ACTION LOGS TO DOCUMENTS. THESE LOGS CAN THEN BE AVAILABLE ON PRINT MODE TO TRACK APPROVALS AND DECISIONS ON DOCUMENTS.
#====================================================================================================================================================
def process_workflow_log(doc, state):
	if state == "before_save":
		workflow = get_workflow_name(doc.get('doctype'))
		if not workflow: return
		if is_workflow_action_already_created(doc): return
		this_doc_workflow_state = get_doc_workflow_state(doc)
		if not this_doc_workflow_state:
			this_doc_workflow_state ="Draft"
		the_decision = "Actioned To: " + this_doc_workflow_state
		
	elif state == "before_submit":
		the_decision = "Document Approved!"
		
		#LET THE USER GIVE A MEMO FOR APPROVING DOCUMENT.
		comment_on_action(doc, state)
	elif state == "on_cancel":
		the_decision = "Document Cancelled/Revoked!"
		
		#LET THE USER GIVE A MEMO FOR CANCELLING DOCUMENT.
		comment_on_action(doc, state)
	#frappe.msgprint("Logging: " + state)
	log_actions(doc, the_decision)

	#================Generation of Quality Inspection========================
	if doc.get('doctype')=="Purchase Receipt" and state == "before_save" and get_doc_workflow_state(doc) =="Pending Inspection":
		#function to insert into Quality Inspection
		#frappe.msgprint("Logging: " + get_doc_workflow_state(doc))
		create_quality_inspection(doc)

def create_quality_inspection(doc):
	#frappe.throw(doc.name)
	docname=doc.name	
	itemlist = frappe.db.get_list("Purchase Receipt Item",
		filters={
				"parent":docname,				
			},
			fields=["item_code","item_name","qty","amount"],
			ignore_permissions = True,
			as_list=False
		)
	for item in itemlist:		
		itemcode=item.get("item_code")	
		itemname=item.get("item_name")		
		qty=item.get("qty")		
		amount= item.get("amount")		
	template_name= frappe.db.get_value('Item', item.get("item_code"), 'quality_inspection_template')	
	today = str(date.today())
	user=frappe.session.user
	doc_type = doc.get('doctype')
	#frappe.throw(doc_type)	
	docc = frappe.new_doc('Quality Inspection')
	docc.update(
				{	
					"naming_series":"MAT-QA-.YYYY.-",
					"report_date":today,	
					"inspection_type":"Incoming",
					"sample_size":qty,
					"status":"Accepted",
					"inspected_by":user,
					"item_code":itemcode,
					"item_name":itemname,
					"reference_type":doc_type,
					"reference_name":docname,
					"quality_inspection_template":template_name,				
																			
				}
			)
	docc.insert(ignore_permissions = True)
	

def log_actions(doc, action_taken):
	logged_in_user = frappe.session.user
	child = frappe.new_doc("Approval Log")
	action_user = get_fullname(logged_in_user)

	if "Employee" not in frappe.get_roles(frappe.session.user):
		action_user ="System Generated"
	action_user_signature = None
	if frappe.db.exists("Signatures", logged_in_user):
		action_user_signature = frappe.get_cached_value("Signatures", logged_in_user, "signature")
	child.update({
		"doctype": "Approval Log",
		"parenttype": doc.get('doctype'),
		"parent": doc.get('name'),
		"parentfield": "action_log",
		"action_time": frappe.utils.data.now_datetime(),
		"decision": action_taken,
		"action_user": action_user,
		"signature": action_user_signature,
		"idx": len(doc.action_log) + 1
	})
	doc.action_log.append(child)

def is_workflow_action_already_created(doc):
	return frappe.db.exists({
		'doctype': 'Workflow Action',
		'reference_doctype': doc.get('doctype'),
		'reference_name': doc.get('name'),
		'workflow_state': get_doc_workflow_state(doc)
	})

def get_doc_workflow_state(doc):
	workflow_name = get_workflow_name(doc.get('doctype'))
	workflow_state_field = get_workflow_state_field(workflow_name)
	return doc.get(workflow_state_field)

def get_next_possible_transitions(workflow_name, state, doc=None):
	transitions = frappe.get_all('Workflow Transition',
		fields=['allowed', 'action', 'state', 'allow_self_approval', 'next_state', '`condition`'],
		filters=[['parent', '=', workflow_name],
		['state', '=', state]])

	transitions_to_return = []

	for transition in transitions:
		is_next_state_optional = get_state_optional_field_value(workflow_name, transition.next_state)
		# skip transition if next state of the transition is optional
		if transition.condition and not frappe.safe_eval(transition.condition, None, {'doc': doc.as_dict()}):
			continue
		if is_next_state_optional:
			continue
		transitions_to_return.append(transition)

	return transitions_to_return

def get_state_optional_field_value(workflow_name, state):
	return frappe.get_cached_value('Workflow Document State', {
		'parent': workflow_name,
		'state': state
	}, 'is_optional_state')

#====================================================================================================================================================
# ON IMPORTANT ACTIONS ON DOCUMENT, PUBLISH A CALL TO UTILITIES.JS SO THAT THE USER CAN BE FORCED TO ENTER A COMMENT/MEMO.
#====================================================================================================================================================
def comment_on_action(doc, state):
	decision = """Saved document"""
	if state == "on_cancel":
		decision = """Cancel document"""
	elif state == "before_submit":
		decision = """Approve document"""
	
	frappe.publish_realtime('doc_comment'+doc.get('name'), {"doc": doc, 'doc_type': doc.get('doctype'),'doc_name': doc.get('name'), 'decision': decision}, user=frappe.session.user)
	#frappe.msgprint("""The doctype ={0} and the docname = {1} """.format(doc.get('doctype'), doc.get('name')))
	#this_doctype = """{{0}}""".format(doc.get('doctype'))
	#this_docname = """{{0}}""".format(doc.get('name'))
	#msgvar = """
	#var docType = '""" + doc.get('doctype') + """';
	#var docName = '""" + doc.get('name') + """';
	#frappe.prompt([
	#	{
	#		label: 'Enter narative for your decision',
	#		fieldtype: 'Small Text',
	#		reqd: true,
	#		fieldname: 'reason'
	#	}],
	#	function(args){
	#		console.log('Reason: ' + args.reason);
	#		//INSERT COMMENT.
	#		//frappe.get_doc(docType, docName).add_comment(frappe.session.user + ' - Document Action Memo : ' + args.reason);
	#		var commentStr = frappe.session.user + ' - Document Action Memo : ' + args.reason;
	#		var comment  = [];
	#		comment["comment"] = commentStr;
	#		comment["comment_by"] = frappe.session.user;
	#		
	#		frappe.publish_realtime('new_comment', comment, doctype = docType, docname = docName)
	#	}
	#);
	#"""
	
	#frappe.msgprint(msgvar)
	 
	#frappe.publish_realtime(event='eval_js', message=msgvar, user=frappe.session.user, doctype = doc.get('doctype'), docname = doc.get('name'))
#====================================================================================================================================================
# VALIDATE THE BUDGET ON SUBMIT AND ALERT IF BUDGET NOT AVAILABLE.
#====================================================================================================================================================
def validate_budget(doc, state):
	purchase_order_items = doc.get("items")
	unique_departments = []
	unique_expense_accounts = []
	payload = []
	row = {}
	
	#GET FISCAL YEAR DETAILS
	fiscal_year_details = get_fiscal_year(today())
	fiscal_year = fiscal_year_details[0]
	fiscal_year_starts = fiscal_year_details[1]
	fiscal_year_ends = fiscal_year_details[2]
	
	for itemrow in purchase_order_items:
		expense_account = itemrow.expense_account
		this_department = itemrow.department
		#GET UNIQUE LIST OF EXPENSE ACCOUNTS
		if expense_account not in unique_expense_accounts:
			unique_expense_accounts.append(expense_account)
		#GET UNIQUE LIST OF DEPARTMENTS
		if this_department not in unique_departments:
			unique_departments.append(this_department)
	
	for department in unique_departments:
		for expense_account in unique_expense_accounts:
			total = 0.0
			for itemrow in purchase_order_items:
				if expense_account and expense_account == itemrow.expense_account and department and itemrow.department == department:
					total = total + itemrow.amount
			row['department'] = department
			row['expense_account'] = expense_account
			row['amount'] = total
			payload.append(row)
		
	for itemrow in payload:
		department = itemrow['department']
		expense_account = itemrow['expense_account']
		amount = itemrow['amount']
		
		#1 GET BUDGET ID
		budget = frappe.db.get_value('Budget', {'department': department,"fiscal_year": fiscal_year, "docstatus":"1"}, 'name')
		
		#2 GET BUDGET AMOUNT:
		budget_amount = frappe.db.get_value('Budget Account', {'parent':budget, "account":expense_account, "docstatus":"1"}, 'budget_amount')
		
		#3. GET SUM OF ALL APPROVED PURCHASE ORDERS:
		total_commitments =  frappe.get_list('Purchase Order Item',
			filters = {
				'department':department,
				'expense_account':expense_account,
				 "creation": [">=", fiscal_year_starts],
				 "creation": ["<", fiscal_year_ends],
				 "docstatus": ["=", 1]
			},
			fields = "sum(`tabPurchase Order Item`.amount) as total_amount",
			order_by = 'creation',
			group_by='department',
			#page_length=2000
			ignore_permissions = True,
			#as_list=False
		)
		#commitments = total_commitments[0].total_amount 
		sql_department_expense_amount = _("""SELECT SUM(amount) as total_amount from `tabPurchase Order Item` WHERE department = '{0}' AND expense_account = '{1}' AND creation >= '{2}' AND creation < '{3}' AND  docstatus = 1""").format(department, expense_account, fiscal_year_starts, fiscal_year_ends)
		#frappe.msgprint(sql_department_expense_amount)
		total_commitments = frappe.db.sql(sql_department_expense_amount)
		if total_commitments and total_commitments[0][0]:
			commitments = total_commitments[0][0]
		if commitments is None:
			commitments = 0.0
		if budget_amount is None:
			budget_amount = 0.0
		balance = float(budget_amount) - float(commitments)
		#frappe.msgprint("""Budget Amount: """ + str(budget_amount) + """,  Total Committments: """ + str(commitments) + """, fiscal_year_starts: """ + str(fiscal_year_starts) )
		if(float(balance) < float(amount) ):
			frappe.throw("""Sorry, this order will not proceed because requests for Department [<b>"""+department+"""</b>] Expense account [<b>"""+expense_account+"""</b>] exceed the current vote balance. <br><br> Vote Balance: [<b>"""+str(balance)+"""</b>]<br>Needed Amount:[<b>"""+str(amount)+"""</b>] """, title = """Budget Exceeded!""")
	process_workflow_log(doc, state)