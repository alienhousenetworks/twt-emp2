import frappe
from frappe.model.document import Document


class AgencyFeedComment(Document):
    def validate(self):
        self.content = (self.content or "").strip()
        if not self.content or len(self.content) > 4000:
            frappe.throw("Comment must contain 1–4000 characters.")
