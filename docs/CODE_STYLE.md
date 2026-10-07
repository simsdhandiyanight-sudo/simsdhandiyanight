# CODE_STYLE.md

## 1. Purpose

This document defines the coding conventions for the Event Ticketing & Registration Platform.

The goal is to keep the codebase:

- Consistent
- Readable
- Maintainable
- Easy for multiple developers to work on
- Easy for AI coding agents to understand
- Safe for production use

These conventions apply to both the frontend and backend unless a specific section states otherwise.

---

# 2. Technology Stack

## Frontend

- React
- TypeScript
- Vite
- React Router
- Tailwind CSS
- REST API communication

## Backend

- Python
- Django
- Django REST Framework
- Django ORM

## Database

- PostgreSQL

---

# 3. General Principles

Follow these principles when writing code:

1. Prefer simple solutions over clever solutions.
2. Keep functions and components focused on one responsibility.
3. Reuse existing utilities and components before creating new ones.
4. Avoid unnecessary abstractions.
5. Avoid duplicated business logic.
6. Keep business rules on the backend.
7. Never trust values received from the frontend.
8. Write code that is easy to test.
9. Use descriptive names instead of excessive comments.
10. Do not introduce a new library when the existing stack can solve the problem.
11. Keep changes focused on the requested feature or bug.
12. Do not refactor unrelated code without a clear reason.

---

# 4. Naming Conventions

## 4.1 General

Use descriptive names.

### Good

```text
ticket
registration
scan_result
event_status
registration_source
```

### Avoid

```text
x
data
obj
temp
thing
info
```

unless the meaning is obvious from a very small local scope.

---

# 5. Python / Django Naming

## 5.1 Variables and Functions
Use `snake_case`.

```python
registration = get_registration()
ticket_token = generate_ticket_token()
validate_ticket()
```

Avoid:

```text
registrationData
getRegistration()
TicketToken
```

---

## 5.2 Classes
Use `PascalCase`.

```text
Event
Registration
Ticket
TicketScan
RegistrationSerializer
TicketViewSet
```

---

## 5.3 Constants
Use `UPPER_SNAKE_CASE`.

```python
MAX_SCAN_ATTEMPTS = 5
TICKET_TOKEN_LENGTH = 64
```

---

## 5.4 Django Models
Model names should represent business entities.

```text
Event
Registration
Ticket
TicketScan
User
```

Avoid technical names that do not represent the domain.

```text
EventData
TicketManagerTable
RegistrationInformation
```

---

# 6. Django Model Conventions
Models must represent actual business entities and relationships.

Prefer:

```python
class Ticket(models.Model):
    registration = models.OneToOneField(
        Registration,
        on_delete=models.CASCADE,
    )
    token = models.CharField(
        max_length=128,
        unique=True,
    )
    status = models.CharField(
        max_length=20,
        choices=TicketStatus.choices,
    )
```

Avoid putting unrelated business logic into models merely to keep files short.

Business logic should be placed where it can be clearly tested and reused.

---

# 7. Backend Architecture Conventions
Organize backend code by domain/module.

Recommended structure:

```text
backend/
├── manage.py
├── config/
│   ├── settings/
│   ├── urls.py
│   └── wsgi.py
│
├── apps/
│   ├── accounts/
│   ├── events/
│   ├── registrations/
│   ├── tickets/
│   ├── scanning/
│   └── audit/
│
└── requirements/
```

Each module should contain code related to its own responsibility.

Example:

```text
scanning/
├── models.py
├── serializers.py
├── views.py
├── services.py
├── urls.py
└── tests/
```

---

# 8. Business Logic
Critical business rules must not be implemented only in React.

Examples of backend-authoritative rules:

- Ticket validity
- Ticket status
- Duplicate entry prevention
- Event ownership
- Registration permissions
- Staff permissions
- On-spot registration authorization
- Ticket cancellation
- Entry recording

The frontend may provide a convenient user experience, but the backend must enforce the actual rule.

---

# 9. Services
Use service functions/classes when business logic becomes too large for views.

Example:

```python
def register_attendee(*, event, attendee_data, source):
    ...
```

or:

```python
class TicketScanService:
    def scan(self, *, token, event, staff_user):
        ...
```

Services should have a clear responsibility.

Avoid creating services for trivial one-line operations without a real benefit.

---

# 10. Critical Ticket Scanning Code
Ticket scanning is a concurrency-sensitive operation.

Do not implement:

```text
check ticket
↓
if unused
↓
mark ticket used
```

