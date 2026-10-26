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
3. Link each Frappe User to the Employee record and grant the minimum required roles.
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
Validate session cookies, CSRF, TLS, logout and session expiry against the deployed Frappe version before release.

## Implemented in this milestone
- Authenticated employee workspace, assigned-task view and visibility-scoped feed.
- Feed post creation plus API and DocTypes for comments and reactions.
- EOD submissions with duplicate-submission protection and manager review workflow state.
- Permission-aware employee directory and manager-gated employee create/update API.
- Attendance history and Leave Application self-service request/list APIs.
- Project and Lead/Opportunity read APIs plus Lead creation API.
- Manager-only operational counts from live ERPNext database records.
- React and Flutter workspace foundations.

## Remaining enterprise rollout work
This is not a verified production-ready release. Exact Frappe/ERPNext version compatibility, migration behavior, permissions, builds and integration tests must be checked on a running site.

Still required: complete employee admin UI and manager hierarchy; shifts and attendance approvals; onboarding/document workflows, appraisals and payroll integration; EOD drafts, task-linked evidence, reminders and notifications; feed attachments, mentions, bookmarks and moderation; opportunity editing and follow-up schedules; client workspaces and sales-to-delivery handover; official WhatsApp Business Platform credentials, signed webhooks, deduplication, managed inbox and delivery tracking; AI agent queue with allow-listed tools, approval gates, audit and idempotency; push notifications, offline sync and automated backend/web/mobile tests.

## No fake data policy
The UI should display records returned by ERPNext. Missing permissions and unavailable endpoints are errors/unavailable states, never invented employee counts, attendance, lead values, AI results or integration delivery statuses.
