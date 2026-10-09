# ARCHITECTURE.md

# Event Ticketing & Registration Platform
## System Architecture

This document defines the technical architecture of the Event Ticketing & Registration Platform.

The architecture is designed around:

- Reliability
- Transactional correctness
- Security
- Simple deployment
- Maintainability
- Concurrent ticket scanning

The system should initially use a **modular monolith architecture** rather than microservices.

---

# 1. Architecture Overview

The recommended architecture is:

```text
                    ┌──────────────────────┐
                    │      Attendees       │
                    │  Mobile / Desktop    │
                    └──────────┬───────────┘
                               │
                               │ HTTPS
                               ▼
                    ┌──────────────────────┐
                    │    React Frontend    │
                    │                      │
                    │ - Public Registration│
                    │ - Ticket UI          │
                    │ - Staff UI           │
                    │ - QR Scanner         │
                    │ - Admin Dashboard    │
                    └──────────┬───────────┘
                               │
                               │ REST / JSON
                               ▼
                    ┌──────────────────────┐
                    │ Django REST Backend  │
                    │                      │
                    │ - Authentication     │
                    │ - Authorization      │
                    │ - Registration       │
                    │ - Tickets            │
                    │ - Scanning           │
                    │ - Events             │
                    │ - Audit              │
                    └──────────┬───────────┘
                               │
                               │ Django ORM
                               ▼
                    ┌──────────────────────┐
                    │     PostgreSQL       │
                    │                      │
                    │ Events               │
                    │ Users                │
                    │ Registrations        │
                    │ Tickets              │
                    │ Scans                │
                    │ Audit Logs           │
                    └──────────────────────┘
```

---

# 2. Technology Stack

## 2.1 Frontend
Recommended:

```
React
TypeScript
```

The frontend is responsible for:

- Public event pages
- Registration forms
- Ticket display
- Staff interfaces
- QR scanner
- Admin dashboard

The frontend must not be treated as the source of truth for security-sensitive state.

---

# 3. Backend
Recommended:

```
Python
Django
Django REST Framework
```

The backend is responsible for:

- Authentication
- Authorization
- Event management
- Registration
- Ticket creation
- QR token validation
- Ticket scanning
- Attendance
- Audit logging
- Business rules

All critical business rules must be enforced here.

---

# 4. Database
Primary database:

```
PostgreSQL
```

PostgreSQL is the authoritative transactional data store.

It is responsible for maintaining:

- Registration data
- Ticket state
- Scan records
- User roles
- Event state
- Database constraints

The database must protect critical invariants even if multiple requests arrive simultaneously.

---

# 5. Why PostgreSQL
The ticket-scanning workflow requires transactional correctness.

Consider:

```
Scanner A ──┐
            ├──> Backend ──> PostgreSQL
Scanner B ──┘
```

Both scanners may attempt to validate the same ticket at almost the same time.

PostgreSQL provides:

- Transactions
- Row-level locking
- Unique constraints
- Consistent reads/writes
- Reliable concurrent updates

This makes it appropriate for the ticket-entry workflow.

---

# 6. Why Django
Django provides several capabilities required by this application:

- Authentication
- Authorization foundations
- ORM
- Database migrations
- Transactions
- Request handling
- Validation
- Security middleware
- Administrative tooling

Django REST Framework provides the API layer required by the React frontend.

---

# 7. Why React
React is suitable for the interactive parts of the platform:

- Registration forms
- Ticket display
- QR scanner
- Admin dashboards
- Real-time-ish operational feedback
- Search and filtering

The scanner requires an interactive browser interface capable of accessing the device camera.

---

# 8. Architectural Style
The initial system should use a:

```
MODULAR MONOLITH
```

This means:

```
One frontend application
+
One Django backend
+
One PostgreSQL database
```

The Django backend should still be separated into logical modules/apps.

---

# 9. Backend Module Structure
Recommended Django apps:

```
backend/
├── events/
├── registrations/
├── tickets/
├── scanning/
├── accounts/
└── audit/
```

The exact structure can be adjusted to the existing repository.

---

# 10. Events Module
Responsible for:

- Event creation
- Event configuration
- Event status
- Registration availability
- Event details

Example responsibilities:

```
Create Event
Update Event
Publish Event
Open Registration
Close Registration
Complete Event
Cancel Event
```

The events module should not contain ticket-scanning business logic.

---

# 11. Registrations Module
Responsible for:

- Online registration
- On-spot registration
- Attendee information
- Registration source
- Registration limits
- Registration lookup

Registration source:

```
ONLINE
ON_SPOT
```

Both sources must use the same registration model.

---

# 12. Tickets Module
Responsible for:

- Ticket creation
- Ticket number
- QR token
- Ticket status
- Ticket lookup
- Ticket cancellation
- Ticket lifecycle

Possible ticket states:

```
ISSUED
USED
CANCELLED
```

The ticket module should contain ticket-related business rules but should not allow the frontend to directly modify ticket state.

---

# 13. Scanning Module
Responsible for:

- QR token validation
- Entry validation
- Scan attempts
- Gate identification
- Scanner identification
- Successful entry recording
- Duplicate-entry prevention

This module is security- and correctness-sensitive.

---

# 14. Accounts Module
Responsible for:

- Authentication
- User accounts
- Roles
- Permissions
- Staff access

Primary roles:

```
ADMIN
REGISTRATION_STAFF
SCANNER_STAFF
```

The exact Django authentication implementation should follow the repository's final configuration.

---

# 15. Audit Module
Responsible for recording important system activity.

Examples:

```
Event created
Event updated
Ticket cancelled
On-spot registration created
Ticket scanned
Entry granted
Ticket rejected
Staff account changed
```

Audit records should not become a second source of truth for ticket state.

The actual ticket state remains in the ticket/entry data model.

---

# 16. Frontend Structure
Recommended structure:

```
frontend/
└── src/
    ├── components/
    ├── features/
    │   ├── events/
    │   ├── registration/
    │   ├── tickets/
    │   ├── scanner/
    │   ├── admin/
    │   └── auth/
    ├── api/
    ├── lib/
    ├── hooks/
    └── types/
```

The actual repository structure takes precedence if the project already has an established organization.

---

# 17. Frontend Responsibilities
The frontend should handle:

```
Presentation
Form interaction
Camera interaction
API communication
Loading states
Error states
Temporary UI state
```

The frontend must NOT be responsible for:

```
Final authorization
Ticket validity
Ticket state
Successful entry decision
Database integrity
```

---

# 18. Backend Responsibilities
The backend handles:

```
Authentication
Authorization
Validation
Business rules
Database transactions
Ticket state
Entry decisions
Audit records
API responses
```

The backend is the authoritative business layer.

---

# 19. State Ownership

## Server State
The server/database owns:

```
Events
Registrations
Tickets
Ticket status
Scan records
Attendance
Users
Roles
Permissions
```

## Client State
The frontend may own:

```
Form input
Camera state
Loading state
Temporary UI state
Current scan result display
Filters
Modal state
```

Never copy authoritative ticket state into client state and treat the copy as truth.

---

# 20. Online Registration Architecture
The online registration flow is:

```
Attendee
   │
   ▼
React Registration Form
   │
   │ POST
   ▼
Django API
   │
   ├── Validate Event
   │
   ├── Validate Input
   │
   ├── Check Registration Rules
   │
   ▼
PostgreSQL Transaction
   │
   ├── Create Registration
   │
   ├── Resolve selected offer and admission count
   ├── Create one Ticket per admission
   └── Generate a unique opaque QR token for each Ticket
   │
   ▼
API Response
   │
   ▼
React Confirmation/Ticket Page
```

Registration/order and all of its tickets must be created atomically. A single-ticket offer creates one ticket; the Dhandiya Night combo creates four separately scannable tickets for one buyer/order. Capacity is reserved in admissions, not orders.

---

# 21. On-Spot Registration Architecture
The on-spot flow is:

```
Registration Staff
        │
        ▼
React On-Spot Form
        │
        │ POST
        ▼
Django API
        │
        ├── Authenticate Staff
        ├── Authorize Staff
        ├── Validate Input
        ├── Validate Event
        │
        ▼
PostgreSQL Transaction
        │
        ├── Create Registration
        │      source = ON_SPOT
        │
        ├── Resolve selected offer and admission count
        └── Create one Ticket per admission with its own opaque token
        │
        ▼
Registration and Ticket Response
        │
        ▼
Display / Print Ticket
```

