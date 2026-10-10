# SECURITY.md

# Event Ticketing & Registration Platform
## Security Rules

This document defines the security requirements for the Event Ticketing & Registration Platform.

All developers and AI coding agents must follow these rules.

Security decisions must prioritize:

1. Correct authorization
2. Ticket integrity
3. Data protection
4. Duplicate-entry prevention
5. Safe failure behavior
6. Auditability

---

# 1. Security Principles

The system follows these core principles:

- Never trust client input.
- Enforce authorization on the server.
- Keep secrets out of source code.
- Keep sensitive operations server-side.
- Use database constraints for critical invariants.
- Use transactions for security-sensitive state changes.
- Fail safely.
- Do not expose internal implementation details.
- Collect only the data required by the product.

---

# 2. Trust Boundary

The frontend must be treated as untrusted.

```text
Browser
   |
   | UNTRUSTED INPUT
   ▼
Django API
   |
   | VALIDATED BUSINESS LOGIC
   ▼
PostgreSQL
```

Anything sent by:

- browser,
- scanner device,
- registration form,
- query parameter,
- URL parameter,
- API client,

must be treated as potentially malicious or incorrect.

The server must validate it.

---

# 3. Authentication
Protected operations require authentication.

Protected operations include:

- Admin operations
- Staff operations
- On-spot registration
- Ticket search
- Ticket management
- QR scanning
- Scan history
- Staff management
- Event management

Public online registration may be unauthenticated where required by the product.

---

# 4. Authorization
Authentication answers:

```
Who is this user?
```

Authorization answers:

```
What is this user allowed to do?
```

Both must be enforced.

The backend must determine the authenticated user's role and permissions.

Never trust role information supplied by the frontend.

Unsafe:

```
{
  "role": "ADMIN"
}
```

if the backend simply accepts that value.

---

# 5. Roles
The system uses three primary roles:

```
ADMIN
REGISTRATION_STAFF
SCANNER_STAFF
```

## ADMIN
Can:

- Manage events
- View registrations
- Manage tickets
- Cancel tickets
- Manage staff
- View reports
- View scan history
- Perform administrative operations

---

## REGISTRATION_STAFF
Can:

- Create on-spot registrations
- View permitted registrations
- Search permitted tickets
- Generate/display tickets

Cannot:

- Manage staff
- Change security configuration
- Bypass ticket validation
- Grant gate entry manually

---

## SCANNER_STAFF
Can:

- Access scanner
- Validate tickets
- View permitted scan results
- View limited recent scans

Cannot:

- Create tickets
- Cancel tickets
- Modify attendee information
- Change event configuration
- Mark tickets as used manually

---

# 6. Server-Side Authorization
Every protected API endpoint must perform authorization checks.

Example:

```
Request
   ↓
Authenticate
   ↓
Identify User
   ↓
Check Permission
   ↓
Perform Operation
```

If authentication fails:

```
401 Unauthorized
```

If authentication succeeds but authorization fails:

```
403 Forbidden
```

Do not rely on hiding buttons in React as an authorization mechanism.

The UI may hide unauthorized actions for usability, but the backend must still enforce the restriction.

---

# 7. Secrets and Environment Variables
Never hardcode:

- Database passwords
- API keys
- Authentication secrets
- Signing keys
- Third-party credentials
- Production passwords

Use environment variables.

Example:

```
DATABASE_URL=
SECRET_KEY=
ALLOWED_HOSTS=
CORS_ALLOWED_ORIGINS=
```

Never commit:

```
.env
```

to source control.

Maintain:

```
.env.example
```

containing variable names only.

---

# 8. Environment Separation
Development, staging, and production must use separate credentials and configuration.

```
Development
     ↓
Development Database
     ↓
Development Secrets
```

```
Production
     ↓
Production Database
     ↓
Production Secrets
```

Never use production credentials during local development unless explicitly required and securely configured.

---

# 9. QR Code Security
The QR code should contain an opaque, non-guessable ticket token.

Example:

```
QR
 ↓
opaque-random-token
```

Do not encode unnecessary sensitive information such as:

- passwords,
- authentication tokens,
- database IDs where avoidable,
- internal permissions,
- unnecessary personal information.

The QR code should identify the ticket, not expose private data.

---

# 10. QR Token Requirements
QR tokens should be:

- Unique
- Non-guessable
- Sufficiently random
- Stored securely
- Validated server-side

Do not generate tokens using predictable values such as:

```
TKT-001
TKT-002
TKT-003
```

A human-readable ticket number may be sequential, but the QR validation token should not be predictable.

---

