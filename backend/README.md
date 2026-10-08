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
6. Run `python manage.py seed_dhandiya_event`.
7. Create an administrator with `python manage.py createsuperuser`.
8. Start with `python manage.py runserver`.

The seed command creates the canonical event and its two ticket offers only.
It does not create attendee data, tickets, scans, staff users, or credentials.
Do not use the SQLite development fallback in production.

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
runs migrations before deploy, and starts Gunicorn. The worker runs
`python manage.py process_ticket_emails --loop` against the same database.
Do not run the email command as a Vercel Cron job.

Create a Neon PostgreSQL database and set `DATABASE_URL` on the Render web
service to its TLS-enabled direct connection string. Keep the connection
string in Render's environment, not in source control. Render's worker reuses
that setting from the web service. Use separate Neon databases/branches,
Razorpay test credentials, and Brevo settings for staging and production.

Deploy `client/` as the Vercel project root. Set the build-time
`VITE_API_BASE_URL` to `https://<render-service-host>/api/v1`; it is a public
API URL, not a secret. On Render, set `CORS_ALLOWED_ORIGINS` and
`CSRF_TRUSTED_ORIGINS` to the exact HTTPS Vercel origin, including the
production Vercel hostname. Set the same-site cookie flags to secure and
`SameSite=None` as shown in the Blueprint so credentialed API and CSRF
requests can cross origins. Browser privacy settings that block third-party
cookies can prevent session-based staff/admin use across separate Vercel and
Render sites; verify sign-in in the browsers used by event staff.

Set `BREVO_API_KEY` only in Render's environment, and rotate any key that was
previously exposed. Configure `BREVO_SENDER_EMAIL` as
`sims.dhandiyanight@gmail.com`, plus `BREVO_SENDER_NAME`. Configure Razorpay
with test keys for staging. The worker sends one email per ticket, reuses the
stored PDF on retries, reserves 295 regular and 5 staff/complimentary sends per
local calendar day, and retains ambiguous outcomes for manual reconciliation.
No live Brevo send has been validated by the test suite.

Never commit `.env` files. The root `.env.example` contains names and
non-secret development defaults only.
