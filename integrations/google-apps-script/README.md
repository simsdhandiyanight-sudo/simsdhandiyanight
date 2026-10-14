# Google Apps Script ticket-sync Web App

This Web App accepts authenticated server-to-server ticket rows from Django
and upserts them into the existing `Online_Tickets` and `OnSpot_Tickets` tabs.
New or empty tabs use the current column order from
`backend/apps/payments/sheets.py`.
Each row is keyed by the ticket UUID (`ticket_id`), so multi-ticket bookings
remain separate and retries update rather than duplicate rows.

## Configure the Apps Script project

1. Create a standalone Google Apps Script project and copy `Code.gs` into its
   editor.
2. In **Project Settings → Script Properties**, add:
   - `SPREADSHEET_ID`: the target spreadsheet ID.
   - `WEBHOOK_SECRET`: a long random secret. Generate one locally, for example:
     `python -c "import secrets; print(secrets.token_urlsafe(48))"`
3. Save the script. The account deploying/running it must have Editor access
   to the target spreadsheet.
4. Choose **Deploy → New deployment → Web app**:
   - **Execute as:** Me.
   - **Who has access:** Anyone, so Render can call the endpoint without a
     Google sign-in. The request is authenticated by the secret in its JSON
     body; the secret is never sent to the browser.
5. Deploy and copy the URL ending in `/exec`. Do not use the `/dev` test URL.
   If the account or organization does not permit public Web Apps, deployment
   cannot be used with this unauthenticated server-to-server method.

When changing `Code.gs`, use **Deploy → Manage deployments → Edit → New
version → Deploy**. Keep the deployment URL unless you intentionally create a
new deployment; if it changes, update Render's URL too.

## Configure Render

Set these environment variables on the production Django web service:

- `GOOGLE_APPS_SCRIPT_WEBHOOK_URL`: the deployed `/exec` URL.
- `GOOGLE_APPS_SCRIPT_WEBHOOK_SECRET`: exactly the same value as Script
  Property `WEBHOOK_SECRET`.

Restart/redeploy the web service after saving the variables. Do not put the
secret in Vercel, client-side environment variables, Apps Script source code,
or source control. The Apps Script deployment uses the `SPREADSHEET_ID`
property and rejects any spreadsheet ID supplied by the caller.

## Request and response contract

Django builds each row from the authoritative database via
`sheet_sync_data()`. A request has this shape:

```json
{
  "secret": "<shared secret>",
  "tickets": [
    {
      "sheet_name": "Online_Tickets",
      "row": {
        "ticket_id": "<ticket UUID>",
        "registration_id": "<registration UUID>"
      }
    }
  ]
}
```

The example omits the other row keys for brevity. The actual `row` includes
every column in the established `SHEET_HEADERS` order. Only `Online_Tickets`
and `OnSpot_Tickets` are accepted. Payment status must be `VERIFIED` or
`CAPTURED`, and ticket status must be `ISSUED`, `USED`, or `CANCELLED`.
Payment proofs and QR tokens are not part of the row.

Successful response:

```json
{
  "success": true,
  "processed_ticket_ids": ["<ticket UUID>"],
  "error_code": "",
  "retryable": false
}
```

Failures contain `success: false`, any IDs already processed, a non-sensitive
`error_code`, and a `retryable` boolean. Django marks jobs synced only when the
response confirms all requested UUIDs. The script holds a `LockService` script
lock across header validation and UUID lookup/upsert. It accepts either the
current 29-column schema or the known legacy 24-column schema. On legacy tabs,
the existing headers and order are preserved; fields absent from that older
schema (`booking_quantity`, `ticket_quantity`, `unit_price`,
`provider_order_id`, and `provider_payment_id`) are not written. Other
nonmatching headers are rejected and are not migrated or cleared.
Formula-leading strings are escaped before writing.

## Delivery and recovery

Approval commits payment, ticket issuance, and outbox rows before the Apps
Script call runs. The backend retries transient HTTP/write failures up to
three times with bounded delays and records the outcome on the existing
`TicketSheetSync` rows. Apps Script failure never undoes an approval.

There is no continuous retry service. If the web process exits before its
post-commit callback, or all retries fail, an administrator can select the
eligible pending/failed rows under Django admin → Payments → Ticket sheet
syncs and run the dispatch action. The existing management command
`process_ticket_sheet_syncs` remains a manual recovery route using the direct
Google Sheets API credentials; no Render cron is required by this webhook
implementation.

## Validation

The Apps Script contract tests use Node's built-in test runner and mocked
Spreadsheet/Lock/Properties services:

```powershell
node --test integrations/google-apps-script/Code.test.js
```

They do not access a real spreadsheet. Production synchronization is not
verified until a controlled approved ticket is observed in the deployed
spreadsheet.
