# Event Ticketing & Registration Platform

## 1. Product Overview

The Event Ticketing & Registration Platform is a web-based system designed to manage the complete event registration and entry process from registration to gate validation.

The system supports two registration channels:

1. Online Registration
2. On-Spot Registration

Both registration channels use the same underlying registration and ticket system.

Each successful registration/order generates one or more unique tickets according to its selected offer. Every ticket has its own unique QR code. At the event venue, authorized staff can scan each ticket independently at multiple gates and validate entry in real time.

The system must support multiple scanners operating simultaneously without allowing the same ticket to be accepted more than once.

The platform also provides administrators with visibility into registrations, tickets, attendance, scan attempts, gates, and operational activity.

---

# 2. Problem Statement

Traditional event registration and manual ticket verification create several operational problems.

### Current problems

- Online and on-spot registrations may be managed separately.
- Manual ticket verification is slow.
- Staff may not know whether a ticket has already been used.
- The same ticket may accidentally be accepted multiple times.
- Multiple gates create a risk of duplicate entry when several staff members scan tickets simultaneously.
- Organizers have limited real-time visibility into attendance.
- Tracking the complete history of a ticket is difficult.
- Manual registration at the venue can create queues.
- Searching for attendee or ticket information during an event is difficult.
- Spreadsheet-based systems do not provide reliable concurrent ticket validation.

The system must provide a single source of truth for registrations, tickets, and entry validation.

---

# 3. Product Goals

## 3.1 Primary Goals

The platform must:

1. Support online registration.
2. Support on-spot registration.
3. Generate one or more unique tickets for every successful registration/order according to its selected ticket offer.
4. Generate a unique QR code/token for every ticket.
5. Allow multiple staff members to scan tickets simultaneously.
6. Prevent duplicate entry.
7. Track every important ticket and scan event.
8. Provide real-time attendance information.
9. Provide an administrative dashboard.
10. Provide secure role-based access.
11. Maintain a reliable audit trail.
12. Work effectively during high-pressure event operations.

---

# 4. Users and Roles

The system has three primary staff roles.

## 4.1 Admin / Event Organizer

The Admin has full access to event operations.

### Permissions

- Create events.
- Edit events.
- Configure event details.
- View registrations.
- View tickets.
- Search attendees.
- View attendance.
- View scan history.
- Manage staff.
- Manage scanner access.
- Cancel tickets.
- View reports.
- View audit logs.

---

## 4.2 Registration Staff

Registration Staff are responsible for attendee registration, particularly on the event day.

### Permissions

- Access on-spot registration.
- Create attendee registrations.
- Generate tickets.
- Search registrations.
- Search tickets.
- View relevant attendee information.
- Print/display tickets.

Registration staff must not be able to:

- Manage administrators.
- Manage scanner permissions.
- Modify event security settings.
- Bypass ticket validation.
- Mark tickets as used manually unless a specific authorized administrative workflow exists.

---

## 4.3 Scanner / Gate Staff

Scanner Staff are responsible for validating tickets at the event entrance.

### Permissions

- Login.
- Select/access assigned event.
- Select/access assigned gate where applicable.
- Open QR scanner.
- Scan tickets.
- View validation results.
- View limited recent scan history.

Scanner Staff must not be able to:

- Create tickets.
- Modify attendee information.
- Cancel tickets.
- Change ticket status manually.
- Modify event configuration.
- Bypass server-side validation.

---

# 5. Registration Types

The system supports two registration sources.

```text
ONLINE
ON_SPOT
```

---

# 6. Registration Orders and Tickets

One registration represents one buyer/order and may contain one or more admissions. Buyer/contact details are stored on the registration and are not redundantly copied to every ticket. Each ticket has an independent ID, opaque QR token, status, and scan history. A registration-to-ticket relationship is one-to-many, not one-to-one.

The Dhandiya Night offers currently configured in the product UI are:

- Single Ticket: one admission for ₹149, with an additional ₹4 per-admission charge collected in Razorpay (₹153 charged).
- Combo Offer: five paid admissions plus one included admission, for six independently scannable tickets at ₹745, with an additional ₹4 per admission collected in Razorpay (₹769 charged).

Event capacity is consumed per admission/ticket, so a combo consumes six places. The buyer/contact may be shared by the order. A combo registration requires all six attendee names: the buyer's name is the first attendee name, and five additional attendee names are required. Buyer email and phone are collected once and shared across the order. Each generated ticket carries its own attendee name.

---

# 7. Duplicate Registration Policy

Multiple registrations may use the same email address or phone number. Do not impose a unique email/phone constraint or automatically reject a registration because contact details match another order. An administrative duplicate warning/report may be considered separately, but its criteria are not yet defined and it must not automatically block registration.

---

# 8. Ticket Lifecycle and Cancellation

Allowed ticket transitions are:

```text
ISSUED -> USED       after successful entry
ISSUED -> CANCELLED  through authorized cancellation
```

`USED` and `CANCELLED` are terminal. A used ticket remains historically used and must not be reset to issued or relabelled cancelled. Tickets within the same registration are independently scannable and may be individually cancelled without changing their siblings. Whole-order cancellation and exceptional handling of already-used tickets remain unresolved; any later exception must preserve ticket and scan history.

---

# 9. Payment and Tax

The registration page displays ticket offer prices in INR: ₹149 for one admission and ₹745 for the six-admission combo. Razorpay collects an additional fixed ₹4 per admission, included in the order total (₹153 single; ₹769 combo) and not shown on the registration page. The application integrates Razorpay TEST/SANDBOX orders with persisted idempotency and backend verification. Online tickets are issued only after the provider confirms a captured payment with matching order, amount, and currency. Payment/order state, registration state, and each ticket's admission state are distinct.

Live Razorpay verification and settlement are deferred pending organization merchant/bank credentials. Tax applicability and calculation remain undefined. Sandbox validation is not production-readiness evidence.

---

# 10. Demo Data and Canonical Event

Existing browser-local and mock registrations, tickets, scans, and staff users are disposable demo data and must not be migrated into production. Production starts clean, with only explicitly approved event/ticket-offer seed data.

The canonical production Dhandiya Night 2026 event identity is UUID `8b3f7a20-6e8d-4b91-a462-9c5d2f1e7043`, with slug `dhandiya-night-2026`. The frontend obtains this identity from the backend event API. The demo ID `evt-technova-2026` is not a production identity.

---

# 11. Unresolved Product Decisions

- Live payment configuration, trusted webhook policy, and settlement behavior. Refunds and settlement reversals are not supported by the application.
- Whether an event-level payment-required setting is needed for future events.
- Tax applicability and calculation for single and combo offers.
- Whole-order cancellation and combo cancellation rules, particularly if any ticket has already been used.
- Whether administrators need a non-blocking duplicate-registration warning/report and its matching criteria.
