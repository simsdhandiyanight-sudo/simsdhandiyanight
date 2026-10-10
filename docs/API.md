# API.md

## 1. Purpose

This document defines the API conventions for the Event Ticketing & Registration Platform.

The API is the communication layer between:

```text
React Frontend
      ↓
HTTP / HTTPS
      ↓
Django REST Framework API
      ↓
PostgreSQL
```

The API must be:

- Consistent
- Secure
- Predictable
- Validated
- Versionable
- Easy for frontend and backend developers to understand

---

# 2. API Technology
Backend:

- Django
- Django REST Framework

Transport:

- HTTP
- HTTPS in production

Data format:

- JSON

Database:

- PostgreSQL

---

# 3. API Base URL
The API should be exposed under a dedicated API prefix.

Example:

```text
/api/
```

Versioning should be introduced when the project requires stable API evolution.

Recommended structure:

```text
/api/v1/
```

Example:

```text
/api/v1/events/
/api/v1/registrations/
/api/v1/tickets/
/api/v1/scans/
```

The actual deployed domain must come from environment configuration.

Do not hardcode production domains throughout the frontend.

## Manual payment proof submission

`POST /api/v1/payments/proof/registrations/{registration_id}/submit/` accepts
multipart form data containing separate `utr_reference` and `transaction_id`
values plus the payment screenshot. Both references are required, normalized
to uppercase, and checked for duplicates among manual UPI submissions.

---

# 4. API Versioning
API versions should be explicit once versioning is adopted.

Example:

```text
/api/v1/events/
/api/v1/registrations/
/api/v1/tickets/
/api/v1/scans/
```

A breaking API change should normally result in a new API version rather than silently changing the existing contract.

Example:

```text
/api/v1/...
/api/v2/...
```

Do not create a new API version for every small change.

---

# 5. Authentication
Authentication is required for protected staff and administrative operations.

Public operations may be unauthenticated where explicitly permitted.

Examples:

### Public

```text
View public event information
Online registration
```

### Protected

```text
On-spot registration
Ticket scanning
Ticket management
Event management
Dashboard
User management
Audit information
```

The exact authorization requirements must follow `SECURITY.md`.

---

# 6. Authorization
Authentication answers:

```text
Who are you?
```

Authorization answers:

```text
Are you allowed to perform this action?
```

The backend must enforce authorization.

Never trust:

```json
{
  "role": "ADMIN"
}
```

sent by the frontend.

The server must determine the authenticated user's role and permissions.

---

# 7. Roles
Primary application roles:

```text
ADMIN
REGISTRATION_STAFF
SCANNER_STAFF
```

Typical responsibilities:

### ADMIN
Can manage:

- Events
- Users/staff
- Registrations
- Tickets
- Reports
- Audit information

### REGISTRATION_STAFF
Can:

- Create on-spot registrations
- View relevant registration information
- Generate tickets

### SCANNER_STAFF
Can:

- Scan tickets
- Receive ticket validation results
- View information necessary for entry operations

Actual permissions must be enforced by the backend.

---

# 8. Authentication Failure
If a request requires authentication and the user is not authenticated:

```text
401 Unauthorized
```

Example response:

```json
{
  "error": {
    "code": "AUTHENTICATION_REQUIRED",
    "message": "Authentication is required."
  }
}
```

Do not expose internal authentication details.

---

# 9. Authorization Failure
If the user is authenticated but does not have permission:

```text
403 Forbidden
```

Example:

```json
{
  "error": {
    "code": "PERMISSION_DENIED",
    "message": "You do not have permission to perform this action."
  }
}
```

Do not return sensitive information explaining internal authorization logic.

---

# 10. Resource Naming
Use plural nouns for collection endpoints.

Preferred:

```text
/events/
/registrations/
/tickets/
/scans/
/users/
```

Avoid:

```text
/getEvents/
/createTicket/
/scanTicketNow/
```

The HTTP method should communicate the operation.

---

# 11. HTTP Methods
Use standard HTTP methods consistently.

### GET
Retrieve data.

```http
GET /api/v1/events/
```

