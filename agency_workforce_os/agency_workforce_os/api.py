"""Agency Workforce OS APIs layered on ERPNext/Frappe; ERPNext remains the source of truth."""
import frappe
import hashlib
import hmac
import json
from frappe import _
from frappe.utils import getdate, now_datetime

FEED_TYPES = {"General Update", "Progress Update", "Help Request", "Achievement", "EOD Report", "Question", "Blocker"}


def _employee_for_session():
    if frappe.session.user == "Guest":
        frappe.throw(_("Login required"), frappe.PermissionError)
    employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if not employee:
        frappe.throw(_("Your Frappe user is not linked to an Employee record."), frappe.PermissionError)
    return employee


def _is_manager():
    return bool(set(frappe.get_roles(frappe.session.user)).intersection(
        {"System Manager", "HR Manager", "HR User", "Projects Manager", "Sales Manager"}))


def _require_manager():
    if not _is_manager():
        frappe.throw(_("Manager or administrator permission required."), frappe.PermissionError)


def _department(employee):
    return frappe.db.get_value("Employee", employee, "department")


@frappe.whitelist()
def get_workspace():
    employee = _employee_for_session()
    emp = frappe.get_doc("Employee", employee)
    tasks = frappe.get_list("Task", filters={"_assign": ["like", "%" + frappe.session.user + "%"]},
        fields=["name", "subject", "status", "priority", "exp_end_date", "project"],
        order_by="modified desc", limit_page_length=50)
    return {"employee": {"name": emp.name, "employee_name": emp.employee_name,
        "department": emp.department, "designation": emp.designation, "company": emp.company,
        "image": emp.image}, "tasks": tasks, "feed": list_feed(limit=20),
        "data_status": "available", "generated_at": now_datetime(), "permissions": {"can_manage": _is_manager()}}


@frappe.whitelist()
def list_feed(limit=30):
    employee = _employee_for_session()
    department = _department(employee)
    limit = max(1, min(int(limit or 30), 100))
    filters = [{"visibility": "Company"}, {"visibility": "Private", "employee": employee}]
    if department:
        filters.append({"visibility": "Team", "department": department})
    rows = frappe.get_list("Agency Feed Post", or_filters=filters,
        fields=["name", "employee", "owner", "creation", "modified", "post_type", "content",
                "department", "project", "visibility"], order_by="creation desc", limit_page_length=limit)
    employee_ids = list({r.employee for r in rows if r.employee})
    names = {r.name: r.employee_name for r in frappe.get_all("Employee",
        filters={"name": ["in", employee_ids]}, fields=["name", "employee_name"])} if employee_ids else {}
    for row in rows:
        row["employee_name"] = names.get(row.employee, row.owner)
    return rows


@frappe.whitelist(methods=["POST"])
def create_feed_post(content, post_type="General Update", visibility="Team", department=None, project=None):
    employee = _employee_for_session()
    content = (content or "").strip()
    if not content or len(content) > 10000:
        frappe.throw(_("Post content must contain 1–10000 characters."))
    if post_type not in FEED_TYPES or visibility not in {"Team", "Company", "Private"}:
        frappe.throw(_("Unsupported post type or visibility."))
    own_department = _department(employee)
    if visibility == "Team":
        department = department or own_department
        if department != own_department:
            frappe.throw(_("Team posts can only target your own department."), frappe.PermissionError)
    elif visibility == "Company":
        department = None
    else:
        department = own_department
    if project:
        frappe.get_doc("Project", project).check_permission("read")
    doc = frappe.get_doc({"doctype": "Agency Feed Post", "employee": employee, "content": content,
        "post_type": post_type, "visibility": visibility, "department": department, "project": project})
    doc.insert()
    return {"name": doc.name, "creation": doc.creation, "status": "created"}


@frappe.whitelist(methods=["POST"])
def add_feed_comment(post, content):
    employee = _employee_for_session()
    content = (content or "").strip()
    if not content or len(content) > 4000:
        frappe.throw(_("Comment must contain 1–4000 characters."))
    parent = frappe.get_doc("Agency Feed Post", post)
    parent.check_permission("read")
    if parent.visibility == "Private" and parent.employee != employee:
        frappe.throw(_("You cannot comment on this post."), frappe.PermissionError)
    doc = frappe.get_doc({"doctype": "Agency Feed Comment", "post": post, "employee": employee, "content": content})
    doc.insert()
    return {"name": doc.name, "status": "created"}


