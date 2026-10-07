# AGENTS.md

# AI Coding Agent Instructions
## Event Ticketing & Registration Platform

This file defines the rules that AI coding agents must follow when working on this project.

The agent must treat the project documentation as persistent project context and must follow the documented architecture, security rules, database rules, API conventions, and design system.

---

# 1. Project Mission

Build and maintain the **Event Ticketing & Registration Platform** described in:

```text
docs/PRD.md
```

The platform supports:

- Online registration
- On-spot registration
- Ticket generation
- QR-code-based ticket validation
- Multiple simultaneous scanners
- Duplicate-entry prevention
- Gate tracking
- Attendance tracking
- Admin dashboard
- Staff roles and permissions
- Ticket and scan history

The system must prioritize correctness, security, reliability, and operational simplicity.

---

# 2. Mandatory Documentation
Before making changes, read the documentation relevant to the requested task.

## For backend/database/security/API work
Read:

```
docs/PRD.md
docs/ARCHITECTURE.md
docs/SECURITY.md
docs/DATABASE.md
docs/API.md
docs/CODE_STYLE.md
```

## For frontend/UI work
Read:

```
docs/PRD.md
docs/DESIGN_SYSTEM.md
docs/CODE_STYLE.md
```

## For database changes
Read:

```
docs/PRD.md
docs/DATABASE.md
docs/SECURITY.md
```

## For API changes
Read:

```
docs/PRD.md
docs/API.md
docs/SECURITY.md
```

## For scanner/ticket validation changes
Read:

```
docs/PRD.md
docs/ARCHITECTURE.md
docs/DATABASE.md
docs/API.md
docs/SECURITY.md
```

Do not implement security-sensitive or database-sensitive features without reading the relevant documentation first.

---

# 3. Source of Truth
The project has multiple sources of truth.

## Product requirements

```
docs/PRD.md
```

Defines what the product must do.

## Architecture

```
docs/ARCHITECTURE.md
```

Defines how the system should be structured.

## Security

```
docs/SECURITY.md
```

Defines how users, tickets, data, credentials, and protected operations must be secured.

## Database

```
docs/DATABASE.md
```

Defines how data is modeled and how critical database operations must be performed safely.

## API

```
docs/API.md
```

Defines API conventions and endpoint behavior.

## UI

```
docs/DESIGN_SYSTEM.md
```

Defines interface and interaction conventions.

## Code conventions

```
docs/CODE_STYLE.md
```

Defines implementation conventions.

---

# 4. Never Invent Project Conventions
Do not invent:

- new authentication systems,
- new database technologies,
- new API conventions,
- new ticket states,
- new user roles,
- new architectural patterns,
- new dependencies,
- new infrastructure,

unless the requirement genuinely requires them.

Before introducing a new technology, determine whether the existing stack can solve the problem.

Prefer the simplest solution that satisfies the requirement.

---

# 5. Existing Architecture
The planned architecture is:

```
React Frontend
       |
       | HTTPS / JSON API
       |
       v
Django + Django REST Framework
       |
       v
PostgreSQL
```

The application should initially remain a modular monolith.

Do not introduce microservices simply because the system has multiple scanners.

Three or four simultaneous scanners are not, by themselves, a reason to introduce:

- microservices,
- Redis,
- message queues,
- Kafka,
- Kubernetes,
- multiple databases.

Any such architectural change requires a documented reason.

---

# 6. Critical Business Rule: Ticket Validation
Ticket validation is one of the most important operations in the system.

The backend is the authority.

The frontend must never decide whether a ticket is valid.

The agent must never implement ticket validation as:

```
Fetch ticket
↓
Check status
↓
Do other work
↓
Update ticket
```

This creates a race condition.

Instead, the operation must be transactional.

Conceptually:

```
BEGIN TRANSACTION

Lock ticket

Check ticket status

Check event

If ticket is cancelled:
    reject

If ticket is already used:
    reject

If ticket belongs to another event:
    reject

Create successful entry

Mark ticket as USED

COMMIT
```

Use PostgreSQL transaction guarantees and Django transaction handling.

---

# 7. Duplicate Entry Protection
This rule is mandatory.

If:

```
Scanner A → Ticket TKT-001
Scanner B → Ticket TKT-001
```

arrive at nearly the same time, only one request may receive:

```
ENTRY_GRANTED
```

The other request must receive an appropriate rejection such as:

```
TICKET_ALREADY_USED
```

The exact order is not important.

The invariant is:

```
ONE TICKET
      ↓
MAXIMUM ONE SUCCESSFUL ENTRY
```

Never weaken this rule to make a test, demo, or UI flow work.

---

# 8. Database Is the Final Authority
Do not use frontend state as the source of truth for:

- ticket status,
- attendance,
- registration ownership,
- user roles,
- permissions,
- successful entry.

The database and backend determine the actual state.

Examples of incorrect logic:

```
if (!ticket.isUsed) {
    allowEntry();
}
```

or:

```
ticket.status = "USED";
```

on the frontend.

The frontend should request validation from the backend and display the result.

---

# 9. Online and On-Spot Registration
Online and on-spot registrations must use the same registration and ticket system.