Each generated ticket must be compatible with the same scanner used for online tickets. A combo order returns four independent tickets.

---

# 21.1 Registration, Tickets, and Payment Boundary

A registration represents one buyer's order and owns the buyer/contact information. It has a one-to-many relationship to Ticket. Ticket identity, status, QR token, and scan history are per ticket; buyer details are not duplicated across the ticket records.

Ticket offers preserve the configured Dhandiya Night prices in INR: ₹149 for one admission and ₹745 for a combo of six admissions (five paid, one included). Razorpay orders add a fixed ₹4 per admission (₹153 single; ₹769 combo); this charge is not shown on the registration page. Registration creation must not be represented as payment success, and payment records must not be fabricated. See `docs/PRODUCT_DECISIONS.md`.

---

# 21.2 Canonical Event Identity and Demo Data

The production Dhandiya Night event is identified by UUID `8b3f7a20-6e8d-4b91-a462-9c5d2f1e7043` and slug `dhandiya-night-2026`. The demo ID `evt-technova-2026` is not a production identifier. The events API is the source of truth; the frontend must obtain the event identity from that API.

Existing browser-local and mock registrations, tickets, scans, and users are disposable demo data and are not migrated into the production database. Production starts without sample attendee or staff records and may be initialized only with explicitly approved event/ticket-offer seed data.

---

# 22. QR Generation Architecture
The QR code should represent a unique, opaque ticket token.

Conceptually:

```
Ticket
   │
   └── qr_token
          │
          ▼
      QR Generator
          │
          ▼
       QR Image
```

The QR code should not contain unnecessary attendee information.

The scanner reads the token and sends it to the backend.

---

# 23. QR Scanning Architecture
The scanner flow is:

```
Scanner Device
      │
      ▼
Browser Camera
      │
      ▼
QR Decoder
      │
      ▼
QR Token
      │
      │ POST
      ▼
Django Scan API
      │
      ├── Authenticate Scanner
      ├── Authorize Scanner
      ├── Validate Event
      ├── Find Ticket
      ├── Start Transaction
      │
      ▼
PostgreSQL
      │
      ├── Lock Ticket
      ├── Check Status
      ├── Record Entry
      └── Mark Ticket Used
      │
      ▼
API Response
      │
      ▼
Scanner UI
```

---

# 24. Critical Concurrency Architecture
This is the most important architectural rule in the project.

Suppose:

```
Gate 1 → Scanner A
Gate 2 → Scanner B
```

Both scan:

```
TKT-001
```

at nearly the same time.

The requests may reach the server like:

```
Request A ───────┐
                 ├──> Django
Request B ───────┘
```

Django must use a database transaction.

Conceptually:

```
BEGIN
   ↓
SELECT ticket FOR UPDATE
   ↓
Check ticket
   ↓
If unused
   ├── Create successful entry
   └── Mark ticket USED
   ↓
COMMIT
```

When another transaction tries to process the same ticket, it must wait for the lock and then re-check the ticket state.

The second request must therefore see:

```
USED
```

and reject the entry.

---

# 25. Why Frontend Locking Is Not Enough
Do NOT solve duplicate scanning with:

```
isScanning = true
```

or:

```
localStorage
```

or:

```
React state
```

or:

```
disable button
```

These only affect one browser/device.

They cannot protect against:

```
Scanner A
Scanner B
Scanner C
Scanner D
```

all communicating with the backend.

Only the server/database transaction can guarantee the business rule.

---

# 26. Entry Transaction
The preferred conceptual implementation is:

```
BEGIN TRANSACTION

SELECT ticket
FOR UPDATE

IF ticket does not exist:
    return INVALID

IF ticket.event != requested event:
    return WRONG_EVENT

IF ticket.status == CANCELLED:
    return CANCELLED

IF ticket.status == USED:
    return ALREADY_USED

CREATE successful scan/entry record

UPDATE ticket
SET status = USED
SET used_at = current timestamp

COMMIT

return ENTRY_GRANTED
```

The exact Django implementation must follow the repository's coding conventions.

---

