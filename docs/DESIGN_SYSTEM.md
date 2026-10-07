# DESIGN_SYSTEM.md

# Event Ticketing & Registration Platform
## Design System & UX Guidelines

This document defines the visual, interaction, and usability standards for the Event Ticketing & Registration Platform.

The design system must support two very different environments:

1. Public attendee experience
2. Event operations experience

The system should prioritize **clarity, speed, accessibility, and operational reliability** over unnecessary visual complexity.

---

# 1. Design Philosophy

The product should feel:

- Professional
- Modern
- Trustworthy
- Fast
- Simple
- Operational
- Easy to understand

The interface must not become visually complicated just to look impressive.

For event-day operations:

```text
Correctness
    ↓
Speed
    ↓
Clarity
    ↓
Accessibility
    ↓
Visual polish
```

A beautiful interface that slows down registration or ticket scanning is a bad interface.

---

# 2. User Interfaces
The product has three major interface contexts.

## 2.1 Public Attendee Interface
Used by attendees for:

- Viewing event information
- Online registration
- Registration confirmation
- Viewing tickets
- Viewing QR codes

The public interface should be:

- Mobile-first
- Simple
- Trustworthy
- Easy to navigate
- Optimized for quick completion

---

## 2.2 Staff Operations Interface
Used by:

- Registration staff
- Scanner staff

This interface must prioritize operational speed.

Important actions should require as few interactions as possible.

---

## 2.3 Admin Interface
Used by event organizers.

The admin interface can contain more information because administrators need:

- Tables
- Filters
- Statistics
- Reports
- Management controls
- Audit information

However, information must still be structured clearly.

---

# 3. Main Screens
The application should contain the following major screens.

## Public Screens

```
Event Landing Page
Registration Page
Registration Confirmation
Ticket Page
QR Ticket View
```

## Staff Screens

```
Staff Login
Staff Dashboard
On-Spot Registration
Ticket Search
Ticket Details
QR Scanner
Scan Result
Recent Scans
```

## Admin Screens

```
Admin Login
Admin Dashboard
Event Management
Registration Management
Ticket Management
Staff Management
Scan History
Audit Logs
Reports
```

---

# 4. Navigation
Navigation should be role-aware.

Users should only see navigation items they are authorized to access.

Example:

### Admin

```
Dashboard
Events
Registrations
Tickets
Scanners
Scan History
Reports
Settings
```

### Registration Staff

```
Dashboard
On-Spot Registration
Registrations
Tickets
```

### Scanner Staff

```
Scanner
Recent Scans
```

Do not expose unauthorized administrative navigation merely to hide it later.

Authorization must still be enforced by the backend.

---

# 5. Visual Hierarchy
Every screen should have a clear hierarchy.

Recommended structure:

```
Page Title
    ↓
Page Description / Context
    ↓
Primary Action
    ↓
Main Content
    ↓
Secondary Information
```

Primary actions should be visually distinct.

Secondary actions should not compete with the primary action.

Destructive actions such as ticket cancellation should require appropriate confirmation.

---

# 6. Typography
Use a clean, readable sans-serif font.

Typography should have a consistent hierarchy.

Recommended levels:

```
Display / Event Title
Page Heading
Section Heading
Card Heading
Body Text
Helper Text
Caption
Status Text
```

Scanner status messages should use large, highly readable text.

Example:

```
ENTRY GRANTED
```

should be significantly more prominent than secondary ticket information.

---

# 7. Color System
Use semantic colors consistently.

## Success
Used for:

- Entry granted
- Successful registration
- Successful ticket generation
- Successful operations

Semantic meaning:

```
SUCCESS
```

---

## Warning
Used for:

- Approaching limits
- Non-critical warnings
- Pending actions

Semantic meaning:

```
WARNING
```

---

## Error
Used for:

- Invalid ticket
- Cancelled ticket
- Failed request
- Validation errors

Semantic meaning:

```
ERROR
```

---

## Neutral
Used for:

- Informational content
- Inactive states
- Secondary information

---

## Important Rule
Never communicate status through color alone.

For example, do not show only:

```
GREEN
```

Instead show:

```
✓ ENTRY GRANTED
```

Likewise:

```
✕ TICKET ALREADY USED
```

The text/icon must communicate the meaning even if color cannot be perceived.

---

# 8. Buttons
Buttons should clearly communicate the action they perform.

Examples:

```
Register
Generate Ticket
Scan Ticket
Search Ticket
Save Changes
Cancel Ticket
```

Avoid vague labels such as:

```
Click Here
Submit
Proceed
Continue
```

when a more meaningful action name is possible.

---

# 9. Button Hierarchy
Use a consistent hierarchy.

### Primary
Main action on a screen.

Example:

```
Register Attendee
```

### Secondary
Supporting action.

Example:

```
View Ticket
```

### Destructive
Dangerous action.

Example:

```
Cancel Ticket
```

Destructive actions should not visually compete with the primary action.

---

# 10. Forms
Forms must contain:

- Clear labels
- Input fields
- Validation messages
- Loading states
- Error states
- Success states

Required fields must be clearly indicated.

