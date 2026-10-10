# Ticketing backend

## Development setup

1. Install Python 3.12 and PostgreSQL.
2. Install dependencies: `python -m pip install -r requirements.txt`
3. Copy the repository `.env.example` to `.env` and configure local values.
4. For a local PostgreSQL database, set `DATABASE_NAME`, `DATABASE_USER`,
   `DATABASE_PASSWORD`, `DATABASE_HOST`, and `DATABASE_PORT`. If
   `DATABASE_NAME` is unset, Django uses a local SQLite database for development
   and tests only.
5. Run `python manage.py migrate`.
6. Run `python manage.py seed_dhandiya_event` to enable backend event APIs,
   ticket registration, payments, and staff operations.
7. Create an administrator with `python manage.py createsuperuser`.
8. Start with `python manage.py runserver`.

The seed command creates the canonical event and its two ticket offers only.
It does not create attendee data, tickets, scans, staff users, or credentials.
Do not use the SQLite development fallback in production.
The public landing and event detail pages display hardcoded event information
without requiring this seed, but online registration and staff operations
remain unavailable until the backend event and ticket offers are created.

### Initial Render administrator

The Render startup command runs `bootstrap_admin` after migrations and event
seeding. Set `BOOTSTRAP_ADMIN_PASSWORD` as a secret in the Render web service
environment before deploying. The configured `BOOTSTRAP_ADMIN_EMAIL` defaults
to `admin@sims.in`. On first startup, the command creates that administrator;
it never changes the password of an existing administrator and refuses to
promote an existing non-admin account. Once Render confirms the first
successful deployment, remove `BOOTSTRAP_ADMIN_PASSWORD` from the service
environment and redeploy to disable future bootstrapping. Do not put the
password in source control or logs.

If the administrator already exists and needs a password reset, set
`BOOTSTRAP_ADMIN_PASSWORD` to the new secret and temporarily set
`BOOTSTRAP_ADMIN_RESET_PASSWORD` to `true` in Render. After confirming the
deployment log reports an updated administrator password, immediately remove
the password secret and reset flag, then redeploy. The flag only resets the
password for the configured email when that account is already an administrator.

## Staff accounts and panel access

Create staff accounts individually in Django admin at `/admin/` using an
administrator account. Create four users with the `Scanner staff` role and
four with the `Registration staff` role. Give each person a unique email and
password; leave `is_staff` and `is_superuser` disabled for these accounts so
they cannot sign in to Django admin. Scanner accounts may be assigned to a gate
through the Staff assignments section.

Scanner staff sign in at `/staff/login` and are routed to the scanner panel.
Registration staff use the same sign-in page and are routed to the on-spot
registration panel. Each role is restricted to its own panel and API operations;
neither staff role can access the admin panel. These accounts are not generated
by the event seed command.

For local frontend development, copy `client/.env.example` to
`client/.env.local` and set `VITE_API_URL` to the local Django API origin. The
Vite development server proxies `/api` requests to that configured origin; it
does not embed a localhost fallback in the application bundle.

## Render, Neon, Vercel, and Brevo deployment

The repository-root `render.yaml` defines a Django web service and a separate
Render Background Worker. In Render, create the services from that Blueprint.
The web service installs the backend requirements, collects static files,
runs database schema migrations and idempotently seeds the canonical event and
ticket tiers at startup, then starts Gunicorn. The worker runs
`python manage.py process_ticket_emails --loop` against the same database. Do
not run the email command as a Vercel Cron job.

Create a Neon PostgreSQL database and set `DATABASE_URL` on the Render web
service to its TLS-enabled direct connection string. Keep the connection
string in Render's environment, not in source control. Render's worker reuses
that setting from the web service. Use separate Neon databases/branches, PayU test credentials, and Brevo
settings for staging and production.