### POST
Create a resource or perform an operation that creates a server-side result.

```http
POST /api/v1/payments/create-order/
```

```http
POST /api/v1/scans/
```

### PATCH
Partially update a resource.

```http
PATCH /api/v1/events/123/
```

### PUT
Use when complete replacement is actually required.

Do not use `PUT` merely because it exists.

### DELETE
Delete a resource only when deletion is permitted by the business rules.

For tickets, cancellation may be preferable to physical deletion.

---

# 12. Event Endpoints
Example endpoint structure:

```http
GET    /api/v1/events/
POST   /api/v1/events/

GET    /api/v1/events/{event_id}/
PATCH  /api/v1/events/{event_id}/
DELETE /api/v1/events/{event_id}/
```

Access should depend on the endpoint.

For example:

```text
Public:
GET /events/

Admin:
POST /events/
PATCH /events/{id}/
DELETE /events/{id}/
```

---

# 13. Registration Endpoints
Example:

```http
GET  /api/v1/registrations/{registration_id}/
```

Administrative listing:

```http
GET /api/v1/registrations/
```

On-spot creation is staff-authorized:

```http
POST /api/v1/registrations/on-spot/
```

Public online creation uses the payment-order and verification flow in section 14; direct public `POST /api/v1/registrations/` is blocked with `402 PAYMENT_REQUIRED`. One completed registration represents one buyer/order and may return one or more tickets. Each returned ticket has its own ID, attendee name, and opaque QR token; the current combo returns six tickets. Include exactly one valid `attendee_names` entry per admission in the selected offer. The buyer name is the first attendee name, and the buyer email and phone are shared once on the registration.

Registration and ticket responses include a human-facing `registration_code`
such as `SIMS-DN-2026-00001`. Codes increment continuously per event year and
appear on tickets and registration records. The existing `id` and
`registration_id` UUID fields remain unchanged for API lookups and relationships.
Each ticket response also includes its own unique `ticket_code`, such as
`SIMS-DN-2026-00001-T01`; tickets in one registration use incrementing
admission suffixes and retain separate QR tokens.

---

# 14. Online Payment and Registration

Public online tickets are issued only after the backend validates PayU's reverse response hash and confirms the captured transaction with PayU's Verify Payment API.

Create or replay an order with a UUID idempotency key:

```http
POST /api/v1/payments/create-order/
Content-Type: application/json
Idempotency-Key: 85635d34-bcbf-4a6d-b15e-0019e16bba80
```

Example:

```json
{
  "event_id": "8b3f7a20-6e8d-4b91-a462-9c5d2f1e7043",
  "ticket_tier_id": "<id returned by the events API>",
  "buyer": {
    "name": "Example User",
    "email": "user@example.com",
    "phone": "+919999999999"
  },
  "attendee_names": ["Example User"]
}
```

For the six-admission combo, `attendee_names` must contain six valid names. The backend derives price, currency, event, and admission count from the selected ticket offer; a client cannot supply payment success or ticket status.

The first response is `201 Created`; a retry with the same key and normalized request reuses the existing payment intent/transaction and returns `200 OK`. Reusing the key with a different request returns `409 Conflict`. The backend response contains `checkout_url` and the signed `payment_params` for the frontend to submit as an `application/x-www-form-urlencoded` POST to PayU. The merchant salt is never returned.

PayU posts its signed success and failure responses to the configured callback URLs. Those callbacks and the configured PayU webhook share server-side processing. The callback hash is checked, then the backend calls PayU's Verify Payment API using its server-side credential:

```http
POST /api/v1/payments/payu/success/
Content-Type: application/x-www-form-urlencoded
```

The failure callback is `POST /api/v1/payments/payu/failure/`; PayU webhook notifications are accepted at `POST /api/v1/payments/payu/webhook/`. Configure the exact webhook URL in the PayU merchant dashboard. The frontend return page is set using `PAYU_FRONTEND_URL`.

The browser return page can check transaction status with:

```http
GET /api/v1/payments/status/?txnid=<merchant_transaction_id>&idempotency_key=<booking_uuid>
```