Online:

```
source = ONLINE
```

On-spot:

```
source = ON_SPOT
```

Do not create a completely separate ticket system for on-spot registration.

Both types must produce tickets that can be scanned by the same gate scanner.

---

# 10. Scanner Rules
The scanner frontend is responsible for:

- Camera access
- QR decoding
- Sending the token to the API
- Displaying the server response

The scanner frontend is NOT responsible for:

- deciding ticket validity,
- marking a ticket as used,
- bypassing validation,
- determining staff permissions,
- deciding whether a duplicate scan is acceptable.

The correct flow is:

```
Camera
  ↓
QR Token
  ↓
Backend API
  ↓
Server Validation
  ↓
Database Transaction
  ↓
Result
  ↓
Scanner UI
```

---

# 11. Scanner Failure Rules
If the backend cannot confirm the ticket because of a network/server failure:

Do NOT show:

```
ENTRY GRANTED
```

Instead show something similar to:

```
VALIDATION FAILED
CHECK NETWORK CONNECTION
```

A ticket is considered successfully validated only after the backend confirms it.

---

# 12. Security Rules
Never:

- hardcode passwords,
- hardcode API keys,
- commit `.env`,
- expose server secrets,
- disable authentication,
- bypass authorization,
- trust client-provided roles,
- trust client-provided ticket status,
- expose stack traces,
- expose database credentials.

Follow:

```
docs/SECURITY.md
```

for all security-sensitive work.

---

# 13. Authentication and Authorization
The backend must determine:

```
Who is the user?
What role does the user have?
What is the user allowed to do?
```

Never trust role information sent by the frontend.

For example, this is unsafe:

```
{
  "role": "ADMIN"
}
```

if the server simply trusts it.

Authorization must be performed using the authenticated server-side identity.

---

# 14. Role Rules
The main roles are:

```
ADMIN
REGISTRATION_STAFF
SCANNER_STAFF
```

### ADMIN
Can perform administrative operations.

### REGISTRATION_STAFF
Can create on-spot registrations and perform permitted registration operations.

### SCANNER_STAFF
Can validate tickets but cannot create, cancel, or modify tickets.

Do not give every authenticated user administrator permissions.

---

# 15. API Rules
Before changing or creating an API endpoint:

Read:

```
docs/API.md
docs/SECURITY.md
```

Follow the existing:

- URL structure
- authentication requirements
- authorization rules
- response format
- error format
- HTTP status conventions

Validate all input on the server.

Never expose internal exceptions.

---

# 16. Database Rules
Before changing models:

Read:

```
docs/DATABASE.md
```

Database changes must:

1. Modify the model.
2. Create a migration.
3. Review the migration.
4. Test the migration.
5. Verify existing data is preserved.
6. Apply it through the normal deployment process.

Never modify production tables manually just to bypass a migration.

Never run destructive database reset commands against production.

---

# 17. Database Constraints
Use database constraints for critical invariants.

Important examples:

```
Ticket number → UNIQUE

QR token → UNIQUE

Successful entry per ticket → UNIQUE
```

Application logic alone should not be the only protection for critical invariants.

---

# 18. Transaction Rules
Use database transactions when multiple operations must succeed or fail together.

Examples:

### Creating registration + ticket

```
Create registration
+
Create ticket
+
Generate ticket identity
```

These operations should not leave the database in an invalid partial state.

### Validating entry

```
Validate ticket
+
Create successful entry
+
Mark ticket used
```

These operations must be atomic.

---

# 19. Frontend Rules
Read:

```
docs/DESIGN_SYSTEM.md
docs/CODE_STYLE.md
```

before significant UI work.

Reuse existing components.

Do not create duplicate components when a reusable component already exists.

Every data-driven screen should handle:

```
Loading
Success
Empty
Error
```

Do not leave blank screens during loading or failures.

---

# 20. Scanner UX
The scanner must prioritize speed.

A scanner operator should be able to:

```
Open scanner
↓
Point camera
↓
Receive result
↓
Scan next ticket
```

Avoid unnecessary confirmation dialogs between scans.

Successful and failed scans must be immediately distinguishable.

---

# 21. Error Handling
Errors shown to users must be:

- clear,
- actionable,
- safe.

Do not expose:

- SQL errors,
- stack traces,
- filesystem paths,
- credentials,
- internal exception messages.

Bad:

```
IntegrityError: duplicate key value violates unique constraint...
```

Better:

```
This ticket has already been used.
```

Detailed diagnostic information belongs in controlled server-side logs.

---

# 22. Logging
Logging must help diagnose production issues without exposing sensitive information.

Do not log:

- passwords,
- authentication tokens,
- authorization headers,
- API keys,
- database credentials,
- unnecessary personal data,
- raw QR tokens unless explicitly required and protected.

Useful logging includes:

```
scan request failed
event ID
ticket internal ID where safe
scanner user ID
gate
error category
timestamp
```

Follow the project's privacy/security rules.

---

# 23. Testing Requirements
Before declaring a feature complete, test the actual behavior.

At minimum, ticket scanning must test:

### Valid ticket

```
Unused ticket
→ ENTRY_GRANTED
```