Do not rely exclusively on placeholder text as a label.

---

# 11. Online Registration UX
The registration process should be straightforward.

Recommended flow:

```
Event Details
      ↓
Registration Form
      ↓
Review / Submit
      ↓
Registration Processing
      ↓
Success
      ↓
Ticket
```

If the registration form is short enough, avoid unnecessary multi-step navigation.

After successful registration, the attendee should immediately understand:

```
Registration Successful
```

and have an obvious way to access the ticket.

---

# 12. On-Spot Registration UX
On-spot registration is an operational workflow.

The interface should minimize typing and unnecessary navigation.

Recommended flow:

```
Open Registration
      ↓
Enter Attendee Details
      ↓
Register
      ↓
Ticket Generated
      ↓
Print / Display Ticket
      ↓
Register Next Attendee
```

The staff member should be able to quickly return to a blank registration form.

Do not force staff to navigate back through multiple screens after every registration.

---

# 13. Scanner UI
The scanner is one of the most important screens in the system.

It must be optimized for:

- Mobile devices
- Camera use
- Fast scanning
- Large status feedback
- Minimal interaction

Recommended structure:

```
Event Name
Gate / Scanner Information

┌─────────────────────────┐
│                         │
│      CAMERA VIEW        │
│                         │
│       QR TARGET         │
│                         │
└─────────────────────────┘

Point camera at QR code

-------------------------

LAST RESULT

ENTRY GRANTED
TKT-000123
10:32 AM
```

---

# 14. Scanner Interaction
Ideal scanner workflow:

```
Open Scanner
     ↓
Camera Active
     ↓
QR Detected
     ↓
API Request
     ↓
Server Validation
     ↓
Result Displayed
     ↓
Ready for Next Scan
```

The scanner should automatically return to scanning mode after displaying the result where appropriate.

Avoid requiring:

```
Scan
↓
Click Confirm
↓
Click Continue
↓
Scan Again
```

unless there is a strong operational reason.

---

# 15. Scanner Result States
The scanner must clearly communicate each result.

## Success

```
✓
ENTRY GRANTED

Ticket: TKT-000123
Attendee: Example Attendee
Gate: GATE-01
Time: 10:32 AM
```

---

## Already Used

```
✕
ALREADY USED

This ticket has already been validated.

First entry:
10:15 AM

Gate:
GATE-02
```

Only show information the current staff role is authorized to see.

---

## Invalid

```
✕
INVALID TICKET

This ticket could not be validated.
```

Do not expose internal database information.

---

## Cancelled

```
✕
TICKET CANCELLED

This ticket cannot be used for entry.
```

---

## Wrong Event

```
✕
WRONG EVENT

This ticket does not belong to this event.
```

---

## Network Error

```
!
VALIDATION FAILED

Unable to contact the server.
Check the network connection and try again.
```

Never display:

```
ENTRY GRANTED
```

when the server has not confirmed the operation.

---

# 16. Scanner Feedback
Scanner results should provide immediate feedback.

Possible feedback mechanisms:

- Large visual status
- Icon
- Text
- Optional sound
- Optional vibration where supported

Do not rely on sound alone.

The interface must remain understandable in noisy event environments.

---

# 17. Ticket Design
A ticket should clearly display:

```
EVENT NAME

Attendee Name

Ticket Number
TKT-000123

Date
Event Date

Time
Event Time

Venue
Event Venue

┌──────────────────┐
│                  │
│      QR CODE     │
│                  │
└──────────────────┘

Important Instructions
```

The QR code should be large enough to scan reliably.

Do not overcrowd the ticket with unnecessary information.

---

# 18. QR Code
The QR code must:

- Have sufficient size.
- Have sufficient contrast.
- Have adequate quiet space around it.
- Remain readable on mobile screens and printed tickets.
- Contain the appropriate opaque ticket token.

Do not put unnecessary attendee information directly inside the QR payload.

---

# 19. Ticket Status Badges
Use consistent status badges.

Possible states:

```
ISSUED
USED
CANCELLED
```

Example:

```
[ ISSUED ]
[ USED ]
[ CANCELLED ]
```

The visual treatment should remain consistent throughout:

- Ticket list
- Ticket details
- Dashboard
- Search results
- Registration records

---

# 20. Dashboard Design
The dashboard should provide immediate operational visibility.

Recommended top-level metrics:

```
┌─────────────┐
│ Registrations│
│    1,240     │
└─────────────┘

┌─────────────┐
│ Tickets Used │
│     842      │
└─────────────┘

┌─────────────┐
│ Unused       │
│     398      │
└─────────────┘

┌─────────────┐
│ On-Spot      │
│     215      │
└─────────────┘
```

The exact visual layout may change with the application implementation.

---

# 21. Registration vs Attendance
The dashboard must clearly distinguish:

```
REGISTRATIONS
```

from:

```
ATTENDANCE
```

For example:

```
Registered:
1,240

Entered:
842

Attendance:
67.9%
```

Do not label registrations as attendees unless the business definition explicitly supports that meaning.

---

# 22. Gate Statistics
Where useful, show gate activity.

Example:

```
GATE 1
320 entries

GATE 2
285 entries

GATE 3
237 entries
```

