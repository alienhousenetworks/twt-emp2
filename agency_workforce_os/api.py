"""Permission-aware API endpoints; ERPNext remains the source of truth."""
import frappe
from frappe import _
from frappe.utils import getdate, now_datetime


def _employee_for_session():
    if frappe.session.user == "Guest":
        frappe.throw(_("Login required"), frappe.PermissionError)
    employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if not employee:
        frappe.throw(_("Your Frappe user is not linked to an Employee record."), frappe.PermissionError)
    return employee


@frappe.whitelist()
def get_workspace():
    employee = _employee_for_session()
    emp = frappe.get_doc("Employee", employee)
    tasks = frappe.get_all(
        "Task", filters={"_assign": ["like", "%" + frappe.session.user + "%"]},
        fields=["name", "subject", "status", "priority", "exp_end_date", "project"],
        order_by="modified desc", limit_page_length=20,
    )
    return {
        "employee": {"name": emp.name, "employee_name": emp.employee_name,
                     "department": emp.department, "designation": emp.designation},
        "tasks": tasks, "feed": list_feed(limit=20),
        "data_status": "available", "generated_at": now_datetime(),
    }


@frappe.whitelist()
def list_feed(limit=30):
    _employee_for_session()
    limit = max(1, min(int(limit or 30), 100))
    rows = frappe.get_all(
        "Agency Feed Post",
        filters={"visibility": ["in", ["Company", "Team"]]},
        fields=["name", "owner", "creation", "post_type", "content", "department", "project", "visibility"],
        order_by="creation desc", limit_page_length=limit,
    )
    return [row for row in rows if frappe.has_permission("Agency Feed Post", "read", row.name)]


@frappe.whitelist(methods=["POST"])
def create_feed_post(content, post_type="General Update", visibility="Team", department=None, project=None):
    employee = _employee_for_session()
    content = (content or "").strip()
    if not content or len(content) > 10000:
        frappe.throw(_("Post content must contain 1–10000 characters."))
    allowed_types = {"General Update", "Progress Update", "Help Request", "Achievement", "EOD Report", "Question", "Blocker"}
    if post_type not in allowed_types:
        frappe.throw(_("Unsupported post type."))
    if visibility not in {"Team", "Company", "Private"}:
        frappe.throw(_("Unsupported visibility."))
    if project:
        frappe.get_doc("Project", project).check_permission("read")
    doc = frappe.get_doc({"doctype": "Agency Feed Post", "employee": employee, "content": content,
                          "post_type": post_type, "visibility": visibility, "department": department, "project": project})
    doc.insert()
    return {"name": doc.name, "creation": doc.creation, "status": "created"}


@frappe.whitelist(methods=["POST"])
def submit_eod(report_date, completed_work, pending_work="", blockers="", next_day_plan="", help_needed="", audience="Team"):
    employee = _employee_for_session()
    if audience not in {"Private", "Team", "Department"}:
        frappe.throw(_("Unsupported report audience."))
    date_value = getdate(report_date)
    if frappe.db.exists("Agency EOD Report", {"employee": employee, "report_date": date_value, "status": "Submitted"}):
        frappe.throw(_("A submitted EOD report already exists for this date."))
    doc = frappe.get_doc({
        "doctype": "Agency EOD Report", "employee": employee, "report_date": date_value,
        "completed_work": (completed_work or "").strip(), "pending_work": (pending_work or "").strip(),
        "blockers": (blockers or "").strip(), "next_day_plan": (next_day_plan or "").strip(),
        "help_needed": (help_needed or "").strip(), "audience": audience, "status": "Submitted",
        "submitted_at": now_datetime(),
    })
    doc.insert()
    return {"name": doc.name, "status": doc.status, "submitted_at": doc.submitted_at}
