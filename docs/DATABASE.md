# DATABASE.md

## 1. Purpose

This document defines the database architecture, data model, constraints, relationships, migration rules, and database conventions for the Event Ticketing & Registration Platform.

The database must preserve the most important business invariants of the system, especially:

- Every successful registration/order contains one or more tickets according to its selected offer.
- A registration/order may contain one or more independently valid tickets.
- Every ticket belongs to an event.
- A ticket has one authoritative status.
- A successfully admitted ticket cannot be admitted again.
- Multiple scanners must be able to operate concurrently.
- Registration source must distinguish online and on-spot registrations.
- Event and ticket data must remain isolated.
- Database constraints must protect against invalid application behavior.

---

# 2. Database Technology

## Database

PostgreSQL

## Backend ORM

Django ORM

## Backend Framework

Django + Django REST Framework

The application should access PostgreSQL primarily through Django's ORM.

Raw SQL should only be used when there is a clear technical requirement.

---

# 3. Environments

The project must maintain separate database configurations for:

```text
Development
Testing
Production
```

Development and testing databases must never use production data unless explicitly authorized and appropriately sanitized.

Production credentials must never be committed to the repository.

---

# 4. Database Configuration
Database connection information must come from environment variables.

Example:

```text
DATABASE_URL=postgresql://...
```

or equivalent Django database configuration variables.

Never hardcode:

- Database passwords
- Production usernames
- Connection strings
- API credentials
- Cloud database secrets

in source code or documentation.

---

# 5. Core Entities
The primary entities are:

```text
User
Event
TicketTier
PaymentIntent
Payment
Registration
RegistrationIdempotency
Ticket
TicketScan
TicketDelivery
AuditLog
```

The exact implementation may evolve, but new entities should represent genuine business requirements.

---

# 6. Entity Responsibilities

## User
Represents authenticated users such as:

- Administrators
- Registration staff
- Scanner staff

A user may have one or more permissions/roles depending on the authorization design.

---

## Event
Represents an event for which attendees can register and enter.

Typical information:

```text
id
name
description
venue
start_datetime
end_datetime
registration_open
registration_close
status
created_at
updated_at
```

The exact fields should follow the implemented requirements.

The canonical Dhandiya Night 2026 production event uses UUID `8b3f7a20-6e8d-4b91-a462-9c5d2f1e7043` and slug `dhandiya-night-2026`. Do not use the frontend demo ID `evt-technova-2026` as its production primary key. Render runs the idempotent event seed command after schema migrations so ticket registration and staff operations have the canonical event and approved ticket offers. Seed data must not include mock attendees, tickets, scans, or staff users.

---

## TicketTier
Represents an event's configured ticket offer, including its name, price, and currency. The Dhandiya Night offers are a single admission and a six-admission combo.

Typical offer information:

```text
event
name
price
currency
admission_count
availability
```

For Dhandiya Night, the registration page shows INR 149 for one admission and INR 745 for a six-admission combo. PayU requests add a fixed ₹4 per admission (₹153 and ₹769 total, respectively); this charge is included in the persisted payment amount in minor currency units and is not shown on the registration page. `admission_count` describes the admissions issued for one selected offer; capacity is reserved while a payment transaction is pending and consumed for each resulting ticket.

---

## Registration
Represents one buyer's registration/order for an event and selected ticket offer.

Typical information:

```text
id
registration_code
event
buyer_name
buyer_email
buyer_phone
registration_source
ticket_tier
created_at
updated_at
```

Buyer/contact information belongs to the registration and must not be redundantly copied onto every ticket. Each ticket stores its own required attendee name; for a combo, four attendee names are required, with the first name also serving as the buyer name. Buyer email and phone remain stored once on the registration.
Each ticket has a unique human-facing `ticket_code`, composed of its
registration code plus an admission suffix (for example,
`SIMS-DN-2026-00008-T01`). Tickets in the same booking share the registration
code but each have their own ticket code and QR token.

Registration source must distinguish:

