# Product Decisions

This document records decisions needed to move the current Dhandiya Night demo toward the documented production ticketing system. Decisions here take precedence over older illustrative examples in the architecture, database, API, and PRD documents.

## 1. Registration/order and ticket model

**DECIDED**

- A `Registration` is the buyer's order/registration record. It belongs to one event and holds the buyer/contact details, registration source, and the selected ticket offer.
- One registration can contain one or more `Ticket` records. The relationship is one-to-many: `Registration 1 -> Ticket 1..N`.
- The buyer/contact details are stored once on the registration; they are not copied to every ticket.
- Every ticket is an independent admission credential with its own stable ID, unique opaque QR token, status, and scan history. Tickets in the same order can be scanned independently.
- Capacity is measured in admissions/tickets, not orders. A combo consumes four admissions.
- One registration submission selects one ticket offer, consistent with the current registration UI. A single-ticket order contains one ticket; a combo order contains four.

**UNRESOLVED**

- Whether the buyer must provide a separate attendee name for every ticket, or whether tickets may initially be issued to bearer attendees without individual names.

## 2. Combo ticket behavior

**DECIDED**

- The current configured offers are one Single Ticket for ₹149 before applicable taxes, and one Combo Offer for ₹447 before applicable taxes.
- The combo covers four admissions: three paid admissions and one included free admission. One buyer/contact may purchase/register the combo; the backend creates four independently scannable tickets under that registration.
- The combo consumes four units of event admission capacity. The offer itself is one purchasable package; package availability and admission capacity are distinct quantities.
- The buyer's registration is not a substitute for the four ticket credentials. Entry is validated per ticket.

**UNRESOLVED**

- Whether taxes apply to the three paid admissions, the full combo amount, or another taxable base. No tax rate or tax calculation is defined.
- How partial cancellation/refund of a combo should affect its included tickets, package availability, or any future payment.

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

- The ticket-offer prices currently specified in the product UI are ₹149 for one admission and ₹447 for the four-admission combo, before applicable taxes; the currency is INR.
- These configured prices are offer information only until a payment workflow is approved and integrated. Registration creation must not be represented as payment success.
- Do not integrate a payment provider, create fabricated payment records, infer a `PAID` state, or calculate/display a tax amount without an approved provider, tax treatment, and rate.
- Registration/order state, ticket state, and payment state are separate concepts. Tickets remain independently scannable regardless of the buyer/order's payment metadata; production ticket issuance/activation must respect the payment rule once it is decided.
- A future payment integration must attach payment records/status to the registration/order and must not require redesigning the one-to-many ticket model.

**UNRESOLVED**

- Whether payment is required before a production registration is accepted and tickets are issued/activated, and which non-paid states are needed.
- Payment provider, payment methods, payment confirmation/webhook rules, refunds, and settlement behavior.
- Tax applicability, taxable base, rate, rounding, and receipt/invoice requirements.
- Whether an event-level `payment_required` setting is needed. The product is not declared free; the displayed prices do not by themselves define the production payment workflow.

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

The unresolved items above require product-owner decisions before implementing payment-dependent production behavior:

1. Whether and when payment is required before ticket issuance or activation.
2. Tax handling for the single and combo offers.
3. Attendee identity fields per ticket.
4. Whole-order cancellation/refund behavior, including combos containing already-used tickets.
5. Whether to show advisory duplicate-registration warnings.
