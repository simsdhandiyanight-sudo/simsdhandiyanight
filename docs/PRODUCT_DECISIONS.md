# Product Decisions

This document records decisions needed to move the current Dhandiya Night demo toward the documented production ticketing system. Decisions here take precedence over older illustrative examples in the architecture, database, API, and PRD documents.

## 1. Registration/order and ticket model

**DECIDED**

- A `Registration` is the buyer's order/registration record. It belongs to one event and holds the buyer/contact details, registration source, and the selected ticket offer.
- One registration can contain one or more `Ticket` records. The relationship is one-to-many: `Registration 1 -> Ticket 1..N`.
- The buyer/contact details are stored once on the registration; they are not copied to every ticket.
- Every combo registration requires the name of each of its six attendees. The existing buyer name is the first attendee's name; five additional attendee names are collected. Buyer email and phone are collected once and shared across the order.
- Each ticket stores its own attendee name so its QR credential and gate scan identify the specific attendee. Ticket names do not duplicate buyer email or phone.
- Every ticket is an independent admission credential with its own stable ID, unique opaque QR token, status, and scan history. Tickets in the same order can be scanned independently.
- Capacity is measured in admissions/tickets, not orders. A combo consumes four admissions.
- One registration submission selects one ticket offer, consistent with the current registration UI. A single-ticket order contains one ticket; a combo order contains four.

**UNRESOLVED**


## 2. Combo ticket behavior

**DECIDED**

- The current configured offers are ₹149 for one admission and ₹745 for the six-admission combo. PayU checkout charges an additional fixed ₹4 per admission (₹153 for a single ticket and ₹769 for the combo); the additional charge is not shown on the registration page.
- The combo covers six admissions: five paid admissions and one included free admission. One buyer/contact may purchase/register the combo; the backend creates six independently scannable tickets under that registration.
- The combo consumes six units of event admission capacity. The offer itself is one purchasable package; package availability and admission capacity are distinct quantities.
- The buyer's registration is not a substitute for the six ticket credentials. Entry is validated per ticket.
- Combo registration is blocked unless all six attendee names are supplied; buyer email and phone remain single shared contact fields.

**UNRESOLVED**

- Whether taxes apply to the five paid admissions, the full combo amount, or another taxable base. No tax rate or tax calculation is defined.
- How partial cancellation of a combo should affect its included tickets or package availability.

## 3. Duplicate registration policy

**DECIDED**

- Multiple registrations using the same email address or phone number are allowed unless and until a separate business rule is approved.
- Do not add database uniqueness constraints on attendee/buyer email or phone, and do not automatically reject a registration because those details already appear on another registration.
- Registration ID, ticket ID, and opaque ticket token uniqueness are separate integrity requirements and remain enforced.

**UNRESOLVED**

- Whether administrators need a duplicate-registration warning or report, and which matching criteria it should use. Any such feature is advisory and must not automatically reject a registration without an approved rule.

## 4. Ticket lifecycle and cancellation

**DECIDED**

- Allowed ticket state transitions are `ISSUED -> USED` after a successful scan, or `ISSUED -> CANCELLED` through an authorized cancellation operation.
- `USED` and `CANCELLED` are terminal ticket states. A used ticket must never transition back to `ISSUED` or be rewritten as `CANCELLED`.
- Tickets in a multi-ticket registration have independent state. Cancelling one eligible ticket does not cancel its sibling tickets.
- A later administrative exception concerning a used ticket must preserve its historical `USED` state and scan record; it requires a separate auditable exception workflow if introduced.

**UNRESOLVED**

- Whether cancelling the entire registration/order should be supported as a separate operation, and how that operation should handle tickets that are already `USED`.

## 5. Payment and tax

**DECIDED**

- The ticket-offer prices shown in the product UI are ₹149 for one admission and ₹745 for the six-admission combo; the currency is INR. PayU collects an additional fixed ₹4 per admission, included in the order amount but not shown on the registration page.
- The PayU hosted checkout persists payment intents and payment attempts. Online tickets are issued only after backend response-hash validation and PayU Verify Payment API confirmation verifies a captured payment matching the stored transaction and booking details.
- Payment state, registration state, and individual ticket state are separate concepts. A browser callback cannot establish payment success or failure; ticket creation requires backend payment verification.
- A verified payment creates one registration, the corresponding tickets and QR tokens, and a retryable backend PDF/email delivery record.
- Payment verification is the only financial action supported by the application. Refunds and settlement reversals are not supported, and the application must never initiate them.
- If a provider-confirmed captured payment cannot be matched or its tickets cannot be issued, preserve the captured payment and audit details, mark it `ADMIN_REVIEW_REQUIRED`, and expose it to administrators for manual handling outside the application. Do not issue an automatic refund.
- Production payments require activated organization credentials and separate production configuration. Test-mode validation does not establish production readiness.
- The ₹4 per-admission charge is a fixed additional charge, not a percentage-based tax calculation. Tax applicability and treatment remain undecided.

**UNRESOLVED**

- Production payment methods and settlement behavior.
- Tax applicability, taxable base, rate, and receipt/invoice requirements for any applicable tax.
- Whether an event-level `payment_required` setting is needed for future free or differently-priced events.

## 6. Legacy demo-data policy

**DECIDED**

- Existing browser `localStorage`, mock registrations, mock tickets, and mock scans are disposable demo/development data. They are not production records and must not be migrated to PostgreSQL.
- Production starts with clean data and only explicitly approved event/tier seed data. Sample attendee registrations, tickets, staff credentials, and scans are not production seed data.
- The local `DataStore` may remain only in an explicitly isolated development/test path until the real API replacement is approved and implemented; it is not an authoritative production store.

## 7. Canonical Dhandiya Night identity

**DECIDED**

- The canonical production event slug is `dhandiya-night-2026`.
- The canonical event primary key is UUID `8b3f7a20-6e8d-4b91-a462-9c5d2f1e7043`.
- This stable identity replaces the frontend demo ID `evt-technova-2026`; that demo ID must not be used as the production event identity.
- The backend is the source of truth for the event. The frontend obtains the event and its canonical ID from the events API rather than hardcoding a demo ID.

## 8. Remaining decisions before production payment/ticket activation

The unresolved items above require product-owner and organization decisions before live payment processing or production release:

1. PayU merchant activation, production credentials, production callback/webhook configuration, verification, and settlement readiness.
2. Tax handling for the single and combo offers.
3. Whole-order cancellation behavior, including combos containing already-used tickets. Refunds remain unsupported.
5. Whether to show advisory duplicate-registration warnings.