### Duplicate ticket

```
First scan
→ ENTRY_GRANTED

Second scan
→ ALREADY_USED
```

### Concurrent scan
Send two simultaneous requests for the same ticket.

Expected:

```
Request A → ENTRY_GRANTED
Request B → ALREADY_USED
```

Never:

```
Request A → ENTRY_GRANTED
Request B → ENTRY_GRANTED
```

### Cancelled ticket

```
CANCELLED
→ REJECTED
```

### Wrong event

```
Event A ticket
+
Event B scanner
→ REJECTED
```

### Unauthorized scanner

```
Unauthorized user
→ 401/403
```

### On-spot registration

```
Registration
→ source = ON_SPOT
→ ticket created
→ QR generated
→ ticket can be scanned
```

---

# 24. Test the Backend, Not Just the UI
A green UI test is not enough for ticket validation.

The critical duplicate-entry tests must execute against the backend/database behavior.

For concurrency-sensitive code, test the actual transaction behavior.

The following is NOT sufficient:

```
Click scanner twice
```

The system must also be tested with simultaneous backend requests.

---

# 25. Do Not Hide Bugs
Never:

- catch an exception and ignore it,
- return success when the operation failed,
- disable validation to make a demo work,
- remove tests because they fail,
- change expected behavior just to make tests green,
- hide database errors.

If a test exposes a real architectural problem, fix the problem.

---

# 26. Dependency Rules
Do not add a dependency merely because it is convenient.

Before adding a package, determine:

1. Does the existing stack already provide the functionality?
2. Is the dependency maintained?
3. Does it increase security risk?
4. Does it increase deployment complexity?
5. Is it actually required?

Prefer existing project dependencies.

---

# 27. File and Code Discipline
Do not:

- reformat unrelated files,
- rename unrelated modules,
- rewrite working code unnecessarily,
- change architecture during a small feature,
- introduce unrelated refactoring,
- delete existing functionality without a requirement.

Keep changes focused.

---

# 28. Documentation Synchronization
If implementation changes a stable project convention, update the relevant documentation.

Examples:

If database structure changes:

```
docs/DATABASE.md
```

If API behavior changes:

```
docs/API.md
```

If architecture changes:

```
docs/ARCHITECTURE.md
```

If security rules change:

```
docs/SECURITY.md
```

If UI conventions change:

```
docs/DESIGN_SYSTEM.md
```

Do not allow documentation to describe a system that no longer exists.

---

# 29. Handling Documentation Conflicts
If documentation says one thing but the existing code does another:

Do NOT silently choose one.

Instead:

1. Identify the conflict.
2. Determine which behavior is currently implemented.
3. Determine whether the requested feature depends on changing it.
4. Explain the impact.
5. Make the smallest safe change.
6. Update the documentation if the new behavior is intentional.

---

# 30. Before Implementing a Feature
Follow this process:

```
1. Read relevant documentation
        ↓
2. Inspect existing code
        ↓
3. Identify affected modules
        ↓
4. Identify affected database models
        ↓
5. Identify affected APIs
        ↓
6. Identify security/authorization impact
        ↓
7. Identify tests required
        ↓
8. Implement
        ↓
9. Test
        ↓
10. Update documentation if required
```

Do not jump directly from a user request to writing code.

---

# 31. Before Changing the Database
Answer:

```
Which model changes?

Which relationships change?

Which constraints change?

Does this require a migration?

Could existing data break?

Does this affect ticket uniqueness?

Does this affect concurrent scanning?

Does this affect authorization?
```

Then implement.

---

# 32. Before Adding an API
Answer:

```
Who can call this endpoint?

What input does it accept?

How is the input validated?

What database records does it modify?

Does it require a transaction?

What could happen if two requests arrive simultaneously?

What response does it return?

What errors can occur?

Does the endpoint expose sensitive information?
```

Then implement.

---

# 33. Before Changing Scanner Logic
Answer:

```
Can two scanners call this endpoint simultaneously?

Can the same ticket be accepted twice?

Is the database transaction safe?

Can a cancelled ticket enter?

Can a ticket from another event enter?

Can an unauthorized user call the endpoint?

What happens if the network fails?

What happens if the scanner sends the same request twice?
```

If any answer is unclear, investigate before implementing.

---

# 34. Definition of Done
A feature is NOT complete simply because it appears to work in the browser.

A feature is complete when:

- Requirements are satisfied.
- Backend logic is correct.
- Database constraints are correct.
- Authorization is correct.
- Security rules are followed.
- Errors are handled.
- Tests pass.
- Important edge cases are tested.
- Concurrency-sensitive operations are tested.
- UI loading/error/empty states are handled.
- Documentation remains accurate.
- Debugging code is removed.

---

# 35. Final Principle
The project must prefer:

```
Simple
+
Reliable
+
Secure
+
Testable
```

over:

```
Complex
+
Over-engineered
+
Fast-to-demo
+
Fragile
```

For event-day software, correctness matters more than cleverness.

A scanner that looks excellent but can allow the same ticket through two gates is a failed implementation.

The backend and PostgreSQL database must remain the authoritative source of truth for ticket validity and attendance.
