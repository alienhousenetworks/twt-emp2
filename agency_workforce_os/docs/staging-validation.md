# Agency Workforce OS — Staging validation runbook

This checklist is intended for a disposable staging site that matches the target Frappe, ERPNext and HRMS versions. It has not been executed against a live site as part of this repository change.

## 1. Preflight and install

Record the actual deployed versions first:

```bash
bench version
bench --site <staging-site> list-apps
```

Back up staging, install HRMS if required, then install/migrate the custom app:

```bash
bench --site <staging-site> backup --with-files
bench --site <staging-site> install-app agency_workforce_os
bench --site <staging-site> migrate
bench build
bench restart
```

If the app is already installed, do not run `install-app` again; run `migrate` after deploying updated code. Confirm DocTypes `Agency WhatsApp Conversation`, `Agency WhatsApp Message`, and `Agency WhatsApp Event` exist.

## 2. Identity and role matrix

Create staging users linked to Employee records. Test separate sessions as:
- Employee without HR/Sales roles.
- HR User / HR Manager.
- Sales User / Sales Manager.
- System Manager.

Expected: all workspace APIs require login and an Employee link; non-WhatsApp roles cannot list conversations, read messages, send replies, or change status; authorized roles can access the inbox. Do not use only an administrator session for validation.

## 3. WhatsApp private configuration

Set these in the site's private configuration, never in source control or frontend variables:

```json
{
  "whatsapp_verify_token": "<random-secret>",
  "whatsapp_app_secret": "<Meta-app-secret>",
  "whatsapp_access_token": "<Meta-system-user-token>",
  "whatsapp_phone_number_id": "<phone-number-id>",
  "whatsapp_graph_api_version": "v21.0"
}
```

Use a Graph API version supported by the Meta app. Restart workers after changing secrets.

## 4. Webhook tests

Configure Meta's webhook URL as `https://<staging-host>/api/method/agency_workforce_os.api.whatsapp_webhook` and subscribe to inbound `messages` and outbound `statuses`.

| Test | Expected result |
|---|---|
| GET with correct subscribe mode and verify token | Returns challenge text |
| GET with wrong token | HTTP 403 |
| POST without signature or with wrong HMAC | HTTP 403; no event/message persisted |
| Valid signed inbound text | Event, conversation and inbound message persisted |
| Same provider message ID delivered twice | One message record only |
| Payload contains multiple entries/messages | Every distinct message persisted |
| Signed delivery status callback | Existing outbound status becomes Sent/Delivered/Read/Failed |
| Invalid JSON or oversized body | 400/413; no message processing |
| Unknown status provider ID | Event accepted; no unrelated message modified |

Use a genuine Meta-signed payload or a controlled harness that computes HMAC-SHA256 over the exact raw request body with the configured app secret. Never disable signature validation to make a test pass.

## 5. Outbound reply tests

1. Open the inbox as an authorized HR/Sales user.
2. Select an inbound conversation and send a short text reply.
3. Expected immediate UI state: Queued, not Delivered.
4. Check worker logs and the message record.
5. On provider acceptance, expect a provider message ID and Sent status.
6. On signed status callback, expect Delivered or Read.
7. With missing credentials or provider rejection, expect Failed with an error; no success should be claimed.
8. Verify closed/archived conversations reject replies.
9. Test outside Meta's free-form reply window; surface provider rejection instead of claiming delivery.

## 6. Operational security

- Confirm HTTPS and secure session cookies.
- Keep Frappe CSRF checks enabled for authenticated POST calls.
- Keep tokens out of logs, error messages, browser bundles and Git.
- Test role access using direct API requests, not only hidden UI controls.
- Define contact-data retention/deletion rules before production.
- Monitor failed jobs and webhook delivery; add retry/backoff and alerts before relying on this inbox operationally.

## 7. Release evidence

Attach version output, migration logs, role-matrix results, sanitized webhook tests, worker logs and screenshots of message status transitions to the release ticket. Do not mark staging validated until expected results are observed.