@frappe.whitelist(methods=["POST"])
def toggle_feed_reaction(post, reaction="Like"):
    employee = _employee_for_session()
    if reaction not in {"Like", "Celebrate", "Support", "Insightful"}:
        frappe.throw(_("Unsupported reaction."))
    parent = frappe.get_doc("Agency Feed Post", post)
    parent.check_permission("read")
    existing = frappe.db.get_value("Agency Feed Reaction",
        {"post": post, "employee": employee, "reaction": reaction}, "name")
    if existing:
        frappe.delete_doc("Agency Feed Reaction", existing)
        return {"active": False, "reaction": reaction}
    doc = frappe.get_doc({"doctype": "Agency Feed Reaction", "post": post, "employee": employee, "reaction": reaction})
    doc.insert()
    return {"active": True, "reaction": reaction}


@frappe.whitelist(methods=["POST"])
def submit_eod(report_date, completed_work, pending_work="", blockers="", next_day_plan="", help_needed="", audience="Team"):
    employee = _employee_for_session()
    if audience not in {"Private", "Team", "Department"}:
        frappe.throw(_("Unsupported report audience."))
    completed_work = (completed_work or "").strip()
    if not completed_work:
        frappe.throw(_("Describe at least one completed item before submitting."))
    date_value = getdate(report_date)
    if date_value > getdate():
        frappe.throw(_("EOD report date cannot be in the future."))
    if frappe.db.exists("Agency EOD Report", {"employee": employee, "report_date": date_value,
            "status": ["in", ["Submitted", "Reviewed"]]}):
        frappe.throw(_("A submitted EOD report already exists for this date."))
    doc = frappe.get_doc({"doctype": "Agency EOD Report", "employee": employee, "report_date": date_value,
        "completed_work": completed_work, "pending_work": (pending_work or "").strip(),
        "blockers": (blockers or "").strip(), "next_day_plan": (next_day_plan or "").strip(),
        "help_needed": (help_needed or "").strip(), "audience": audience, "status": "Submitted",
        "submitted_at": now_datetime()})
    doc.insert()
    return {"name": doc.name, "status": doc.status, "submitted_at": doc.submitted_at}


@frappe.whitelist()
def list_eod_reports(report_date=None, status=None, limit=50):
    employee = _employee_for_session()
    filters = {} if _is_manager() else {"employee": employee}
    if report_date:
        filters["report_date"] = getdate(report_date)
    if status in {"Draft", "Submitted", "Reviewed", "Returned"}:
        filters["status"] = status
    rows = frappe.get_list("Agency EOD Report", filters=filters,
        fields=["name", "employee", "report_date", "completed_work", "pending_work", "blockers",
                "next_day_plan", "help_needed", "audience", "status", "submitted_at", "reviewed_by", "review_notes"],
        order_by="report_date desc, modified desc", limit_page_length=max(1, min(int(limit or 50), 100)))
    employee_ids = list({r.employee for r in rows if r.employee})
    names = {r.name: r.employee_name for r in frappe.get_all("Employee",
        filters={"name": ["in", employee_ids]}, fields=["name", "employee_name"])} if employee_ids and _is_manager() else {}
    for row in rows:
        row["employee_name"] = names.get(row.employee, row.employee)
    return rows