# 11. Ticket Validation Security
The backend must be the authority for ticket validation.

The server must verify:

1. Scanner authentication
2. Scanner authorization
3. Event validity
4. Ticket existence
5. Ticket/event relationship
6. Ticket status
7. Entry state
8. Database transaction
9. Successful entry recording

The frontend must never determine final validity.

---

# 12. Duplicate Entry Prevention
Duplicate entry prevention is a security-critical requirement.

The system must guarantee:

```
One Ticket
     ↓
Maximum One Successful Entry
```

Consider:

```
Scanner A ──┐
            ├──> Same Ticket
Scanner B ──┘
```

Both requests may arrive simultaneously.

The system must never allow:

```
Scanner A → ENTRY_GRANTED
Scanner B → ENTRY_GRANTED
```

for the same ticket.

One request may succeed.

The other must be rejected.

---

# 13. Transaction-Safe Entry Validation
The preferred conceptual operation is:

```
BEGIN TRANSACTION

Lock Ticket

Check Event

Check Ticket Status

IF cancelled:
    reject

IF already used:
    reject

Create successful entry

Mark Ticket USED

COMMIT
```

Use Django transaction handling and PostgreSQL row-level locking.

The ticket status must be re-checked after obtaining the database lock.

Do not trust a status value retrieved before the lock.

---

# 14. Database Constraints
Application-level validation is not enough for critical invariants.

Use database constraints where appropriate.

Important constraints include:

```
ticket_number → UNIQUE

qr_token → UNIQUE

successful_entry.ticket_id → UNIQUE
```

These constraints provide an additional layer of protection against programming errors and race conditions.

---

# 15. Race Conditions
Do not implement ticket validation as:

```
SELECT ticket

IF ticket.status == UNUSED:
    UPDATE ticket SET status = USED
```

without transaction/locking protection.

Two requests can otherwise perform:

```
Request A → sees UNUSED
Request B → sees UNUSED

Request A → marks USED
Request B → marks USED
```

Both could incorrectly receive success.

The database transaction must prevent this.

---

# 16. Idempotency and Retries
Network problems can cause clients to retry requests.

The implementation must consider repeated scan requests.

For ticket entry, the system must preserve the invariant:

```
Repeated request
      ↓
Must not create another successful entry
```

If a ticket has already been successfully used, subsequent requests must not grant another entry.

---

# 17. On-Spot Registration Security
On-spot registration must require an authorized staff account.

The server must determine:

```
Authenticated User
        ↓
Registration Staff?
        ↓
Allowed
```

A normal public user must not be able to call the staff-only on-spot registration endpoint simply by knowing its URL.

---

# 18. Online Registration Security
Public registration endpoints are exposed to potentially untrusted users.

Validate:

- Required fields
- Data types
- String lengths
- Email format where applicable
- Phone format where applicable
- Event ID
- Event availability
- Registration limits
- Unexpected fields

Never trust frontend validation alone.

---

# 19. Input Validation
All user-controlled input must be validated server-side.

This includes:

- Names
- Email addresses
- Phone numbers
- Event IDs
- Ticket IDs
- QR tokens
- Search parameters
- Pagination
- Filters
- Gate identifiers
- Registration fields

The backend should reject unexpected or invalid data where appropriate.

---

# 20. SQL Injection Protection
Use Django ORM or properly parameterized database queries.

Do not construct SQL by concatenating user input.

Unsafe concept:

```
query = "SELECT * FROM tickets WHERE token = '" + token + "'"
```

Use Django ORM or parameterized queries instead.

---

# 21. API Security
Protected APIs must:

- Authenticate users.
- Authorize operations.
- Validate inputs.
- Use HTTPS in production.
- Return safe errors.
- Avoid exposing internal exceptions.
- Apply rate limiting where appropriate.

---

# 22. Public API Abuse
Public registration endpoints may be abused through:

- Automated requests
- Spam registrations
- Request flooding
- Duplicate submissions
- Enumeration attempts

Use appropriate controls such as:

- Rate limiting
- Registration limits
- Input validation
- Bot protection where justified
- Request throttling

Do not add unnecessary security mechanisms that negatively affect legitimate attendees.

---

# 23. Rate Limiting
Rate limiting should be considered for:

```
Authentication
Public Registration
Ticket Search
Ticket Scanning
Expensive Dashboard Queries
```

Scanner rate limits must account for legitimate event traffic.

A rate limit must not prevent four legitimate gates from operating simultaneously.

---

# 24. Ticket Enumeration Protection
Ticket numbers may be human-readable.

However, public users must not be able to enumerate all tickets simply by changing:

```
TKT-000001
TKT-000002
TKT-000003
```

Administrative ticket search must require appropriate authorization.

QR validation should use the opaque QR token rather than relying solely on predictable ticket numbers.

---

# 25. Event Isolation
A ticket must only be valid for its associated event.

Example:

```
Ticket
   ↓
Event A
```

must not be accepted by:

```
Event B Scanner
```

The scan endpoint must verify the relationship between:

```
Requested Event
+
Ticket Event
```

before granting entry.

---

# 26. Cancelled Tickets
A cancelled ticket must never be accepted.

The backend must check ticket status during validation.

Example:

```
Ticket Status = CANCELLED
       ↓
ENTRY REJECTED
```

The frontend must not be able to change:

```
CANCELLED → USED
```

---

# 27. Ticket Status Integrity
Ticket status must only be changed through authorized server-side operations.

Do not allow clients to submit:

```
{
  "status": "USED"
}
```

and directly modify the ticket.

The backend must determine when a ticket becomes `USED`.

A ticket becomes used only as part of successful entry validation.

---

# 28. Error Handling
User-facing errors must not expose internal information.

Never expose:

- Stack traces
- SQL queries
- Database credentials
- API keys
- Internal filesystem paths
- Internal service configuration
- Authentication secrets

Bad:

```
IntegrityError:
duplicate key value violates unique constraint
database postgres://...
```

Better:

```
This ticket has already been used.
```

---

# 29. Error Response Security
API errors should use safe, consistent responses.

Example:

```
{
  "success": false,
  "error": {
    "code": "TICKET_ALREADY_USED",
    "message": "This ticket has already been used."
  }
}
```

Do not return raw Python/Django exceptions to the client.

---

# 30. Logging
Logs should help developers diagnose failures without exposing sensitive data.

Never log:

- Passwords
- Authentication tokens
- Authorization headers
- API keys
- Database passwords
- Unnecessary personal information

Avoid logging raw QR tokens unless there is a documented operational/security requirement.

Useful fields may include:

```
event_id
ticket_id
scanner_user_id
gate
result
timestamp
error_category
```

---

# 31. Audit Logging
Important security-sensitive actions should be auditable.

Examples:

```
Admin created event
Admin changed event
Admin cancelled ticket
Staff created on-spot registration
Scanner attempted ticket validation
Scanner successfully granted entry
Scanner attempted already-used ticket
Staff permissions changed
```

Audit records should contain enough information to investigate an incident.

Do not use audit logs as a substitute for enforcing security.

---

# 32. Personal Data Protection
Only collect information required for the event.

Potential attendee data may include:

- Name
- Email
- Phone
- Registration information

Do not collect unnecessary information merely because the database can store it.

Do not duplicate personal information across multiple tables unless there is a clear reason.

---

# 33. Data Access
Users should only be able to access data required for their role.

For example:

```
Scanner Staff
    ↓
Needs ticket validation
    ↓
Does NOT need full attendee database access
```

Similarly:

```
Registration Staff
    ↓
Needs registration information
    ↓
Does NOT need staff-management access
```

Use least-privilege access.

---

# 34. Authentication Tokens / Sessions
Authentication credentials must be handled securely according to the selected Django authentication mechanism.

Do not:

- expose server secrets to React,
- store sensitive credentials in URLs,
- log authentication headers,
- send secrets unnecessarily to the client.

The final authentication implementation must be documented once selected.

---

# 35. HTTPS
Production traffic must use HTTPS.

This includes:

```
Attendee → Frontend
Staff → Frontend
Scanner → API
Frontend → API
```

Do not transmit authentication credentials or ticket operations over unencrypted production HTTP.

---

# 36. CORS
CORS must be explicitly configured.

Do not allow unrestricted origins in production.

Avoid:

```
CORS_ALLOW_ALL_ORIGINS = True
```

unless there is a documented and justified requirement.

Production allowed origins should be explicitly configured.

---

# 37. CSRF
The authentication architecture must use the appropriate Django CSRF protections.

If cookie-based authentication is used, configure CSRF protection correctly.

Do not disable CSRF protection simply because an API request is inconvenient to implement.

---

# 38. File Upload Security
If future features allow users or staff to upload files:

- Validate file type.
- Validate file size.
- Do not trust the filename.
- Store uploads safely.
- Prevent executable uploads.
- Scan files where appropriate.
- Do not expose private files publicly without authorization.

This applies to any future ticket/document upload feature.