The idempotency key must be the UUID originally sent in `Idempotency-Key`; it prevents an exposed transaction reference alone from granting access to tickets. The status endpoint also reconciles directly with PayU and never trusts browser-supplied payment status. It returns tickets only after the merchant transaction ID, amount, booking details, PayU response hash, and PayU's captured transaction status are verified. Duplicate callbacks are idempotent. If PayU confirms capture but ticket issuance fails, the payment remains recorded and the case requires administrator review; tickets are not issued a second time. Administrators can inspect cases through `GET /api/v1/payments/review/dashboard/`.

This implementation follows PayU's [Hosted Checkout](https://docs.payu.in/docs/cb-integration-non-seamless) request/reverse-hash format and the documented Verify Payment API (`verify_payment` command at `https://test.payu.in/merchant/postservice.php?form=2` in test mode and `https://info.payu.in/merchant/postservice.php?form=2` in production).

Set backend-only `PAYU_MERCHANT_KEY` and `PAYU_MERCHANT_SALT`, plus `PAYU_ENVIRONMENT=test` during sandbox integration. Production uses `PAYU_ENVIRONMENT=production`; test and production merchant credentials must remain separate. `PAYU_SUCCESS_URL` and `PAYU_FAILURE_URL` should point to the backend callback URLs. `PAYU_WEBHOOK_URL` is the corresponding public webhook endpoint for dashboard configuration.

Direct public `POST /api/v1/registrations/` returns `402 PAYMENT_REQUIRED`; it cannot issue online tickets. Authorized on-spot registration continues through its protected endpoint and does not use the payment gateway.

The Dhandiya Night canonical event UUID is `8b3f7a20-6e8d-4b91-a462-9c5d2f1e7043`, with slug `dhandiya-night-2026`. The public landing page uses hardcoded descriptive content; event detail and ticket availability are loaded from the backend API. Render seeds the canonical event and ticket tiers at startup. Do not use the frontend demo ID `evt-technova-2026` as the production event primary key.

Configured offer prices are ₹149 for one admission and ₹745 for six combo admissions. PayU payment requests include the existing fixed ₹4 per-admission charge (₹153 single; ₹769 combo); this charge is not shown on the registration page and is not a percentage-based tax calculation. Refunds and settlement reversals are not supported in this application. Sandbox integration must be validated with the merchant account before enabling production mode.

---

# 15. On-Spot Registration
On-spot registration is a protected operation.

Conceptual flow:

```text
Staff Authentication
        ↓
POST /registrations/
        ↓
Backend Authorization
        ↓
Validate attendee data
        ↓
registration_source = ON_SPOT
        ↓
Create Registration
        ↓
Create one Ticket per admission in selected offer
        ↓
Return Registration and Tickets
```

The server should ensure that unauthorized users cannot create on-spot registrations.

---

# 16. Ticket Endpoints
Possible endpoints:

```http
GET  /api/v1/tickets/{ticket_id}/
POST /api/v1/tickets/{ticket_id}/cancel/
```

Ticket status should not be freely writable through a generic update endpoint.

Avoid:

```http
PATCH /tickets/123/
```

with a request such as:

```json
{
  "status": "USED"
}
```

The client must never directly mark a ticket as used.

---

# 17. Ticket Scanning API
Ticket scanning is one of the most critical APIs in the system.

Example:

```http
POST /api/v1/scans/
Content-Type: application/json
```

Request:

```json
{
  "token": "opaque-ticket-token"
}
```

The authenticated scanner user is obtained from the server-side authentication context.

Do not send:

```json
{
  "token": "...",
  "staff_id": 10,
  "role": "SCANNER_STAFF",
  "event_id": 123,
  "status": "USED"
}
```

as authoritative information.

The server should determine the authenticated staff user and validate the ticket/event relationship.

---

# 18. Scan Processing
The backend scan operation should conceptually perform:

```text
Receive token
      ↓
Authenticate scanner
      ↓
Authorize scanner
      ↓
Find ticket
      ↓
Lock ticket
      ↓
Validate ticket
      ↓
Validate event
      ↓
Validate ticket status
      ↓
Record result
      ↓
If valid:
    create successful entry
    mark ticket USED
      ↓
Return result
```