@frappe.whitelist(methods=["POST"])
def review_eod(report, decision, review_notes=""):
    _require_manager()
    if decision not in {"Reviewed", "Returned"}:
        frappe.throw(_("Decision must be Reviewed or Returned."))
    doc = frappe.get_doc("Agency EOD Report", report)
    if doc.status != "Submitted":
        frappe.throw(_("Only submitted reports can be reviewed."))
    doc.status = decision
    doc.reviewed_by = frappe.session.user
    doc.review_notes = (review_notes or "").strip()[:4000]
    doc.reviewed_at = now_datetime()
    doc.save()
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def list_employees(search=None, department=None, status=None, limit=100):
    _employee_for_session()
    filters = {}
    if department:
        filters["department"] = department
    if status in {"Active", "Inactive", "Left"}:
        filters["status"] = status
    fields = ["name", "employee_name", "user_id", "department", "designation", "company", "status", "date_of_joining", "image"]
    kwargs = {"filters": filters, "fields": fields, "order_by": "employee_name asc",
        "limit_page_length": max(1, min(int(limit or 100), 200))}
    if search:
        term = "%" + search.strip()[:100] + "%"
        kwargs["or_filters"] = [{"employee_name": ["like", term]}, {"name": ["like", term]}]
    rows = frappe.get_list("Employee", **kwargs)
    return {"employees": rows, "can_manage": _is_manager(), "count": len(rows)}


@frappe.whitelist(methods=["POST"])
def save_employee(employee=None, employee_name=None, company=None, date_of_joining=None,
                  department=None, designation=None, user_id=None, status="Active", gender=None):
    _require_manager()
    if status not in {"Active", "Inactive", "Left"}:
        frappe.throw(_("Invalid employee status."))
    if not (employee_name or "").strip() or not company:
        frappe.throw(_("Employee name and company are required."))
    if user_id and not frappe.db.exists("User", user_id):
        frappe.throw(_("The selected Frappe user does not exist."))
    linked = frappe.db.get_value("Employee", {"user_id": user_id}, "name") if user_id else None
    if linked and linked != employee:
        frappe.throw(_("This user is already linked to another employee."))
    if employee:
        doc = frappe.get_doc("Employee", employee)
        doc.check_permission("write")
        doc.employee_name, doc.company = employee_name.strip(), company
        doc.department, doc.designation, doc.user_id, doc.status = department, designation, user_id, status
        if date_of_joining:
            doc.date_of_joining = getdate(date_of_joining)
        if gender:
            doc.gender = gender
        doc.save()
    else:
        doc = frappe.get_doc({"doctype": "Employee", "employee_name": employee_name.strip(),
            "company": company, "date_of_joining": getdate(date_of_joining) if date_of_joining else getdate(),
            "department": department, "designation": designation, "user_id": user_id,
            "status": status, "gender": gender or "Prefer not to say"})
        doc.insert()
    return {"name": doc.name, "employee_name": doc.employee_name, "status": "saved"}


@frappe.whitelist()
def list_my_attendance(from_date=None, to_date=None, limit=60):
    employee = _employee_for_session()
    filters = {"employee": employee}
    if from_date and to_date:
        filters["attendance_date"] = ["between", [getdate(from_date), getdate(to_date)]]
    elif from_date:
        filters["attendance_date"] = [">=", getdate(from_date)]
    elif to_date:
        filters["attendance_date"] = ["<=", getdate(to_date)]
    return frappe.get_list("Attendance", filters=filters,
        fields=["name", "attendance_date", "status", "shift", "working_hours", "leave_type"],
        order_by="attendance_date desc", limit_page_length=max(1, min(int(limit or 60), 100)))


@frappe.whitelist(methods=["POST"])
def request_leave(leave_type, from_date, to_date, reason, half_day=0):
    employee = _employee_for_session()
    reason = (reason or "").strip()
    start, end = getdate(from_date), getdate(to_date)
    if end < start:
        frappe.throw(_("To date cannot be before from date."))
    if start < getdate():
        frappe.throw(_("Leave requests cannot start in the past through this self-service form."))
    if not reason or len(reason) > 2000:
        frappe.throw(_("Please provide a reason (maximum 2000 characters)."))
    if not frappe.db.exists("Leave Type", leave_type):
        frappe.throw(_("Unknown leave type."))
    doc = frappe.get_doc({"doctype": "Leave Application", "employee": employee,
        "leave_type": leave_type, "from_date": start, "to_date": end,
        "half_day": int(bool(int(half_day or 0))), "half_day_date": start if int(bool(int(half_day or 0))) else None,
        "description": reason, "status": "Open"})
    doc.insert()
    return {"name": doc.name, "status": doc.status, "message": _("Leave request submitted for HR review.")}