```text
ONLINE
ON_SPOT
```

Both registration types must use the same registration/ticket architecture.
`id` remains the internal UUID used by foreign keys and API routes.
`registration_code` is the human-facing, unique sequential reference formatted
as `SIMS-DN-YYYY-NNNNN`. The year comes from the event start date and the
sequence is shared by registrations created in that year. `RegistrationSequence`
stores the next number and is incremented atomically with registration creation.

## RegistrationIdempotency
Stores one idempotency key and normalized request fingerprint for a registration operation, with a one-to-one link to the resulting registration. The UUID key is the primary key, so the database arbitrates concurrent duplicate submissions. The key record, registration, tickets, and registration audit record are committed atomically; a failed transaction leaves no incomplete key record or partial ticket set.

The registration model does not impose uniqueness on buyer email or phone. A different idempotency key represents a separate attempt, even when contact details match.

---

## PaymentIntent
Stores an idempotent online registration/payment attempt, normalized request fingerprint, buyer and attendee details, pending capacity reservation, and an optional link to the verified registration. The UUID idempotency key is the primary key. A captured payment whose ticket issuance needs investigation moves the intent to `REVIEW_REQUIRED`.

## Payment
Stores each payment-provider transaction, amount, currency, lifecycle status, verification status, capture time, ticket-issuance status, expiry, and failure/verification metadata. Provider transaction and payment IDs are unique. The provider field distinguishes PayU payments from retained historical Razorpay records; the migration renames provider ID columns in place without dropping existing values. A conditional database uniqueness constraint permits at most one verified captured payment per payment intent. Captured payments whose tickets were not issued or whose registration is incomplete are retained and reported for administrator review; the application has no refund or settlement-reversal operation.

## TicketDelivery
Stores retryable email/PDF delivery state for a registration, including recipient, attempt count, last error, and sent time. It is one-to-one with the registration and does not control ticket validity.

---

## Ticket
Represents one independently scannable admission credential within a registration/order.

Typical information:

```text
id
registration
token
status
issued_at
cancelled_at
used_at
created_at
updated_at
```

Each ticket has its own unique opaque QR token, status, and scan history. Ticket status must not be used as the order's payment status.

Ticket status:

```text
ISSUED
USED
CANCELLED
```

The ticket token must be unique.

---

## TicketScan
Represents an attempt to scan a ticket.

Typical information:

```text
id
ticket
event
scanned_by
result
scanned_at
device_identifier
```

The exact fields may vary depending on operational requirements.

A scan record should provide enough information to understand what happened during ticket validation.

---

## AuditLog
Records important administrative and operational actions.

Examples:

```text
Registration created
Ticket cancelled
Ticket scanned
User role changed
Event created
Event updated
```

Audit logging should not be treated as a replacement for application logs.

---

# 7. Relationships
The primary relationship structure is:

```text
Event
  ├──< TicketTier
  ├──< PaymentIntent
  │       └──< Payment
  └──< Registration (order)
          ├── RegistrationIdempotency (optional 1:1)
          └──< Ticket
                  └──< TicketScan
          └── TicketDelivery (optional 1:1)
```

Conceptually:

```text
One Event
    ↓
Many TicketTiers and Registrations

One Registration/order
    ↓
One or more independent Tickets

One Ticket
    ↓
Many Scan Attempts
```

For the Dhandiya Night combo, one buyer/order contains six tickets, each scannable independently. A single-ticket offer contains one ticket. Do not use a one-to-one Registration–Ticket relationship.

---

# 8. Registration Source
Every registration must identify how it was created.

Allowed values:

```text
ONLINE
ON_SPOT
```

Do not create separate ticket tables for online and on-spot registrations.

Both should use the same ticket model.

Example:

```text
Registration
├── id
├── event_id
├── attendee information
└── registration_source
        ├── ONLINE
        └── ON_SPOT
```

This allows reporting such as:

```text
Total registrations
Online registrations
On-spot registrations
```

without duplicating the ticket system.