This operation must be transaction-safe.

---

# 19. Successful Scan Response
Example:

```http
200 OK
```

```json
{
  "success": true,
  "result": "ENTRY_GRANTED",
  "ticket": {
    "id": 123,
    "status": "USED"
  },
  "scanned_at": "2026-10-06T10:30:00Z"
}
```

The exact response fields may evolve.

The frontend should use the backend response rather than making its own validity decision.

---

# 20. Already Used Ticket
If a ticket has already been successfully consumed:

```http
409 Conflict
```

Example:

```json
{
  "success": false,
  "result": "ALREADY_USED",
  "message": "This ticket has already been used."
}
```

The exact HTTP status can be adjusted if the final API convention uses another semantic mapping, but the meaning must remain consistent.

---

# 21. Invalid Ticket
For a token that does not correspond to a valid ticket:

```http
404 Not Found
```

Example:

```json
{
  "success": false,
  "result": "INVALID_TICKET",
  "message": "Ticket not found."
}
```

Avoid revealing unnecessary information that helps attackers enumerate valid ticket tokens.

The final implementation should balance operational scanner feedback with token enumeration resistance.

---

# 22. Cancelled Ticket
Example:

```json
{
  "success": false,
  "result": "CANCELLED",
  "message": "This ticket has been cancelled."
}
```

The ticket must not be marked as used.

---

# 23. Wrong Event
If a valid ticket belongs to another event:

```json
{
  "success": false,
  "result": "WRONG_EVENT",
  "message": "This ticket is not valid for this event."
}
```

The ticket must remain unchanged.

---

# 24. Event Closed
If scanning is not permitted because the event is closed:

```json
{
  "success": false,
  "result": "EVENT_CLOSED",
  "message": "Entry is currently closed."
}
```

The ticket must not be consumed.

---

# 25. Scan Result States
The frontend should be prepared to handle at least:

```text
ENTRY_GRANTED
ALREADY_USED
INVALID_TICKET
CANCELLED
WRONG_EVENT
EVENT_CLOSED
UNAUTHORIZED
NETWORK_ERROR
```

The exact API representation may use an enum or error code.

The meaning of each result must remain consistent.

---

# 26. Network Failure
A network failure is not a successful ticket scan.

If the scanner cannot reach the backend:

```text
NETWORK_ERROR
```

must be shown.

The scanner must not assume:

```text
ENTRY_GRANTED
```

because the QR code was successfully decoded.

Important rule:

```text
QR decoded
≠
Ticket validated
```

and:

```text
API unavailable
≠
Entry granted
```

---

# 27. Error Response Format
Use a consistent error structure.

Recommended:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message.",
    "details": {}
  }
}
```

For validation errors:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Please correct the highlighted fields.",
    "details": {
      "email": [
        "Enter a valid email address."
      ]
    }
  }
}
```

Do not expose raw Django/Python exceptions.

---

# 28. HTTP Status Codes
Use status codes consistently.

Recommended mapping:

```text
200 OK
Successful retrieval or operation

201 Created
Resource successfully created

204 No Content
Successful operation with no response body

400 Bad Request
Invalid request

401 Unauthorized
Authentication required/failed

403 Forbidden
Authenticated but not authorized

404 Not Found
Requested resource does not exist

409 Conflict
Request conflicts with current resource state

422 Unprocessable Entity
Optional alternative for semantic validation failures

429 Too Many Requests
Rate limit exceeded

500 Internal Server Error
Unexpected server failure
```

Do not return `200 OK` for every type of failure.

---

# 29. Validation Errors
Validation errors should identify the affected field where appropriate.