@frappe.whitelist()
def list_my_leave(limit=50):
    employee = _employee_for_session()
    return frappe.get_list("Leave Application", filters={"employee": employee},
        fields=["name", "leave_type", "from_date", "to_date", "total_leave_days", "status", "docstatus"],
        order_by="from_date desc", limit_page_length=max(1, min(int(limit or 50), 100)))


@frappe.whitelist()
def list_projects(limit=50):
    _employee_for_session()
    return frappe.get_list("Project", fields=["name", "project_name", "status", "percent_complete", "expected_end_date", "project_manager"],
        order_by="modified desc", limit_page_length=max(1, min(int(limit or 50), 100)))


@frappe.whitelist()
def list_crm_records(doctype="Lead", search=None, limit=50):
    _employee_for_session()
    if doctype not in {"Lead", "Opportunity"}:
        frappe.throw(_("Only Lead and Opportunity records are supported."))
    if not frappe.has_permission(doctype, "read"):
        frappe.throw(_("CRM read permission required."), frappe.PermissionError)
    fields = ["name", "lead_name", "company_name", "status", "source", "email_id", "mobile_no"] if doctype == "Lead" else ["name", "party_name", "opportunity_type", "status", "opportunity_amount", "transaction_date", "expected_closing"]
    filters = {}
    if search:
        field = "lead_name" if doctype == "Lead" else "party_name"
        filters[field] = ["like", "%" + search.strip()[:100] + "%"]
    return frappe.get_list(doctype, filters=filters, fields=fields, order_by="modified desc",
        limit_page_length=max(1, min(int(limit or 50), 100)))


@frappe.whitelist(methods=["POST"])
def create_lead(lead_name, company_name=None, email_id=None, mobile_no=None, source=None, notes=None):
    _employee_for_session()
    if not frappe.has_permission("Lead", "create"):
        frappe.throw(_("CRM create permission required."), frappe.PermissionError)
    lead_name = (lead_name or "").strip()
    if not lead_name:
        frappe.throw(_("Lead name is required."))
    doc = frappe.get_doc({"doctype": "Lead", "lead_name": lead_name,
        "company_name": (company_name or "").strip() or None, "email_id": (email_id or "").strip() or None,
        "mobile_no": (mobile_no or "").strip() or None, "source": source or None, "notes": notes or None})
    doc.insert()
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def get_management_overview():
    _require_manager()
    return {"employees_active": frappe.db.count("Employee", {"status": "Active"}),
        "employees_total": frappe.db.count("Employee"),
        "open_tasks": frappe.db.count("Task", {"status": ["not in", ["Completed", "Cancelled"]]}),
        "projects_open": frappe.db.count("Project", {"status": ["not in", ["Completed", "Cancelled"]]}),
        "eod_waiting_review": frappe.db.count("Agency EOD Report", {"status": "Submitted"}),
        "leave_open": frappe.db.count("Leave Application", {"status": "Open", "docstatus": 0}),
        "leads_open": frappe.db.count("Lead", {"status": ["not in", ["Converted", "Do Not Contact"]]}),
        "as_of": str(getdate()), "data_status": "live_database_counts"}


@frappe.whitelist()
def list_leave_types():
    _employee_for_session()
    return frappe.get_list("Leave Type", fields=["name"], order_by="name asc", limit_page_length=100)


AGENT_ALLOWLIST = {"task_summarizer", "eod_assistant", "campaign_brief", "lead_research", "project_risk_review"}


@frappe.whitelist(methods=["POST"])
def request_agent_run(agent_key, purpose, input_json="{}"):
    employee = _employee_for_session()
    if agent_key not in AGENT_ALLOWLIST:
        frappe.throw(_("Agent is not in the approved registry."))
    purpose = (purpose or "").strip()
    if not purpose or len(purpose) > 1000:
        frappe.throw(_("Provide a short purpose (maximum 1000 characters)."))
    try:
        payload = json.loads(input_json or "{}") if isinstance(input_json, str) else input_json
    except (TypeError, ValueError):
        frappe.throw(_("Input must be valid JSON."))
    if not isinstance(payload, dict) or len(frappe.as_json(payload)) > 20000:
        frappe.throw(_("Agent input must be a JSON object under 20 KB."))
    doc = frappe.get_doc({"doctype": "Agency Agent Run", "requested_by": frappe.session.user,
        "employee": employee, "agent_key": agent_key, "purpose": purpose,
        "input_json": frappe.as_json(payload), "status": "Pending Approval"})
    doc.insert()
    return {"name": doc.name, "status": doc.status, "message": _("Queued for human approval; no agent has executed yet.")}