as separate database operations without transaction protection.

The backend must perform the validation and update atomically.

The implementation should follow the architecture defined in `ARCHITECTURE.md` and `SECURITY.md`.

Conceptually:

```text
BEGIN TRANSACTION
        ↓
Lock ticket
        ↓
Validate ticket
        ↓
Check event
        ↓
Check ticket status
        ↓
If unused:
    create successful entry
    mark ticket USED
        ↓
COMMIT
```

Do not move this logic into the frontend.

---

# 11. API Code Style
Use Django REST Framework consistently.

Prefer:

```python
class TicketScanView(APIView):
    ...
```

or existing project-standard DRF views/viewsets.

Do not mix multiple API architectures without a clear reason.

API validation belongs in serializers and/or dedicated validation/service logic.

Example:

```python
class ScanTicketSerializer(serializers.Serializer):
    token = serializers.CharField()
```

Do not assume frontend validation is sufficient.

---

# 12. API Response Naming
Use `snake_case` for API JSON fields unless an existing API convention requires otherwise.

Example:

```json
{
  "ticket_id": 123,
  "registration_id": 456,
  "registration_source": "ON_SPOT",
  "scan_status": "ENTRY_GRANTED"
}
```

Keep response structures consistent across endpoints.

---

# 13. TypeScript Naming

## Variables
Use `camelCase`.

```typescript
const ticketToken = "...";
const registrationSource = "ONLINE";
const scanResult = await scanTicket();
```

## Functions
Use `camelCase`.

```typescript
function validateTicket() {}
function submitRegistration() {}
function scanTicket() {}
```

## Components
Use `PascalCase`.

```text
TicketCard
RegistrationForm
ScannerView
EventDashboard
ScanResult
```

---

# 14. TypeScript Types
Use explicit types for important domain objects.

Example:

```typescript
type RegistrationSource = "ONLINE" | "ON_SPOT";

type TicketStatus = "ISSUED" | "USED" | "CANCELLED";

interface Ticket {
  id: number;
  token: string;
  status: TicketStatus;
  registrationSource: RegistrationSource;
}
```

Avoid unnecessary use of:

```typescript
any
```

If a value is unknown, prefer:

```typescript
unknown
```

and validate/narrow it appropriately.

---

# 15. React Component Structure
Components should have a focused responsibility.

Good:

```text
TicketCard
QRDisplay
ScannerCamera
ScanResult
RegistrationForm
EventSelector
```

Avoid giant components such as:

```text
EventPage.tsx
```

containing hundreds or thousands of lines of unrelated UI, API calls, validation, and business logic.

Split large components when responsibilities become difficult to understand.

---

# 16. React Feature Structure
Prefer feature-oriented organization.

```text
src/
├── components/
├── features/
│   ├── auth/
│   ├── events/
│   ├── registration/
│   ├── tickets/
│   ├── scanner/
│   └── admin/
│
├── api/
├── hooks/
├── lib/
├── types/
└── routes/
```

Keep feature-specific logic close to the feature.

---

# 17. React State
Use the simplest state mechanism that solves the problem.

Prefer local component state for local UI state.

```typescript
const [isLoading, setIsLoading] = useState(false);
```

Use shared/global state only when multiple parts of the application genuinely need the same state.

Do not create global state for every value.

---

# 18. Server State
Data obtained from the backend should be treated as server state.

Examples:

- Events
- Registrations
- Tickets
- Scan results
- Dashboard statistics
- Staff information

Do not create duplicate copies of the same server data in multiple unrelated places without a reason.

Follow the project's established API/data-fetching pattern.

---

# 19. API Calls
Keep API communication separate from presentation components where practical.

Prefer:

```text
features/scanner/
    scannerApi.ts
    ScannerView.tsx
```

rather than putting large API implementations directly inside JSX components.

Example:

```typescript
export async function scanTicket(token: string) {
  return api.post("/scans/", {
    token,
  });
}
```

The component should focus primarily on UI and interaction.

---

# 20. Imports
Keep imports organized and consistent.

Example:

```typescript
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { ScannerCamera } from "@/features/scanner/components/ScannerCamera";

import { scanTicket } from "@/features/scanner/api/scannerApi";
```

Prefer project aliases where configured.

Avoid unnecessarily long relative import chains such as:

```text
../../../../components/Button
```

when an established alias exists.

---

# 21. Formatting
Use the project's configured formatter and linter.

Do not manually format code differently from the repository standard.

Before committing:

```text
format
↓
lint
↓
type check
↓
tests
```

Do not disable linting or formatting rules simply to make code pass.

If a rule genuinely needs to be changed, update the project configuration deliberately.

---

# 22. Comments
Prefer clear code over excessive comments.

Bad:

```python
# This variable stores the ticket token
ticket_token = token
```

Good:

```python
# The lock prevents two scanners from successfully consuming the same ticket.
ticket = Ticket.objects.select_for_update().get(token=token)
```

Comments should explain:

- Why something is necessary
- Non-obvious business rules
- Concurrency considerations
- Security considerations
- External limitations

Do not comment obvious code.

---

# 23. TODO Comments
Do not leave vague TODOs.

Bad:

```python
# TODO: fix this
```

Better:

```python
# TODO: Replace temporary dashboard pagination once the reporting endpoint is available.
```

If a TODO represents important future work, it should be specific enough for another developer to understand.

---

# 24. Error Handling
Never silently ignore important errors.

Bad:

```typescript
try {
  await scanTicket(token);
} catch {
  // ignore
}
```

Errors should produce an appropriate user-facing state and useful diagnostic information where appropriate.

Do not expose:

- Stack traces
- Database errors
- Internal paths
- Secret configuration
- Internal implementation details

to normal users.

---

# 25. Scanner UI Error Handling
The scanner must clearly distinguish between:

```text
ENTRY GRANTED
ALREADY USED
INVALID TICKET
CANCELLED TICKET
WRONG EVENT
EVENT CLOSED
NETWORK ERROR
UNAUTHORIZED
```

A network error must never be interpreted as:

```text
ENTRY GRANTED
```

The frontend must display the actual server result.

---

# 26. Forms
Forms should:

- Validate user input
- Display clear validation messages
- Prevent accidental duplicate submissions
- Show loading states
- Handle server-side validation errors
- Preserve entered values where appropriate

Client-side validation improves UX.

Server-side validation remains authoritative.

---

# 27. Loading States
Every important asynchronous operation should have an appropriate loading state.

Examples:

```text
Submitting registration...
Generating ticket...
Loading event...
Validating ticket...
Recording entry...
```

Avoid interfaces that appear frozen during API requests.

---

# 28. Duplicate Submission Prevention
Important operations such as registration and ticket scanning must prevent accidental repeated requests from the UI.

Examples:

```text
Submit Registration
        ↓
Disable button
        ↓
Request
        ↓
Receive response
        ↓
Re-enable / navigate
```

However, frontend prevention is not a replacement for backend idempotency and database constraints.

---

# 29. Security-Sensitive Code
Never:

- Trust a role sent by the frontend
- Trust ticket status sent by the frontend
- Allow the client to mark a ticket as used
- Store secrets in source code
- Log authentication tokens
- Log complete sensitive credentials
- Bypass authorization for convenience
- Disable security checks to make development easier

Security rules defined in `SECURITY.md` take precedence over UI convenience.

---

# 30. QR Code Handling
The QR code should contain an opaque ticket identifier/token.

Do not expose unnecessary personal information inside the QR code.

The scanner should:

```text
Camera
↓
Decode QR
↓
Extract token
↓
Send token to backend
↓
Display backend result
```

The scanner frontend must not decide whether a ticket is valid.

---

# 31. Database Access
Use Django ORM for application database access.

Do not build raw SQL queries unless there is a clear technical reason.

If raw SQL is necessary:

- Parameterize inputs
- Review it carefully
- Document why it is necessary
- Test it

Never concatenate user input into SQL.

---

# 32. Migrations
Database schema changes must use Django migrations.

Do not manually modify production database tables.

Typical workflow:

```text
python manage.py makemigrations
python manage.py migrate
```

Migration files should be committed to version control.

---

# 33. Testing Style
Tests should focus on actual business behavior.

Important cases include:

### Registration

- Valid online registration
- Valid on-spot registration
- Invalid registration data
- Duplicate registration where prohibited
- Unauthorized on-spot registration

### Ticket

- Ticket creation
- Ticket cancellation
- Invalid token
- Wrong event
- Used ticket

### Scanning

- Valid ticket
- First successful scan
- Duplicate scan
- Concurrent scans
- Cancelled ticket
- Wrong event
- Unauthorized staff
- Event closed
- Network/API failure handling

---

# 34. Test Naming
Test names should explain the expected behavior.

Good:

```python
def test_used_ticket_is_rejected():
    ...
```