Example:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid registration data.",
    "details": {
      "attendee_name": [
        "This field is required."
      ],
      "email": [
        "Enter a valid email address."
      ]
    }
  }
}
```

Do not rely only on frontend validation.

---

# 30. Pagination
Collection endpoints should use pagination when the response can become large.

Example:

```http
GET /api/v1/registrations/?page=1&page_size=25
```

Possible response:

```json
{
  "count": 120,
  "next": "...",
  "previous": null,
  "results": []
}
```

The exact pagination structure should follow the project's DRF configuration.

---

# 31. Filtering
Use query parameters for collection filtering.

Example:

```http
GET /api/v1/registrations/?event_id=123
```

Possible filters:

```text
event_id
registration_source
ticket_status
created_from
created_to
```

Only expose filters that are actually required.

---

# 32. Searching
Search parameters should be explicit.

Example:

```http
GET /api/v1/registrations/?search=rahul
```

Search should be implemented using safe ORM queries.

Do not build SQL strings from search input.

---

# 33. Sorting
If sorting is required:

```http
GET /api/v1/registrations/?ordering=-created_at
```

Only allow approved ordering fields.

Do not allow arbitrary database expressions from the client.

---

# 34. API Authentication Headers
If token-based authentication is used, the frontend should send credentials through the project's configured authentication mechanism.

Example:

```http
Authorization: ******
```

Never place authentication tokens in:

```text
URL query parameters
```

such as:

```text
/api/events/?token=...
```

unless there is a very specific, reviewed requirement.

The public manual-payment status and Ticket ID confirmation endpoints use the
opaque `X-Proof-Access-Token` request header. Do not move this capability token
into a URL or log it. Payment proof screenshots are only delivered through the
authenticated administrator screenshot endpoint; Cloudinary delivery URLs are
never returned to the frontend.

---

# 35. CSRF and CORS
The API configuration must follow the authentication architecture.

If cookie-based authentication is used:

- Configure CSRF protection correctly.
- Do not disable CSRF globally.
- Restrict allowed origins.

CORS should allow only trusted frontend origins.

Do not use:

```text
Allow all origins
```

in production without a deliberate security reason.

---

# 36. Rate Limiting
Rate limiting should be considered for endpoints that can be abused.

Important candidates include:

```text
Public registration
Authentication
Ticket lookup
Ticket scanning
Password reset
```

The exact limits should be based on expected traffic and operational requirements.

A scanner operation must be able to handle legitimate rapid scanning while still preventing abuse.

---

# 37. Registration Idempotency
Online payment-order and on-spot registration requests require an `Idempotency-Key` header containing a UUID. Browser clients making cross-origin requests must be allowed to send this header by the API's CORS policy.

```http
Idempotency-Key: 85635d34-bcbf-4a6d-b15e-0019e16bba80
```

The client reuses the same key for retries of one logical attempt. Online requests persist the key and normalized request fingerprint in `PaymentIntent`; its primary-key constraint arbitrates concurrent requests and the intent is associated with the resulting registration and payment records. On-spot requests store the key and fingerprint in `RegistrationIdempotency` in the same transaction that creates the registration and tickets.

- On-spot creation returns `201 Created` with `Idempotency-Replayed: false`; a replay returns the same registration/tickets with `200 OK` and `Idempotency-Replayed: true`.
- Online order creation returns `201 Created` for a new order and `200 OK` for a replay, with a `replayed` boolean in the JSON response. If the intent is already paid, the replay also returns the original registration/tickets.
- Reusing the key with a different request returns `409 Conflict` (`IDEMPOTENCY_CONFLICT`).
- If creation fails, the transaction rolls back the key and any partial registration/tickets, so the same key can be retried.

Different keys remain separate attempts; email and phone are not used as idempotency keys and are not made unique by this behavior. Payment verification is independently protected by persisted payment/order identifiers and a database uniqueness constraint allowing only one verified capture per payment intent.

---

# 38. API Security
The API must:

- Validate all incoming data
- Authenticate protected requests
- Authorize every protected operation
- Use HTTPS in production
- Avoid leaking sensitive errors
- Prevent SQL injection
- Protect against unauthorized event access
- Prevent arbitrary ticket state changes
- Protect ticket scanning against race conditions
- Apply rate limits where appropriate

---

# 39. Event Authorization
Administrative APIs must ensure that users can only access events they are authorized to manage.

Do not rely on the frontend hiding events.

Bad:

```text
Frontend hides Event B
        ↓