@frappe.whitelist()
def list_agent_runs(limit=50):
    employee = _employee_for_session()
    filters = {} if _is_manager() else {"requested_by": frappe.session.user}
    return frappe.get_list("Agency Agent Run", filters=filters,
        fields=["name", "requested_by", "employee", "agent_key", "purpose", "status", "creation",
                "approved_by", "approved_at", "started_at", "finished_at", "error_message"],
        order_by="creation desc", limit_page_length=max(1, min(int(limit or 50), 100)))


@frappe.whitelist(methods=["POST"])
def review_agent_run(run, decision, review_notes=""):
    _require_manager()
    if decision not in {"Approve", "Reject"}:
        frappe.throw(_("Decision must be Approve or Reject."))
    doc = frappe.get_doc("Agency Agent Run", run)
    if doc.status != "Pending Approval":
        frappe.throw(_("Only pending agent requests can be reviewed."))
    doc.status = "Approved" if decision == "Approve" else "Rejected"
    doc.approved_by = frappe.session.user
    doc.approved_at = now_datetime()
    doc.review_notes = (review_notes or "").strip()[:4000]
    doc.save()
    return {"name": doc.name, "status": doc.status,
        "message": _("Approval recorded. Execution remains unavailable until a reviewed worker is configured.")}


def _require_whatsapp_access():
    allowed = {"System Manager", "HR Manager", "HR User", "Sales Manager", "Sales User"}
    if not set(frappe.get_roles(frappe.session.user)).intersection(allowed):
        frappe.throw(_("WhatsApp inbox access is restricted to authorized HR, sales, and system roles."), frappe.PermissionError)


def _whatsapp_conversation(phone, name=None):
    phone = (phone or "").strip()
    if not phone or len(phone) > 32:
        return None
    existing = frappe.db.get_value("Agency WhatsApp Conversation", {"wa_id": phone}, "name")
    if existing:
        doc = frappe.get_doc("Agency WhatsApp Conversation", existing)
        if name and not doc.contact_name:
            doc.contact_name = name[:140]
            doc.save(ignore_permissions=True)
        return doc
    doc = frappe.get_doc({"doctype": "Agency WhatsApp Conversation", "wa_id": phone,
        "contact_name": (name or "")[:140], "status": "Open"})
    doc.insert(ignore_permissions=True)
    return doc


@frappe.whitelist()
def list_whatsapp_conversations(search=None, limit=50):
    _employee_for_session()
    _require_whatsapp_access()
    filters = {"status": ["!=", "Archived"]}
    term = "%" + search.strip()[:80] + "%" if search else None
    or_filters = [{"wa_id": ["like", term]}, {"contact_name": ["like", term]}] if term else None
    return frappe.get_list("Agency WhatsApp Conversation", filters=filters, or_filters=or_filters,
        fields=["name", "wa_id", "contact_name", "status", "last_message_at", "last_message_preview", "modified"],
        order_by="last_message_at desc", limit_page_length=max(1, min(int(limit or 50), 100)))


@frappe.whitelist()
def list_whatsapp_messages(conversation, limit=100):
    _employee_for_session()
    _require_whatsapp_access()
    frappe.get_doc("Agency WhatsApp Conversation", conversation).check_permission("read")
    return frappe.get_list("Agency WhatsApp Message", filters={"conversation": conversation},
        fields=["name", "provider_message_id", "direction", "message_type", "text_body", "status",
                "sent_by", "sent_at", "error_message", "creation"],
        order_by="creation asc", limit_page_length=max(1, min(int(limit or 100), 200)))