---

# 9. Ticket Status
Ticket status should be represented using controlled values.

```text
ISSUED
USED
CANCELLED
```

Meaning:

### ISSUED
Ticket has been generated and is currently eligible for entry if all event rules are satisfied.

### USED
Ticket has already successfully completed entry.

### CANCELLED
Ticket has been invalidated and must not grant entry.

The client must never be allowed to arbitrarily update the ticket status.

---

# 10. Ticket Token
The QR code should represent an opaque ticket token.

The token must be:

- Unique
- Non-guessable
- Generated securely
- Stored in the database
- Suitable for lookup
- Not based on predictable sequential IDs

Example concept:

```text
QR Code
    ↓
Opaque Token
    ↓
Backend
    ↓
Ticket lookup
```

Do not use a simple sequential database ID as the only QR credential.

---

# 11. Unique Constraints
Database constraints are essential for protecting business invariants.

At minimum:

```text
Ticket.token → UNIQUE
```

Do not constrain a registration to exactly one ticket. Do not add unique constraints on buyer/attendee email or phone; the duplicate-registration policy permits repeated contact details.

---

# 12. Duplicate Entry Protection
The system must guarantee:

> A ticket can have at most one successful entry.

This must not depend only on frontend logic.

The backend should use a transaction and row-level locking when consuming a ticket.

Conceptually:

```text
BEGIN
    ↓
SELECT ticket FOR UPDATE
    ↓
Check ticket status
    ↓
If ISSUED:
    create successful scan/entry
    change ticket to USED
    ↓
COMMIT
```

If two scanners scan the same ticket at approximately the same time:

```text
Scanner A ──┐
            ├── Backend transaction
Scanner B ──┘
```

only one request should be able to successfully consume the ticket.

The other request must receive an appropriate result such as:

```text
ALREADY_USED
```

---

# 13. Database Transactions
Use transactions for operations where multiple database changes must succeed or fail together.

Examples:

### Ticket entry

```text
Lock ticket
↓
Validate
↓
Create successful scan
↓
Mark ticket USED
↓
Commit
```

If an operation fails, the transaction should roll back appropriately.

Do not allow a situation where:

```text
Ticket = USED
```

but no successful entry/scan record exists when the business model requires both operations to succeed together.

---

# 14. Row-Level Locking
For concurrent ticket scanning, the ticket row must be locked during the critical operation.

Django concept:

```python
Ticket.objects.select_for_update().get(...)
```

The exact implementation belongs in the backend service/transaction layer.

Do not perform:

```text
SELECT ticket
↓
check status
↓
later UPDATE ticket
```

without transaction protection for the ticket-consumption operation.

---

# 15. Indexes
Indexes should be created for fields frequently used in:

- Ticket lookup
- Event filtering
- Registration lookup
- Scan history
- Administrative dashboards

Likely candidates include:

```text
Ticket.token
Registration.event_id
Registration.email
Ticket.registration_id
TicketScan.ticket_id
TicketScan.scanned_at
```

Indexes should be added based on actual query patterns rather than blindly indexing every column.

---

# 16. Foreign Keys
Use database relationships to preserve referential integrity.

Examples:

```text
Registration.event → Event
Registration.ticket_tier → TicketTier
Ticket.registration → Registration
TicketScan.ticket → Ticket
TicketScan.event → Event
TicketScan.scanned_by → User
```

Use appropriate Django `on_delete` behavior for each relationship.

Do not select `CASCADE` automatically without considering the business impact.

For operational/audit data, accidental deletion may be unacceptable.

---

# 17. Event Isolation
Every ticket belongs to an event through its registration.

When validating a ticket for an event, the backend must verify that the ticket belongs to the event being scanned.

Example:

```text
Scanner at Event A
        ↓
Ticket belongs to Event A
        ↓
Continue validation
```

If:

```text
Scanner at Event A
        ↓
Ticket belongs to Event B
```

the ticket must not grant entry.

Database relationships should make this association explicit.