User manually requests Event B API
        ↓
Backend returns Event B
```

Correct:

```text
Frontend request
        ↓
Backend authorization
        ↓
Allowed?
   ├── Yes → return data
   └── No  → 403
```

---

# 40. Ticket Enumeration Protection
Ticket tokens should be opaque and difficult to guess.

API responses should not unnecessarily reveal information that allows attackers to discover valid tickets.

Avoid exposing internal sequential IDs as the only ticket credential.

Example:

```text
Bad:
QR = 12345

Better:
QR = securely-generated opaque token
```

---

# 41. API Logging
Log important operational information without exposing secrets.

Do not log:

```text
Passwords
Authentication tokens
Authorization headers
Sensitive personal data unnecessarily
Complete QR credentials where avoidable
```

Logs should help diagnose:

```text
Authentication failures
Authorization failures
API errors
Ticket scan failures
Unexpected server errors
```

---

# 42. Audit Logging
Important actions should generate audit records where required.

Examples:

```text
Event created
Event updated
Registration created
On-spot registration created
Ticket cancelled
Ticket scanned
User permission changed
```

Audit records should identify:

```text
Who
What
When
Which resource
```

where appropriate.

---

# 43. API Documentation
Every production API endpoint should have enough documentation for another developer to understand:

```text
Endpoint
HTTP method
Authentication requirement
Authorization requirement
Request body
Query parameters
Response
Error responses
Important business rules
```

OpenAPI/Swagger documentation may be introduced if required by the project.

Do not create API documentation that contradicts the actual implementation.

---

# 44. Frontend API Layer
The frontend should communicate with the backend through a consistent API layer.

Recommended structure:

```text
src/
├── api/
│   ├── client.ts
│   ├── authApi.ts
│   ├── eventApi.ts
│   ├── registrationApi.ts
│   ├── ticketApi.ts
│   └── scanApi.ts
```

The exact structure may change based on project conventions.

Avoid scattering raw `fetch()` or Axios calls throughout unrelated components.

---

# 45. API Client
A shared API client should handle common concerns such as:

```text
Base URL
Authentication
Headers
JSON serialization
Error normalization
Timeouts where appropriate
```

Feature-specific modules should use the shared client.

---

# 46. API and Business Logic Separation
Do not place complex business logic directly inside HTTP request handlers.

Prefer:

```text
API View
    ↓
Serializer / Validation
    ↓
Service / Business Logic
    ↓
ORM
    ↓
Database
```

This makes critical behavior easier to test.

---

# 47. Scanner API Performance
The ticket scan endpoint is operationally sensitive.

A scanner may process many tickets quickly.

Therefore:

- Keep the request path efficient.
- Avoid unnecessary database queries.
- Avoid unnecessary external API calls.
- Keep the transaction limited to the critical operation.
- Return a clear result quickly.
- Do not perform heavy reporting work during a scan request.

The scan endpoint should prioritize correctness and predictable response time.

---

# 48. API Timeout Behavior
The frontend should handle requests that take too long or fail.

For scanner operations:

```text
Request
   ↓
Timeout/network failure
   ↓