@frappe.whitelist(methods=["POST"])
def send_whatsapp_text(conversation, text_body):
    _employee_for_session()
    _require_whatsapp_access()
    body = (text_body or "").strip()
    if not body or len(body) > 4096:
        frappe.throw(_("Message must contain 1–4096 characters."))
    convo = frappe.get_doc("Agency WhatsApp Conversation", conversation)
    convo.check_permission("read")
    if convo.status != "Open":
        frappe.throw(_("Only open conversations can receive replies."))
    if not frappe.conf.get("whatsapp_access_token") or not frappe.conf.get("whatsapp_phone_number_id"):
        frappe.throw(_("WhatsApp outbound credentials are not configured in private site config."))
    msg = frappe.get_doc({"doctype": "Agency WhatsApp Message", "conversation": convo.name,
        "direction": "Outbound", "message_type": "text", "text_body": body,
        "status": "Queued", "sent_by": frappe.session.user})
    msg.insert()
    frappe.enqueue("agency_workforce_os.api._send_whatsapp_message", message_name=msg.name,
        queue="short", enqueue_after_commit=True)
    return {"name": msg.name, "status": "Queued", "message": _("Message queued; delivery is not yet confirmed.")}


def _send_whatsapp_message(message_name):
    """Background worker for the official WhatsApp Cloud API. Secrets stay in site config."""
    import requests
    doc = frappe.get_doc("Agency WhatsApp Message", message_name)
    if doc.status not in {"Queued", "Failed"} or doc.direction != "Outbound":
        return
    token = frappe.conf.get("whatsapp_access_token")
    phone_number_id = frappe.conf.get("whatsapp_phone_number_id")
    version = str(frappe.conf.get("whatsapp_graph_api_version") or "v21.0")
    if not token or not phone_number_id:
        doc.status = "Failed"
        doc.error_message = "WhatsApp Cloud API credentials are not configured."
        doc.save(ignore_permissions=True)
        return
    convo = frappe.get_doc("Agency WhatsApp Conversation", doc.conversation)
    doc.status = "Sending"
    doc.error_message = None
    doc.save(ignore_permissions=True)
    try:
        response = requests.post(
            f"https://graph.facebook.com/{version}/{phone_number_id}/messages",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"messaging_product": "whatsapp", "recipient_type": "individual",
                  "to": convo.wa_id, "type": "text", "text": {"preview_url": False, "body": doc.text_body}},
            timeout=(5, 20))
        payload = response.json() if response.content else {}
        if not response.ok:
            raise RuntimeError(f"WhatsApp API HTTP {response.status_code}: {json.dumps(payload)[:1500]}")
        provider_id = ((payload.get("messages") or [{}])[0]).get("id")
        if not provider_id:
            raise RuntimeError("WhatsApp API response did not include a provider message ID.")
        doc.provider_message_id = provider_id
        doc.status = "Sent"
        doc.error_message = None
        doc.save(ignore_permissions=True)
        convo.last_message_at = now_datetime()
        convo.last_message_preview = doc.text_body[:240]
        convo.save(ignore_permissions=True)
    except Exception as exc:
        doc.status = "Failed"
        doc.error_message = str(exc)[:2000]
        doc.save(ignore_permissions=True)
        frappe.log_error(title="WhatsApp message delivery failed", message=f"{message_name}: {str(exc)[:2000]}")