---

# 18. Cancelled Tickets
A cancelled ticket must never grant entry.

The backend must check ticket status before creating a successful entry.

Expected behavior:

```text
ISSUED
→ entry may be granted

USED
→ entry rejected; state remains USED

CANCELLED
→ entry rejected
```

The only allowed state transitions are `ISSUED -> USED` after a successful scan and `ISSUED -> CANCELLED` through authorized cancellation. `USED` and `CANCELLED` are terminal states. A cancellation affects only its ticket; it does not implicitly cancel sibling tickets in the same registration. Do not change a `USED` ticket to `CANCELLED` or back to `ISSUED`.

Do not rely on the QR code itself to communicate cancellation status.

The database remains authoritative.

---

# 19. Scan Records
Scan attempts should be recorded in a structured way.

Possible results:

```text
ENTRY_GRANTED
ALREADY_USED
INVALID_TICKET
CANCELLED
WRONG_EVENT
EVENT_CLOSED
UNAUTHORIZED
```

The exact enumeration may evolve with the API design.

A failed scan may still be useful for audit and operational analysis.

---

# 20. Successful Entry Invariant
The database design must support this invariant:

```text
One ticket
    ↓
0 or 1 successful entry
```

It must never become:

```text
One ticket
    ↓
2 successful entries
```

Database-level constraints and transaction logic should work together to enforce this.

If a separate `Entry` model is introduced, it should have an appropriate uniqueness constraint such as one successful entry per ticket.

---

# 21. Date and Time
Store event and operational timestamps consistently.

Use timezone-aware datetime handling.

Important timestamps may include:

```text
created_at
updated_at
issued_at
used_at
cancelled_at
scanned_at
```

Do not manually construct timestamps in inconsistent formats across different modules.

Use Django's timezone utilities and project configuration.

---

# 22. Soft Delete vs Hard Delete
Do not introduce soft deletion for every model automatically.

Use soft deletion only when there is a genuine business/audit requirement.

For example, deleting an event or ticket may have consequences for:

- Audit history
- Reports
- Entry records
- Compliance
- Historical data

Before implementing deletion, determine whether the entity should instead be:

```text
CANCELLED
ARCHIVED
INACTIVE
```

rather than physically deleted.

---

# 23. Migration Rules
All schema changes must use Django migrations.

Typical workflow:

```text
python manage.py makemigrations
python manage.py migrate
```

Migration files must be committed to version control.

Never manually modify the production schema without a controlled migration process.

---

# 24. Migration Best Practices
Before creating a migration:

1. Understand the existing schema.
2. Check existing migrations.
3. Consider existing production data.
4. Consider whether the migration is reversible.
5. Test the migration locally.
6. Run the application tests.
7. Review generated SQL for high-risk changes when appropriate.

Be especially careful with:

- Dropping columns
- Renaming columns
- Changing constraints
- Changing large tables
- Adding non-null fields to populated tables
- Removing indexes
- Data migrations

---

# 25. Data Migrations
Use Django data migrations when existing database data must be transformed as part of a schema change.

Do not write one-off scripts that silently modify production data without documentation or review.

For large datasets, consider migration performance and deployment impact.

---

# 26. Seed Data
Development seed data may be used for:

```text
Development users
Test events
Sample registrations
Sample tickets
```

Seed data must never contain real attendee information.

Development credentials must be clearly marked and must not be reused in production.

---

# 27. Production Data
Production data should be treated as sensitive.

Do not:

- Copy production data into development unnecessarily
- Commit production database dumps
- Share attendee data through source control
- Include real personal information in tests
- Log unnecessary personal information

Production database access should follow least-privilege principles.

---

# 28. Backups
Production database backups must be configured outside the application codebase.

Backups should be:

- Automated
- Protected
- Tested for restoration
- Stored separately from the primary database where appropriate

A backup that has never been successfully restored should not be assumed to be reliable.

---

# 29. Database Credentials
Never commit:

```text
DATABASE_URL
DB_PASSWORD
DB_USERNAME
Production credentials
Cloud database credentials
```

Use environment configuration.

Example:

```text
DATABASE_URL=<configured outside source control>
```

The `.env` file should be excluded from Git.

Provide:

```text
.env.example
```

when developers need to understand required configuration variables.

---

# 30. Database Security
Database access should be restricted.

Application users should receive only the permissions necessary for the application.

Do not expose PostgreSQL directly to the public internet unless the deployment architecture explicitly requires it and appropriate controls are implemented.

Use encrypted connections where required by the hosting environment.

---

# 31. Input Validation
Database safety must not depend on database errors alone.

Validate incoming data before persistence.

Examples:

```text
Email format
Phone format
Required attendee fields
Event ID
Registration source
Ticket token
User permissions
```

However, validation does not replace database constraints.

Use both:

```text
Application validation
        +
Database constraints
```

---

# 32. SQL Injection Protection
Never construct SQL using raw user input.

Bad:

```python
query = f"SELECT * FROM tickets WHERE token = '{token}'"
```

Prefer Django ORM:

```python
Ticket.objects.filter(token=token)
```

If raw SQL is genuinely required, use parameterized queries.

---

# 33. Query Performance
Avoid unnecessary database queries.

Watch for:

```text
N+1 queries
Repeated event lookups
Repeated user queries
Unnecessary full-table scans
Loading large datasets into memory
```

Use appropriate ORM techniques such as:

```python
select_related()
prefetch_related()
```

when justified by actual relationships and query patterns.

Do not optimize blindly.

Measure first when performance becomes a concern.

---

# 34. Pagination
Administrative lists should use pagination where datasets can become large.

Examples:

```text
Registrations
Tickets
Scan history
Audit logs
Users
Events
```

Do not return thousands of records in a single API response simply because the database can technically retrieve them.

---

# 35. Reporting Queries
Dashboard/reporting queries should avoid modifying operational data.

For example:

```text
Total registrations
Online registrations
On-spot registrations
Tickets issued
Tickets used
Tickets cancelled
Successful entries
Failed scans
```

should be generated from read/query operations.

Do not update ticket or registration state while generating a report.

---

# 36. Concurrency
The application must assume multiple users and scanners can operate at the same time.

Important concurrent operations include:

```text
Multiple ticket scans
Multiple on-spot registrations
Multiple staff users
Multiple admin actions
```

Database transactions and constraints must protect shared state.

Never assume:

```text
Only one scanner will scan at a time.
```

---

# 37. On-Spot Registration
On-spot registration must use the same core registration and ticket tables as online registration.

Example:

```text
Staff
  ↓
Create Registration
  ↓
registration_source = ON_SPOT
  ↓
Resolve selected offer and admission count
  ↓
Create one Ticket per admission, each with its own QR token
```

Do not create a separate database architecture for on-spot attendees unless a future requirement explicitly demands it.

---

# 38. Online Registration
Online registration follows:

```text
Attendee
  ↓
Registration Form
  ↓
Backend Validation
  ↓
Registration/order
  ↓
One Ticket per admission
  ↓
Unique opaque QR token per Ticket
```

The database should preserve the relationship between the attendee registration and generated ticket.

---

# 39. Ticket Cancellation
Cancellation is handled through controlled application logic. `ISSUED -> CANCELLED` is the only cancellation transition. `USED` tickets remain historically `USED`; they must never be reset to `ISSUED` or relabelled `CANCELLED`. A cancelled ticket is independently invalidated and does not cancel any other tickets in its registration/order. Whole-order and combo cancellation behavior for tickets containing used admissions remains unresolved; the application does not support or initiate refunds. See `docs/PRODUCT_DECISIONS.md`.

---

# 40. Auditability
Important state changes should be traceable.

For example:

```text
Who cancelled the ticket?
When was it cancelled?
Who scanned the ticket?
When was entry granted?
Who created an on-spot registration?
```

Use audit records where required.

