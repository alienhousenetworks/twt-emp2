import frappe
from frappe import _
from frappe.model.document import Document


class AgencyFeedPost(Document):
    def validate(self):
        if self.content and len(self.content) > 10000:
            frappe.throw(_("Post content cannot exceed 10,000 characters."))
