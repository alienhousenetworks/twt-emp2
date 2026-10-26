# Agency Workforce OS

ERPNext source is preserved under `erpnext/`. This is a separate custom Frappe app: it extends ERPNext through DocTypes and APIs rather than modifying ERPNext core or duplicating its Employee, Task, Project, Attendance or Leave records.

## Install
Install the custom app into a compatible Frappe bench (this repository is the ERPNext app source, not a complete bench with Frappe, site config, database and workers):
```bash
bench --site <site> install-app agency_workforce_os
bench --site <site> migrate
bench build
```
Ensure the authenticated Frappe User is linked to an Employee record and assign the Agency Employee role. Use a test site before production.

## Implemented foundation
- Agency Feed Post and Agency EOD Report DocTypes.
- Authenticated workspace/feed/create-post/EOD APIs.
- React workspace starter and Flutter mobile starter using Frappe APIs.
- ERPNext remains the system of record for existing business data.

## Not yet complete
This is not the entire PRD implementation. Managed WhatsApp Business inbox/webhooks, internal chat, push notifications, complete HR lifecycle workflows, CRM-specific workspaces, GitHub/Figma/marketing integrations, advanced analytics, AI orchestration and production load/security validation still need implementation. No integration is claimed as connected without configuration and live verification.
