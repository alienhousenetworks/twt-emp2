"""Agency Workforce OS APIs layered on ERPNext/Frappe; ERPNext remains the source of truth."""
import frappe
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
        "data_status": "available", "generated_at": now_datetime()}


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