Do not depend exclusively on mutable ticket fields to reconstruct historical events.

---

# 41. Data Retention
Data retention rules should be defined according to the event organizer's actual requirements.

Do not automatically delete:

```text
Registrations
Tickets
Successful entry records
Audit records
```

just because an event has ended.

Historical data may be required for reporting and auditing.

---

# 42. Database Testing
Database-related tests should verify both valid behavior and constraints.

Important tests include:

```text
Unique ticket token
Registration → ticket relationship
Ticket → event relationship
Cancelled ticket rejection
Used ticket rejection
Wrong-event rejection
Concurrent scan behavior
One successful entry per ticket
Migration correctness
```

Concurrency tests are especially important for ticket scanning.

---

# 43. Development Database Reset
A development database may be reset when necessary.

Never run destructive database reset commands against production.

Before executing commands such as:

```text
python manage.py flush
```

verify the active environment.

AI coding agents must not perform destructive database operations without explicit authorization.

---

# 44. AI Coding Agent Rules
AI agents must:

1. Read `DATABASE.md` before modifying database structure.
2. Inspect existing models before creating new ones.
3. Reuse existing relationships when possible.
4. Use Django migrations for schema changes.
5. Preserve existing constraints.
6. Never remove a constraint merely to make an operation succeed.
7. Never bypass transaction requirements for ticket scanning.
8. Never modify production data without explicit authorization.
9. Never hardcode database credentials.
10. Add tests for important database behavior.
11. Consider existing production data before destructive migrations.
12. Update this document when stable database conventions change.

---

# 45. Database Change Checklist
Before submitting a database-related change:

```text
[ ] Existing models inspected
[ ] Existing relationships inspected
[ ] Existing migrations inspected
[ ] New model justified
[ ] Naming conventions followed
[ ] Foreign keys reviewed
[ ] Unique constraints reviewed
[ ] Indexes considered
[ ] Transaction requirements considered
[ ] Migration generated
[ ] Migration tested
[ ] Existing data considered
[ ] Tests added/updated
[ ] Security implications reviewed
[ ] Documentation updated if required
```

---

# 46. Core Database Invariants
The following invariants are critical:

```text
1. Every ticket belongs to a registration.

2. Every registration belongs to an event.

3. Every ticket has a unique token.

4. A cancelled ticket cannot grant entry.

5. A used ticket cannot grant entry again.

6. A ticket can have at most one successful entry.

7. A ticket must belong to the event being scanned.

8. Online and on-spot registrations use the same ticket system.

9. Ticket consumption must be transaction-safe.

10. Database constraints must protect critical business rules.
```

---

# 47. Final Principle
The database is not merely a place to store application data.

It is one of the final layers protecting the integrity of the ticketing system.

Application validation can fail.

Frontend code can be manipulated.

Requests can be duplicated.

Multiple scanners can operate simultaneously.

Therefore:

```text
Frontend
    ↓
Backend Validation
    ↓
Business Logic
    ↓
Database Transaction
    ↓
Database Constraints
```

Critical ticketing rules must remain correct even when requests arrive concurrently or when the client behaves incorrectly.

---

# 48. Ticket Email Queue and Quota

`TicketDelivery` has a one-to-one relationship with `Ticket`; this ensures a
combo registration produces an independent email and PDF for each attendee.
The migration converts historical registration-level delivery rows to
ticket-level rows and preserves sent states.

`EmailDailyUsage` is keyed by local calendar date. Its database check
constraints cap regular reservations at 295 and staff/complimentary
reservations at 5. Workers lock the daily usage row before claiming a pending
delivery and increment the corresponding reservation in the same transaction.
Provider acceptance increments the sent count; definite rejection releases
the reservation. Daily reservations cannot be borrowed across priority classes.

A timeout or provider 5xx may mean Brevo accepted the message even though the
application did not receive confirmation. Such deliveries intentionally keep
their reservation and `SENDING` state until reconciled, preventing an automatic
retry from creating duplicate emails.