Deploy `client/` as the Vercel project root. Set the build-time
`VITE_API_BASE_URL` to `https://<render-service-host>/api/v1`; it is a public
API URL, not a secret. On Render, set `CORS_ALLOWED_ORIGINS` and
`CSRF_TRUSTED_ORIGINS` to the exact HTTPS Vercel origin, including the
production Vercel hostname. Production Django settings enforce secure cookies
with `SameSite=None` so credentialed API and CSRF requests can cross origins.
Browser privacy settings that block third-party
cookies can prevent session-based staff/admin use across separate Vercel and
Render sites; verify sign-in in the browsers used by event staff.

Set `BREVO_API_KEY` only in Render's environment, and rotate any key that was
previously exposed. Configure `BREVO_SENDER_EMAIL` as
`sims.dhandiyanight@gmail.com`, plus `BREVO_SENDER_NAME`. Configure the PayU
merchant key and salt as backend-only secrets; use `PAYU_ENVIRONMENT=test` for
staging and register the callback/webhook URLs with PayU. Production mode must
use separate production credentials after merchant activation and sandbox
validation. `PAYU_FRONTEND_URL` is the browser return origin. The worker sends
one email per ticket, reuses the
stored PDF on retries, reserves 295 regular and 5 staff/complimentary sends per
local calendar day, and retains ambiguous outcomes for manual reconciliation.
No live Brevo send has been validated by the test suite.

Payment screenshots are uploaded by the backend using the official Cloudinary
SDK. Set `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and
`CLOUDINARY_API_SECRET` as secrets on the Render web service; never set these
in the frontend. Proofs are uploaded as `authenticated` image assets under
`college-ticketing/payment-proofs`, not public assets. PostgreSQL stores the
Cloudinary asset identifiers and image metadata. The admin-only screenshot
endpoint proxies Cloudinary's signed authenticated delivery server-side; it
does not send Cloudinary URLs or credentials to the browser. New proof images
are not stored as database binary data.

On startup, `migrate_legacy_payment_proofs` transfers pre-existing binary
proofs to Cloudinary and clears their database binary values. Configure the
Cloudinary credentials before deploying this change if existing manual proof
records need to be retained. The daily Render cleanup cron deletes only
unreferenced authenticated assets at least seven days old. Referenced proofs,
including rejected submissions, are retained for reconciliation and disputes;
apply an explicit retention policy before deleting them.

Online registration uses manual UPI payment proof. The payment QR image is
served by the frontend from `client/public/upi-payment-qr.jpeg`; no UPI ID or
QR URL environment variables are required. Replace that frontend image when
the payment QR changes. Set `PAYMENT_PROOF_RESERVATION_HOURS` (default 24) and
`PAYMENT_PROOF_RESUBMISSION_HOURS` (default 12) to the reservation windows.
Uploaded JPEG/PNG/WebP proof images are capped at 5 MB and stored in the
private Cloudinary assets (not in PostgreSQL or the ephemeral Render
filesystem); only administrators can retrieve them through the authorized
backend proxy. The approval dashboard requires an
administrator to confirm the actual received UTR/amount against bank/UPI
records before approval. The Render expiry cron releases unpaid/rejected
reservations every five minutes.
Applicants submit both the UTR and transaction ID as separate required
references; each is checked against prior manual UPI submissions.

Final tickets use the existing Brevo delivery worker. A verified payment stays
verified if email delivery fails; admins can retry failed ticket delivery from
the Email Delivery panel without generating new tickets or QR codes. Configure
`BREVO_API_KEY` and the verified sender settings before production.

Schedule `python manage.py reconcile_payu_payments` on the backend every
minute or every few minutes to retry due PayU verifications. Each run is a
bounded pass; automatic verification uses at most five attempts per payment
with exponential backoff and honors a PayU `Retry-After` header. Captured
payments needing review are not automatically ticketed. An administrator can
retry verification or resume verified ticket issuance from the Payment Review
page. Do not rerun a checkout or charge the customer again to reconcile a
pending transaction.

Never commit `.env` files. The root `.env.example` contains names and
non-secret development defaults only.
