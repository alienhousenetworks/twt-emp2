import frappe


def after_install():
    """Create the app role idempotently; administrators still grant it explicitly."""
    if not frappe.db.exists("Role", "Agency Employee"):
        frappe.get_doc({"doctype": "Role", "role_name": "Agency Employee", "desk_access": 1}).insert(ignore_permissions=True)
