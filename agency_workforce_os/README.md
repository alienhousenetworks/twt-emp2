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
- React navigation for Overview, People, Feed, Tasks, EOD, Attendance/Leave, Projects, CRM, WhatsApp inbox, AI Workforce and Management.
- Flutter login/session shell plus Home, Feed, Tasks, EOD, People, Leave, Projects, CRM and Profile views.
- Allow-listed agent request and manager approval queue. Approval queues read-only deterministic Task/EOD data agents with source DocType, record count and verification timestamp in output; no generative model is used. Unsupported agent adapters fail closed without producing output.
- WhatsApp webhook challenge/signature verification, inbound conversation/message persistence, deduplicated provider IDs, message-status reconciliation, role-gated inbox API, and queued outbound text replies through the official WhatsApp Cloud API worker. Delivery remains pending until a verified provider status webhook is received.
- GitHub Actions checks for custom-app Python compilation, DocType JSON, web build and Flutter analysis.

## Configure WhatsApp webhook intake
Set the following keys in the site's private configuration (never commit real secrets):
```json
{
  "whatsapp_verify_token": "replace-with-a-long-random-verification-token",
  "whatsapp_app_secret": "Meta-app-secret-from-your-app-settings",
  "whatsapp_access_token": "long-lived-system-user-access-token",
  "whatsapp_phone_number_id": "your-WhatsApp-phone-number-id",
  "whatsapp_graph_api_version": "v21.0"
}
```
Configure Meta's webhook URL as `https://<your-site>/api/method/agency_workforce_os.api.whatsapp_webhook` and subscribe to inbound `messages` and outbound `statuses` webhook fields. The web inbox is available to authorized HR and Sales roles. Outbound text replies are queued and sent by a Frappe background worker. The API records provider IDs and reconciles `sent`, `delivered`, `read`, and `failed` status callbacks. The worker does not claim delivery merely because Meta accepted a message.

Before production, verify challenge/signature, duplicate webhook, multiple-message payload, status update, provider rejection and worker failure cases on staging. Add template-message support, operational retry/backoff, assignment/ownership controls, retention rules and monitoring before describing the inbox as a fully managed enterprise contact center.

## Important limitations
This is not a verified production-ready release. No live ERPNext site was available here. CI catches static/build issues but does not replace bench installation, migration, permissions or integration tests against the exact deployed Frappe/ERPNext version.

Still required: full employee administration UI and manager hierarchy; shifts and attendance capture/approval; onboarding/document workflows, appraisals and payroll integration; EOD drafts, task-linked evidence, reminders and notification delivery; feed attachments, bookmarks and moderation; opportunity editing, follow-up schedules, client workspaces and sales-to-delivery handover; WhatsApp templates, retries/backoff, assignment/ownership, retention and monitoring; production AI-provider adapters for campaign brief, lead research and project risk review; richer tool-level audit and idempotency; push notifications and robust offline queue/sync; comprehensive automated permission/security/integration tests.

## No fake data policy
The UI displays records returned by ERPNext. Missing permissions and unavailable endpoints are errors/unavailable states, never invented employee counts, attendance, lead values, AI results or integration delivery statuses.