Payment proof images must be content-validated and size-limited server-side.
Store them as Cloudinary `authenticated` assets; a folder or unguessable URL is
not an access control. Deliver proofs only from an administrator-authorized
backend endpoint, proxying the signed Cloudinary request without exposing its
URL or credentials. Do not log signed delivery URLs or proof capability
headers.

---

# 39. QR Image Security
QR images themselves are not authentication credentials for administrative access.

The QR token only identifies the ticket for the intended validation workflow.

Do not reuse QR tokens as:

- Admin login tokens
- Staff authentication tokens
- Password-reset tokens
- Session tokens

---

# 40. Scanner Device Security
Scanner devices should:

- Use authenticated staff accounts.
- Use HTTPS.
- Avoid storing unnecessary ticket data locally.
- Avoid storing authentication credentials insecurely.
- Log out when the device is no longer authorized.
- Avoid exposing the admin dashboard to scanner staff.

If a scanner device is lost, its account/session should be revocable.

---

# 41. Session Security
Staff sessions should have appropriate:

- Expiration
- Logout
- Revocation
- Secure cookie settings where applicable
- Session protection

The exact implementation depends on the authentication strategy.

---

# 42. Production Configuration
Before production deployment verify:

```
DEBUG = False

HTTPS enabled

Production secrets configured

Database credentials secure

Allowed hosts configured

CORS configured

CSRF configured

Authentication enabled

Authorization enabled

Rate limiting configured where required

Database backups configured

Logging configured
```

---

# 43. Database Backups
Production database backups must be configured according to the selected hosting/deployment environment.

Backups should be tested periodically.

A backup that has never been restored is not considered fully verified.

---

# 44. Destructive Operations
Destructive operations require appropriate authorization.

Examples:

- Event deletion
- Ticket cancellation
- Data deletion
- Staff removal

Do not expose destructive operations to scanner staff.

Where appropriate, use soft deletion or status changes instead of permanently deleting operational records.

---

# 45. Audit Integrity
Do not allow normal users to delete or modify audit records.

Audit information should remain trustworthy.

If audit retention/deletion requirements are later introduced, they must be explicitly documented.

---

# 46. Security Testing
Before production release, test at minimum:

### Authentication

```
Unauthenticated user
→ Protected endpoint
→ 401
```

### Authorization

```
Scanner Staff
→ Admin endpoint
→ 403
```

### Ticket validation

```
Valid ticket
→ ENTRY_GRANTED
```

### Duplicate ticket

```
Used ticket
→ ALREADY_USED
```

### Concurrent ticket

```
Two simultaneous scans
→ Maximum one ENTRY_GRANTED
```

### Cancelled ticket

```
Cancelled ticket
→ REJECTED
```

### Wrong event

```
Event A ticket
→ Event B scanner
→ REJECTED
```

### Input validation

```
Invalid input
→ Request rejected
```

### Rate limiting
Verify abuse-prone public endpoints cannot be flooded without protection.

---

# 47. AI Coding Agent Security Rules
The AI coding agent must NEVER:

- Hardcode credentials.
- Invent production secrets.
- Disable authentication.
- Disable authorization.
- Disable CSRF protection merely to make requests work.
- Disable database constraints.
- Remove duplicate-entry protection.
- Trust client-provided roles.
- Trust client-provided ticket status.
- Expose stack traces.
- Log secrets.
- Mark tickets as used from the frontend.
- Bypass database transactions for convenience.
- Delete security tests because they fail.

If a requested change conflicts with this document, the conflict must be identified before implementation.

---

# 48. Security Decision Rule
When there is a conflict between:

```
Convenience
```

and:

```
Security / Data Integrity
```

the implementation must preserve security and data integrity.

For example:

```
"Make the scanner work without login"
```

must not result in disabling scanner authentication.

Instead, the requirement must be reviewed and an appropriate authenticated workflow designed.

---

# 49. Security Incident Principle
If suspicious activity is detected, the system should preserve enough information to investigate:

- User
- Event
- Ticket
- Gate
- Timestamp
- Operation
- Result

Do not hide failed or suspicious operations merely to make dashboards look clean.

---

# 50. Final Security Principle
The most important security invariant is:

```
UNTRUSTED CLIENT
       ↓
SERVER VALIDATION
       ↓
AUTHORIZED OPERATION
       ↓
TRANSACTION
       ↓
DATABASE INTEGRITY
```

For ticket entry:

```
QR CODE
   ↓
AUTHENTICATED SCANNER
   ↓
SERVER VALIDATION
   ↓
DATABASE TRANSACTION
   ↓
ONE SUCCESSFUL ENTRY
```

If the server cannot confidently confirm the ticket, the system must not grant entry.

Security must never depend solely on frontend behavior.
