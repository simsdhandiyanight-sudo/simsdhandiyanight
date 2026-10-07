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

The Vite development server should proxy `/api` requests to Django so the
browser uses same-origin session cookies and CSRF protection.
