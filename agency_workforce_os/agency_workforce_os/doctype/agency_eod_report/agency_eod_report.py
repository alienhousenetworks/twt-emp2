import frappe
from frappe import _
from frappe.model.document import Document


class AgencyEODReport(Document):
    def validate(self):
        if self.report_date and self.employee and self.status == "Submitted":
            duplicate = frappe.db.exists("Agency EOD Report", {
                "employee": self.employee, "report_date": self.report_date,
                "status": "Submitted", "name": ["!=", self.name or ""],
            })
            if duplicate:
                frappe.throw(_("A submitted report already exists for this employee and date."))