Show NETWORK_ERROR
```

Never convert an uncertain request state into a successful entry state.

---

# 49. Third-Party Integrations
External services should be isolated behind dedicated integration modules.

Examples, if introduced:

```text
Email service
SMS service
Payment provider
Cloud storage
Analytics
```

Do not spread third-party SDK calls throughout business logic.

Use environment variables for credentials.

---

# 50. API Testing
Important API tests include:

```text
Public event retrieval
Online registration
On-spot registration authorization
Ticket generation
Ticket cancellation
Valid scan
Duplicate scan
Concurrent scan
Invalid token
Cancelled ticket
Wrong event
Closed event
Unauthorized scanner
Validation errors
Authentication failure
Permission failure
Rate limiting
```

Critical security and ticketing behavior should have automated tests.

---

# 51. API Change Checklist
Before changing an API:

```text
[ ] Existing endpoint inspected
[ ] Existing frontend usage inspected
[ ] Authentication reviewed
[ ] Authorization reviewed
[ ] Request schema reviewed
[ ] Response schema reviewed
[ ] Validation reviewed
[ ] Error handling reviewed
[ ] Database impact reviewed
[ ] Security impact reviewed
[ ] Tests updated
[ ] Documentation updated
```

For breaking changes:

```text
[ ] API versioning considered
[ ] Frontend migration planned
[ ] Existing clients considered
```

---

# 52. AI Coding Agent Rules
AI coding agents must:

1. Read `API.md` before modifying API contracts.
2. Inspect existing endpoints before creating new ones.
3. Reuse established response formats.
4. Reuse existing authentication mechanisms.
5. Never bypass authorization.
6. Never trust client-provided roles or permissions.
7. Never expose raw server exceptions.
8. Never expose secrets in responses or logs.
9. Never allow the client to directly mark tickets as used.
10. Preserve transaction safety for ticket scanning.
11. Add API tests for important behavior.
12. Update API documentation when stable contracts change.
13. Avoid introducing a new API pattern when an existing project pattern already works.

---

# 53. Core API Principles
The API must preserve these principles:

```text
Client requests
      ↓
Authentication
      ↓
Authorization
      ↓
Validation
      ↓
Business logic
      ↓
Database transaction
      ↓
Consistent response
```

For ticket scanning:

```text
QR decoded
      ↓
POST /scans/
      ↓
Authenticate scanner
      ↓
Authorize scanner
      ↓
Validate token
      ↓
Validate event
      ↓
Lock ticket
      ↓
Check status
      ↓
Record successful entry
      ↓
Mark ticket USED
      ↓
Return ENTRY_GRANTED
```

The frontend must never be treated as the authority for ticket validity.

---

# 54. Final Principle
The API is a security and business boundary, not simply a way to move JSON between React and Django.

Every request must be treated as untrusted input.

The backend must determine:

```text
Who is making the request?
        ↓
Are they allowed?
        ↓
Is the input valid?
        ↓
Is the requested operation allowed?
        ↓
Can the database safely perform it?
        ↓
What result should the client receive?
```

The API contract must remain consistent with:

```text
PRD.md
ARCHITECTURE.md
SECURITY.md
DATABASE.md
CODE_STYLE.md
```

When the implementation changes a stable API convention, update this document rather than allowing documentation and code to drift apart.

---

# 55. Ticket Email Delivery

Ticket email is queued as one `TicketDelivery` record per issued ticket. Online
deliveries become eligible only after verified payment; on-spot deliveries are
eligible after registration. The payment verification endpoint does not wait
for Brevo and never treats an email failure as a payment failure.

Administrators can inspect the queue at `GET /api/v1/payments/delivery/dashboard/`,
retry a failed message at
`POST /api/v1/payments/delivery/{delivery_id}/retry/`, and change an unsent
message's priority at
`PATCH /api/v1/payments/delivery/{delivery_id}/priority/` with
`{"priority":"STAFF"}`, `{"priority":"COMPLIMENTARY"}`, or
`{"priority":"REGULAR"}`. These operations require the ADMIN role.

Brevo delivery callbacks use `POST /api/v1/payments/brevo/webhook/`, the
`X-Brevo-Webhook-Token` secret, and an event plus message ID. Configure the
Brevo callback and application secrets out of band; credentials are never
returned to the frontend.

Run `python manage.py process_ticket_emails` as a scheduled worker, or
`python manage.py process_ticket_emails --loop` under a process supervisor.
Configure `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, and optionally
`BREVO_SENDER_NAME` and `BREVO_WEBHOOK_TOKEN`. Without the API key and sender,
the worker exits with a configuration error.

The local daily allocation is strictly 295 regular messages and 5 staff or
complimentary messages. Unused priority slots are not borrowed by regular
messages. A timeout or provider 5xx has an ambiguous outcome: the item remains
in `SENDING` with its slot reserved to prevent duplicate delivery. Reconcile
such an item against Brevo before taking manual recovery action.