# 27. Database Constraints
Application logic should be supported by database constraints.

Important constraints include:

```
ticket_number UNIQUE
qr_token UNIQUE
successful_entry.ticket_id UNIQUE
```

The exact schema is defined in:

```
docs/DATABASE.md
```

The database must prevent impossible states even if application code contains an unexpected bug.

---

# 28. API Communication
Frontend and backend communicate using:

```
HTTPS
+
JSON
+
REST API
```

Base path:

```
/api/v1
```

Example:

```
POST /api/v1/events/123/scans
```

The API contract is defined in:

```
docs/API.md
```

---

# 29. Authentication Flow
Protected operations follow:

```
User
 ↓
Login
 ↓
Authentication
 ↓
Authenticated Session / Token
 ↓
API Request
 ↓
Authentication Verification
 ↓
Authorization
 ↓
Operation
```

The backend must determine the authenticated identity.

The client must never be allowed to simply declare:

```
role = ADMIN
```

---

# 30. Authorization Flow
For every protected request:

```
Request
  ↓
Authenticated?
  │
  ├── NO → 401
  │
  ▼
Authorized?
  │
  ├── NO → 403
  │
  ▼
Perform operation
```

Example:

```
Scanner Staff
    ↓
POST /scans
    ↓
Allowed
```

But:

```
Scanner Staff
    ↓
POST /events
    ↓
Forbidden
```

---

# 31. Ticket Search Architecture
Ticket search should be handled by the backend.

```
Staff
  ↓
Search UI
  ↓
API
  ↓
Authorization
  ↓
Database Query
  ↓
Filtered Results
```

The frontend should not download the entire ticket database and filter it locally.

---

# 32. Dashboard Architecture
The dashboard should retrieve aggregated data from backend APIs.

Example:

```
Admin Dashboard
      │
      ├── Registration Metrics
      ├── Ticket Metrics
      ├── Attendance Metrics
      ├── Scan Metrics
      └── Gate Metrics
```

The frontend should not calculate authoritative attendance from locally cached tickets.

The backend/database should provide the authoritative counts.

---

# 33. Audit Architecture
Important actions should produce audit records.

Example:

```
Admin
  ↓
Cancel Ticket
  ↓
Ticket Updated
  ↓
Audit Record Created
```

For scanning:

```
Scanner
  ↓
Scan Request
  ↓
Validation
  ↓
Scan Record
```

The audit/scan record should capture the operational history without replacing the ticket's actual state.

---

# 34. Failure Handling

## 34.1 Network Failure
If the scanner cannot contact the backend:

```
Scanner
   ↓
API Request
   ↓
Network Failure
```

Result:

```
VALIDATION FAILED
```

The system must NOT assume success.

---

## 34.2 Database Failure
If PostgreSQL is unavailable:

```
API
 ↓
Database Failure
```

The API should:

- return a safe error,
- log the technical failure server-side,
- never expose database internals.

---

## 34.3 Camera Failure
If the camera cannot be accessed:

```
Camera unavailable
```

The UI should clearly explain the problem.

If permitted by the final product requirements, provide manual token entry.

---

# 35. Scaling Strategy
The initial architecture should be:

```
React
   ↓
Django
   ↓
PostgreSQL
```

If traffic increases, the Django application can be horizontally scaled:

```
             ┌── Django Instance 1
             │
Load Balancer├── Django Instance 2
             │
             └── Django Instance 3
                    │
                    ▼
               PostgreSQL
```

PostgreSQL remains the transactional source of truth.

---

# 36. Multiple Scanner Scaling
Having:

```
3 scanners
4 scanners
10 scanners
```

does not automatically require microservices.

The important requirement is that all scanners communicate with the same authoritative backend/database.

Example:

```
Scanner A ─┐
Scanner B ─┤
Scanner C ─┼──> Django ───> PostgreSQL
Scanner D ─┘
```

The database transaction ensures duplicate-entry protection.

---

# 37. Why Not Microservices Initially
Microservices would add:

- deployment complexity,
- network failure points,
- service discovery,
- monitoring complexity,
- authentication between services,
- distributed transaction concerns,
- higher maintenance cost.

The MVP does not require this complexity.

Start with a modular monolith.