@frappe.whitelist(methods=["POST"])
def set_whatsapp_conversation_status(conversation, status):
    _employee_for_session()
    _require_whatsapp_access()
    if status not in {"Open", "Closed", "Archived"}:
        frappe.throw(_("Unsupported conversation status."))
    doc = frappe.get_doc("Agency WhatsApp Conversation", conversation)
    doc.check_permission("write")
    doc.status = status
    doc.save()
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def whatsapp_webhook():
    """Verify Meta's challenge/signature and persist events idempotently.

    Configure whatsapp_verify_token and whatsapp_app_secret in the site's private
    config. This endpoint stores inbound events; it does not send messages or
    claim delivery until an inbox worker and WhatsApp credentials are configured.
    """
    if frappe.request.method == "GET":
        verify_token = frappe.conf.get("whatsapp_verify_token")
        mode = frappe.form_dict.get("hub.mode")
        token = frappe.form_dict.get("hub.verify_token")
        challenge = frappe.form_dict.get("hub.challenge")
        if not verify_token or mode != "subscribe" or not hmac.compare_digest(str(token or ""), str(verify_token)):
            frappe.local.response["http_status_code"] = 403
            return {"error": "Webhook verification failed"}
        frappe.local.response["type"] = "text"
        return str(challenge or "")
    secret = frappe.conf.get("whatsapp_app_secret")
    signature = frappe.get_request_header("X-Hub-Signature-256") or ""
    raw = frappe.request.get_data() or b""
    if not secret or not signature.startswith("sha256="):
        frappe.local.response["http_status_code"] = 403
        return {"error": "Webhook signature configuration missing or invalid"}
    expected = "sha256=" + hmac.new(str(secret).encode("utf-8"), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        frappe.local.response["http_status_code"] = 403
        return {"error": "Webhook signature invalid"}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        frappe.local.response["http_status_code"] = 400
        return {"error": "Invalid JSON payload"}
    if not isinstance(payload, dict) or len(raw) > 1024 * 1024:
        frappe.local.response["http_status_code"] = 413 if len(raw) > 1024 * 1024 else 400
        return {"error": "Payload must be a JSON object under 1 MB"}
    changes = [change for entry in (payload.get("entry") or []) for change in (entry.get("changes") or [])]
    values = [change.get("value") or {} for change in changes]
    messages = [message for value in values for message in (value.get("messages") or [])]
    statuses = [status for value in values for status in (value.get("statuses") or [])]
    event_key = hashlib.sha256(raw).hexdigest()
    duplicate = bool(frappe.db.exists("Agency WhatsApp Event", {"event_key": event_key}))
    if not duplicate:
        event = frappe.get_doc({"doctype": "Agency WhatsApp Event", "event_key": event_key,
            "provider_message_id": (messages[0].get("id") if messages else None) or (statuses[0].get("id") if statuses else None),
            "event_type": "message" if messages else "status" if statuses else "other",
            "payload_json": json.dumps(payload, ensure_ascii=False), "processing_status": "Received",
            "received_at": now_datetime()})
        event.insert(ignore_permissions=True)
    contacts = {contact.get("wa_id"): contact.get("profile", {}).get("name")
                for value in values for contact in (value.get("contacts") or [])}
    stored_messages = 0
    for incoming in messages:
        provider_id = incoming.get("id")
        sender = incoming.get("from")
        if not provider_id or not sender or frappe.db.exists("Agency WhatsApp Message", {"provider_message_id": provider_id}):
            continue
        convo = _whatsapp_conversation(sender, contacts.get(sender))
        if not convo:
            continue
        text_body = (incoming.get("text") or {}).get("body") or ""
        msg = frappe.get_doc({"doctype": "Agency WhatsApp Message", "conversation": convo.name,
            "provider_message_id": provider_id, "direction": "Inbound",
            "message_type": incoming.get("type") or "unknown", "text_body": text_body[:4096],
            "status": "Received", "sent_at": now_datetime()})
        msg.insert(ignore_permissions=True)
        convo.last_message_at = now_datetime()
        convo.last_message_preview = (text_body or f"[{incoming.get('type') or 'message'}]")[:240]
        convo.save(ignore_permissions=True)
        stored_messages += 1
    for state in statuses:
        provider_id = state.get("id")
        if not provider_id:
            continue
        msg_name = frappe.db.get_value("Agency WhatsApp Message", {"provider_message_id": provider_id}, "name")
        if msg_name:
            msg = frappe.get_doc("Agency WhatsApp Message", msg_name)
            state_map = {"sent": "Sent", "delivered": "Delivered", "read": "Read", "failed": "Failed"}
            msg.status = state_map.get(state.get("status"), msg.status)
            errors = state.get("errors") or []
            if errors:
                msg.error_message = json.dumps(errors, ensure_ascii=False)[:2000]
            msg.save(ignore_permissions=True)
    frappe.db.commit()
    return {"accepted": True, "duplicate": duplicate, "stored_messages": stored_messages}