```python
def test_concurrent_scan_allows_only_one_entry():
    ...
```

Avoid:

```python
def test_ticket_1():
    ...
```

---

# 35. Reusable Components
Create reusable components when the same UI pattern appears multiple times.

Examples:

```text
Button
Input
Modal
Table
Badge
Alert
LoadingSpinner
EmptyState
TicketCard
StatusIndicator
```

Do not create an abstraction merely because two pieces of code look slightly similar.

---

# 36. Avoid Premature Abstraction
Do not build a generic framework inside the project.

Avoid:

```text
GenericUniversalFormEngine
UniversalApiManager
DynamicEverythingComponent
```

unless there is a genuine repeated requirement.

Prefer simple, understandable code.

---

# 37. Dependencies
Before adding a package:

1. Check whether the project already has a suitable dependency.
2. Check whether the feature can be implemented using the existing stack.
3. Consider maintenance and security implications.
4. Add the dependency only when it provides meaningful value.

Do not install packages simply because an AI-generated solution commonly uses them.

---

# 38. Environment Configuration
Configuration that changes between environments should come from environment variables.

Examples:

```text
DATABASE_URL
SECRET_KEY
DEBUG
ALLOWED_HOSTS
CORS_ALLOWED_ORIGINS
```

Never commit actual production credentials.

Use example configuration files when necessary:

```text
.env.example
```

---

# 39. Git Practices
Commits should be focused and descriptive.

Good:

```text
feat: add on-spot registration flow
fix: prevent duplicate ticket entry
feat: add QR scanner
fix: reject cancelled tickets
```

Avoid:

```text
update
changes
final
final2
new
```

Do not commit:

```text
.env
secrets
passwords
API keys
large generated files
temporary debug files
```

unless explicitly required and safe.

---

# 40. Logging
Logs should provide useful operational information without exposing sensitive data.

Good:

```text
Ticket scan failed: ticket not found
```

Avoid:

```text
User password: ...
JWT token: ...
Full authentication header: ...
```

For important operational events, use the project's audit logging mechanism.

---

# 41. Debugging
Temporary debugging code must not be committed.

Remove:

```text
print(...)
```

```text
console.log(...)
```

and other temporary debugging statements unless they are intentionally part of the project's logging strategy.

---

# 42. AI Coding Agent Rules
AI coding agents working on this project must:

1. Read the relevant documentation before making changes.
2. Follow existing project conventions.
3. Inspect existing code before creating new abstractions.
4. Reuse existing components and utilities when appropriate.
5. Avoid inventing new database models without a requirement.
6. Avoid inventing new API conventions.
7. Avoid introducing unnecessary dependencies.
8. Never bypass authorization.
9. Never move security-critical validation to the frontend.
10. Never implement ticket scanning as an unsafe read-then-write operation.
11. Preserve database constraints.
12. Add or update tests for important behavior.
13. Keep changes focused.
14. Update documentation when stable project conventions change.

---

# 43. Files to Read Before Major Changes
For major implementation work, AI agents should consult:

```text
docs/PRD.md
docs/AGENTS.md
docs/DESIGN_SYSTEM.md
docs/ARCHITECTURE.md
docs/SECURITY.md
docs/CODE_STYLE.md
docs/DATABASE.md
docs/API.md
```

The relevant documents should be read before changing the corresponding area.

Examples:

```text
UI change
→ DESIGN_SYSTEM.md
→ CODE_STYLE.md

Database change
→ DATABASE.md
→ ARCHITECTURE.md
→ SECURITY.md

API change
→ API.md
→ SECURITY.md
→ ARCHITECTURE.md

Authentication/security change
→ SECURITY.md
→ ARCHITECTURE.md

Ticket scanning change
→ ARCHITECTURE.md
→ SECURITY.md
→ API.md
→ DATABASE.md
```

---

# 44. Rule Priority
When conventions conflict, use this priority:

1. Security requirements
2. Database integrity requirements
3. Backend business rules
4. Existing project architecture
5. Existing project conventions
6. Code style preferences

Do not sacrifice security or data integrity for convenience or stylistic consistency.

---

# 45. Final Principle
Write code that another developer can understand without needing to ask the original author what it does.

Prefer:

```text
simple
explicit
typed
tested
secure
maintainable
```

over:

```text
clever
over-abstracted
duplicated
implicit
fragile
```

The objective is not to write the smallest amount of code.

The objective is to build a reliable event ticketing system that remains understandable and safe as the number of events, attendees, staff members, and concurrent scanners increases.