Split services only if real requirements justify it.

---

# 38. Why Not Redis for Ticket Validation
Redis should not be introduced simply to prevent duplicate scans.

PostgreSQL is already the system of record.

Using Redis as the primary ticket-entry authority would create unnecessary complexity and synchronization concerns.

If Redis is introduced later for caching or rate limiting, PostgreSQL must still remain authoritative for ticket entry.

---

# 39. Offline Scanning
Offline scanning is intentionally outside the initial architecture.

Do not implement offline acceptance without a dedicated architecture.

Offline scanning creates difficult problems:

- duplicate acceptance across devices,
- synchronization,
- stale ticket state,
- cancelled tickets,
- conflicting entry records,
- secure local storage.

The MVP should require online backend confirmation before granting entry.

---

# 40. Observability
The system should monitor:

```
API errors
API response latency
Database errors
Authentication failures
Scan success rate
Scan rejection rate
Duplicate scan attempts
Registration failures
```

Useful operational metrics include:

```
Average scan response time
Entries per minute
Entries per gate
Rejected scans
Server errors
```

Do not log sensitive credentials or unnecessary personal data.

---

# 41. Security Boundaries
The main security boundary is:

```
Browser
   │
   │ Untrusted
   ▼
Django API
   │
   │ Trusted business logic
   ▼
PostgreSQL
```

The browser must be considered untrusted.

Anything coming from the browser must be validated.

---

# 42. Deployment Architecture
The exact hosting provider is not fixed by this document.

The deployment should provide:

- HTTPS
- Secure environment variables
- PostgreSQL
- Application monitoring
- Database backups
- Production logging
- Secure authentication configuration

Development, staging, and production environments should use separate configuration and database credentials.

---

# 43. Environment Separation
Use:

```
Development
Staging
Production
```

Each environment should have its own:

- Database
- Secrets
- API configuration
- Allowed origins
- Deployment configuration

Never use production credentials during local development.

---

# 44. Architecture Decision Rules
Before adding a new infrastructure component, answer:

```
Why is the current architecture insufficient?

What problem does the new component solve?

Can PostgreSQL/Django/React already solve it?

What new failure modes does it introduce?

What security implications exist?

What operational cost does it add?

Is it required for the current scale?
```

If the answer is unclear, do not add the component.

---

# 45. Architecture Principles
The project should follow these principles:

## Principle 1 — Backend Authority
The backend determines business outcomes.

## Principle 2 — Database Integrity
Critical invariants must be protected by the database.

## Principle 3 — Atomic Operations
Operations that must succeed together must use transactions.

## Principle 4 — Least Complexity
Do not introduce infrastructure without a real requirement.

## Principle 5 — Secure by Default
Protected operations require authentication and authorization.

## Principle 6 — Observable Operations
Important event operations must be traceable.

## Principle 7 — Fail Safely
When the server cannot confirm entry, do not grant entry.

---

# 46. Final Architecture
The intended MVP architecture is:

```
                         ┌─────────────────┐
                         │    ATTENDEES    │
                         └────────┬────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │ React Frontend  │
                         │                 │
                         │ Registration    │
                         │ Ticket          │
                         │ Scanner         │
                         │ Admin           │
                         └────────┬────────┘
                                  │
                              HTTPS/JSON
                                  │
                                  ▼
                         ┌─────────────────┐
                         │ Django + DRF    │
                         │                 │
                         │ Auth            │
                         │ Events          │
                         │ Registration    │
                         │ Tickets         │
                         │ Scanning        │
                         │ Audit           │
                         └────────┬────────┘
                                  │
                              Django ORM
                                  │
                                  ▼
                         ┌─────────────────┐
                         │   PostgreSQL    │
                         │                 │
                         │ Events          │
                         │ Users           │
                         │ Registrations   │
                         │ Tickets         │
                         │ Entries/Scans   │
                         │ Audit Logs      │
                         └─────────────────┘
```

The central architectural invariant is:

```
ONE TICKET
      ↓
ONE AUTHORITATIVE DATABASE STATE
      ↓
MAXIMUM ONE SUCCESSFUL ENTRY
```

This invariant must survive multiple scanners, simultaneous requests, retries, browser refreshes, and frontend failures.