This can help organizers identify:

- Busy gates
- Underused gates
- Operational bottlenecks

---

# 23. Tables
Admin tables should prioritize readability.

Possible columns:

```
Ticket
Attendee
Registration Type
Status
Gate
Scanned At
Actions
```

Avoid putting every available database field into a table.

Use a details page or drawer for additional information.

---

# 24. Search
Search interfaces should clearly indicate what can be searched.

Example:

```
Search ticket number, attendee name, phone...
```

Search results should show the most useful information first.

Example:

```
TKT-000123
Rahul S
ON_SPOT
USED
GATE-02
```

---

# 25. Empty States
Every data-driven screen should have a meaningful empty state.

Bad:

```
Nothing
```

Better:

```
No registrations yet.

Registrations will appear here once attendees register.
```

For scan history:

```
No scan activity yet.

Successful and rejected scans will appear here.
```

---

# 26. Loading States
Never leave users looking at a blank page while data loads.

Use:

- Skeletons
- Loading indicators
- Disabled actions
- Progress feedback

For scanner validation, use a short processing state when necessary:

```
VALIDATING...
```

Do not make the UI appear frozen.

---

# 27. Error States
Errors should explain:

1. What happened.
2. What the user can do next.

Bad:

```
Error 500
```

Better:

```
Unable to load ticket information.

Please try again.
```

For scanner errors:

```
Unable to validate this ticket.

Check your network connection and scan again.
```

---

# 28. Confirmation Dialogs
Use confirmation dialogs for destructive actions.

Example:

```
Cancel Ticket?

This ticket will no longer be accepted at the event gate.

[Keep Ticket] [Cancel Ticket]
```

Do not use confirmation dialogs for routine scanning.

---

# 29. Responsive Design
The application must support:

- Mobile
- Tablet
- Desktop

## Public Registration
Mobile-first.

## Scanner
Mobile-first and optimized for portrait orientation where practical.

## Registration Desk
Tablet/desktop friendly.

## Admin Dashboard
Desktop/tablet optimized.

---

# 30. Accessibility
The application should use:

- Semantic HTML
- Proper labels
- Keyboard navigation
- Visible focus indicators
- Accessible buttons
- Accessible form errors
- Sufficient contrast
- Meaningful headings

Do not rely solely on color.

Camera errors and scanner results should also be communicated through accessible text.

---

# 31. Camera Permissions
The scanner must handle:

```
Camera Permission Granted
Camera Permission Denied
Camera Not Available
Camera In Use
Unsupported Browser
```

If camera scanning is unavailable and the product requirements permit it, provide a manual ticket-token entry fallback.

---

# 32. Mobile Scanner Considerations
The scanner should:

- Keep the camera view large.
- Avoid unnecessary scrolling.
- Keep critical controls reachable.
- Prevent accidental navigation during scanning.
- Clearly show the active event and gate.
- Provide a visible connection/validation state.

The scanner should be usable while staff are standing and moving through a gate operation.

---

# 33. Notifications and Toasts
Use notifications for:

- Successful operations
- Non-blocking warnings
- Background status changes

Do not use a toast as the only way to communicate a critical scanner result.

For ticket validation, the main scanner interface must display the result prominently.

---

# 34. Animation
Use animation sparingly.

Good uses:

- Loading transitions
- Status transitions
- Small feedback animations

Avoid:

- Long page transitions
- Decorative animations during scanning
- Animations that delay operations

Event staff should not have to wait for animations before scanning the next ticket.

---

# 35. Forms During Event Operations
Forms should optimize for speed.

After successful on-spot registration:

```
Ticket Created
     ↓
Print / Display
     ↓
New Registration
```

The staff member should be able to immediately register the next attendee.

---

# 36. Design Consistency
The following must remain consistent throughout the application:

- Typography
- Spacing
- Buttons
- Form controls
- Status badges
- Tables
- Cards
- Error messages
- Loading states
- Modal behavior
- Navigation

Do not create different versions of the same component without a strong reason.

---

# 37. Component Reuse
Prefer reusable components such as:

```
Button
Input
Select
Modal
Dialog
Table
Pagination
StatusBadge
TicketCard
QRCode
ScannerViewport
ScanResult
SearchInput
EmptyState
LoadingState
ErrorState
```

Before creating a new component, check whether an existing component can be reused.

---

# 38. Design System Rule
The design system should make the product easier to operate.

Do not optimize for:

```
"Looks impressive in a screenshot"
```

Optimize for:

```
"Works reliably when 1,000 people are waiting at the gate"
```

The scanner, registration desk, and ticket validation interfaces are operational tools.

Speed and clarity take priority over decorative design.

---

# 39. Final UX Principle
The best event interface is one that staff barely have to think about.

The intended operational flow should feel like:

```
REGISTER
   ↓
GET TICKET
   ↓
SCAN
   ↓
ENTRY GRANTED
   ↓
NEXT PERSON
```

Any unnecessary step should be questioned.

Any ambiguity around ticket status should be eliminated.

Any design decision that risks incorrect entry validation must be rejected in favor of correctness and clarity.
