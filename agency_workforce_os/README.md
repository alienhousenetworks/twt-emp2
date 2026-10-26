# Agency Workforce OS

A custom Frappe app layered on ERPNext for an agency spanning software development, AI, digital marketing and creative delivery. ERPNext remains the source of truth for Employees, Tasks, Projects, Attendance, Leave Applications, Leads and Opportunities.

## Repository layout
- `erpnext-develop/` and `erpnext-develop.zip`: ERPNext source snapshot.
- `agency_workforce_os/`: separate custom Frappe app package.
- `web/`: React/Vite workspace.
- `mobile/`: Flutter client.

This repository is not a complete Frappe Bench. It does not include a configured site database, site_config, workers or a complete Frappe Framework environment.

## Install on a compatible bench
1. Copy the `agency_workforce_os` app folder into the bench `apps/` directory or publish it as a separate Git repository and use `bench get-app`.
2. Run:
   ```bash
   bench --site <site> install-app agency_workforce_os
   bench --site <site> migrate
   bench build
   ```
3. Link each Frappe User to an Employee record and grant the minimum required roles.
4. Validate migrations and role permissions on staging before production.

## Web client
```bash
cd web
cp .env.example .env
# Set VITE_FRAPPE_URL to the HTTPS Frappe origin, or leave empty for same-origin hosting.
npm install
npm run build
npm run dev
```
Do not disable CSRF to make cross-origin requests work. Production should use HTTPS and a reviewed cookie/CORS/SameSite configuration.

## Flutter client
```bash
cd mobile
flutter pub get
flutter run --dart-define=FRAPPE_URL=https://your-frappe-host.example
```
The mobile client includes Frappe username/password login, stores the session id in secure storage, and attempts server logout. Validate session cookies, CSRF token exchange, TLS, logout and session expiry against the deployed Frappe version before release.

## Implemented in this milestone
- Authenticated employee workspace, assigned-task view and visibility-scoped feed.
- Feed post creation, comment/reaction DocTypes and API endpoints.
- EOD submissions with duplicate-submission protection and manager review/return state.
- Employee directory and manager-gated Employee create/update API.
- Attendance history and Leave Application self-service request/list APIs.
- Project and Lead/Opportunity read APIs, Lead creation endpoint and manager-only operational counts.
- React navigation for Overview, People, Feed, Tasks, EOD, Attendance/Leave, Projects, CRM, AI Workforce and Management.
- Flutter login/session shell plus Home, Feed, Tasks, EOD, People, Leave, Projects, CRM and Profile views.
- Allow-listed agent request and manager approval queue. Approval is recorded, but no agent executes automatically.
- WhatsApp webhook verification endpoint using configured site secrets and idempotent event persistence. It does not send outbound messages or constitute a managed inbox.
- GitHub Actions checks for custom-app Python compilation, DocType JSON, web build and Flutter analysis.

## Configure WhatsApp webhook intake
Set the following keys in the site's private configuration (never commit real secrets):
```json
{
  "whatsapp_verify_token": "replace-with-a-long-random-verification-token",
  "whatsapp_app_secret": "Meta-app-secret-from-your-app-settings"
}
```
Configure Meta's webhook URL as `https://<your-site>/api/method/agency_workforce_os.api.whatsapp_webhook` and subscribe to the required WhatsApp Business Account webhook fields. Test challenge verification and signed POST payloads in a staging site. This endpoint stores verified events only; inbox UI, message sending, template management, retry workers and delivery reconciliation remain outstanding.

## Important limitations
This is not a verified production-ready release. No live ERPNext site was available here. CI catches static/build issues but does not replace bench installation, migration, permissions or integration tests against the exact deployed Frappe/ERPNext version.

Still required: full employee administration UI and manager hierarchy; shifts and attendance capture/approval; onboarding/document workflows, appraisals and payroll integration; EOD drafts, task-linked evidence, reminders and notification delivery; feed attachments, mentions, bookmarks and moderation; opportunity editing, follow-up schedules, client workspaces and sales-to-delivery handover; official WhatsApp managed inbox/outbound delivery; a reviewed agent execution worker with allow-listed tools, audit and idempotency; push notifications and robust offline queue/sync; comprehensive automated permission/security/integration tests.

## No fake data policy
The UI displays records returned by ERPNext. Missing permissions and unavailable endpoints are errors/unavailable states, never invented employee counts, attendance, lead values, AI results or integration delivery statuses.
