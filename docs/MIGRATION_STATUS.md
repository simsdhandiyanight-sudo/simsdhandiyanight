# Frontend Migration Status

**Last Updated:** 2026-10-18  
**Status:** ✅ **COMPLETE** - All public, staff, and admin pages migrated to backend APIs

## Summary

The frontend has been successfully migrated from local DataStore and mock data to a backend-driven architecture powered by Django REST APIs. All six main application pages now fetch event and operational data from the PostgreSQL-backed Django server.

## Completed Migrations

### Public Pages
- ✅ **LandingPage** (`client/src/pages/public/LandingPage.tsx`)
  - Uses `eventsApi.getById(FEATURED_EVENT_SLUG)` instead of mock FEATURED_EVENT_ID
  - Loads canonical event data from backend
  - Preserves all animation, poster, and reveal logic
  - Shows error state if event load fails

- ✅ **EventDetailPage** (`client/src/pages/public/EventDetailPage.tsx`)
  - Uses `FEATURED_EVENT_SLUG` to load event via backend API
  - Preserves FAQ, schedule, highlights rendering
  - Maintains loading and error UI patterns

- ✅ **RegistrationPage** (`client/src/pages/public/RegistrationPage.tsx`)
  - Loads event and available tiers from backend
  - Uses `registrationsApi.create()` for online registration
  - Preserves multi-step form logic and field validation
  - No mock registration data used

### Staff Pages
- ✅ **OnSpotRegistrationPage** (`client/src/pages/staff/OnSpotRegistrationPage.tsx`)
  - Loads active event from `eventsApi.getById(FEATURED_EVENT_SLUG)`
  - Uses `registrationsApi.create()` with `source: 'ON_SPOT'` 
  - No DataStore dependency
  - Generates and displays individual tickets for combo orders

- ✅ **StaffDashboardPage** (`client/src/pages/staff/StaffDashboardPage.tsx`)
  - Loads event via `eventsApi.getById(FEATURED_EVENT_SLUG)`
  - Uses `reportsApi.getEventReport()` for aggregated metrics
  - Uses `scansApi.getPage()` for recent scan history
  - Uses `ticketsApi.getPage()` for attendee lookup
  - Removed real-time DataStore subscriptions; uses component state
  - Preserves all dashboard metrics and attendee search

- ✅ **StaffScannerPage** (`client/src/pages/staff/StaffScannerPage.tsx`)
  - Loads event from backend API
  - Uses `scansApi.verifyTicket()` for QR verification
  - Shows scan result modal with backend-persisted records
  - Displays recent scans from backend
  - Removed demo scan scenarios

### Admin Pages
- ✅ **AdminDashboardPage** (`client/src/pages/admin/AdminDashboardPage.tsx`)
  - Already migrated (previous checkpoint)
  - Uses backend dashboard and reports APIs

- ✅ **AdminRegistrationsPage** (`client/src/pages/admin/AdminRegistrationsPage.tsx`)
  - Already migrated (previous checkpoint)
  - Uses `registrationsApi.getPage()` with server-side filtering

- ✅ **AdminTicketsPage** (`client/src/pages/admin/AdminTicketsPage.tsx`)
  - Already migrated (previous checkpoint)
  - Uses `ticketsApi.getPage()` with pagination

- ✅ **AdminScansPage** (`client/src/pages/admin/AdminScansPage.tsx`)
  - Already migrated (previous checkpoint)
  - Uses `scansApi.getPage()` with filtering

- ✅ **AdminReportsPage** (`client/src/pages/admin/AdminReportsPage.tsx`)
  - Migrated in this phase
  - Uses `eventsApi.getById()` for event details
  - Uses `reportsApi.getEventReport()` for aggregates and gate summaries
  - Uses `reportsApi.downloadManifest()` for CSV export
  - Shows error state if backend unreachable

## Backend API Layer

### Configured Endpoints
All endpoints require CSRF protection and session authentication where appropriate:

- **Events API** (`/api/events/`)
  - `GET /events/` - List all events
  - `GET /events/{id_or_slug}/` - Get event by UUID or slug
  - `PATCH /events/{id}/` - Update event (admin only)

- **Registrations API** (`/api/registrations/`)
  - `POST /registrations/` - Online registration (public)
  - `POST /registrations/on-spot/` - Staff on-spot registration
  - `GET /registrations/` - List with pagination and filters (admin)

- **Tickets API** (`/api/tickets/`)
  - `GET /tickets/{id}/` - Retrieve ticket details
  - `DELETE /tickets/{id}/` - Cancel ticket (before use only)
  - `GET /tickets/` - List with pagination and filters (admin)

- **Scans API** (`/api/scans/`)
  - `POST /scans/` - Verify and scan ticket (staff only)
  - `GET /scans/` - List with pagination (admin/scanner)

- **Reports API** (`/api/reports/`)
  - `GET /reports/dashboard/?event_id={id}` - Dashboard summary (admin)
  - `GET /reports/?event_id={id}` - Event report with aggregates (admin)
  - `GET /reports/manifest.csv/?event_id={id}` - Export CSV (admin)

### Environment Configuration
Frontend Vite proxy now configured to route `/api` to backend:

```typescript
// vite.config.ts
proxy: {
  '/api': {
    target: process.env.VITE_API_URL || 'http://localhost:8000',
    changeOrigin: true,
    rewrite: (path) => path.replace(/^\/api/, ''),
  },
}
```

Set `VITE_API_URL` environment variable in `.env.example`:
```
VITE_API_URL=http://localhost:8000
```

## Backend Test Results

All Django API tests passing:
- ✅ 13/13 tests pass (SQLite)
- ⚠️ 2/2 PostgreSQL concurrency tests skipped (require live PostgreSQL)

Test coverage includes:
- Authentication and role-based access
- Event and capacity management
- Online and on-spot registration
- Combo ticket creation (4 independent tickets per order)
- Per-ticket QR code scanning
- Ticket cancellation (before use only)
- Capacity conflict detection
- Duplicate email/phone allowed
- Dashboard and report aggregation

## Frontend Type Checking

✅ **All frontend TypeScript checks pass**
```
npm run lint
> tsc --noEmit
Exit code: 0
```

No remaining references to:
- Legacy `FEATURED_EVENT_ID` in production pages
- Direct `store.get*()` calls in production pages
- `localStorage` or `sessionStorage` in page logic

## Known Limitations and Future Work

### Local DataStore
The legacy demo DataStore (`client/src/api/store.ts`) remains in place but is no longer used by production pages. It may be safely deleted once all component libraries and utilities confirm they don't reference it.

### Demo Mock Data
Mock registration, ticket, and scan data in `client/src/mock/` are not migrated to PostgreSQL. These are demo-only fixtures and should not be used for production capacity or metrics.

### ScannerFrame Component
The `ScannerFrame` component (`client/src/components/scanner/ScannerFrame.tsx`) has been updated to remove demo scenarios and only handle real QR scans via the backend API.

### Authentication Initialization
The `AuthContext` currently does not handle API unreachability errors when initializing `getCurrentUser()`. A follow-up should add explicit loading/error UI if the backend is unavailable at startup.

### PostgreSQL Concurrency
The two PostgreSQL-specific concurrency tests must be run against a live PostgreSQL test database to validate row-locking guarantees. SQLite uses a simpler locking model and cannot validate the full behavior.

## Deployment Checklist

Before deploying to production:

- [ ] Verify backend database is PostgreSQL (not SQLite)
- [ ] Run all concurrency tests against PostgreSQL test database
- [ ] Confirm `VITE_API_URL` or proxy routing is configured correctly
- [ ] Test session authentication across frontendand backend
- [ ] Verify CSRF token exchange works in production domain
- [ ] Confirm error handling for network timeouts
- [ ] Load-test simultaneous combo registration and scanning
- [ ] Verify CSV export and admin reports work end-to-end
- [ ] Test QR code generation and scanning with real devices
- [ ] Validate capacity calculations under concurrent load

## Files Changed in This Phase

### Frontend
- `client/src/pages/public/LandingPage.tsx` - Backend event loading with error state
- `client/src/pages/public/EventDetailPage.tsx` - Already migrated
- `client/src/pages/public/RegistrationPage.tsx` - Already migrated
- `client/src/pages/staff/OnSpotRegistrationPage.tsx` - Removed store import
- `client/src/pages/staff/StaffDashboardPage.tsx` - Backend APIs for dashboard
- `client/src/pages/staff/StaffScannerPage.tsx` - Backend event loading
- `client/src/pages/admin/AdminReportsPage.tsx` - Backend reports API
- `client/vite.config.ts` - Added `/api` proxy
- `client/.env.example` - Added `VITE_API_URL` documentation
- `client/src/api/store.ts` - Fixed status field types
- `client/src/mock/registrations.ts` - Fixed status field types

### Backend
No backend changes in this phase (APIs implemented in previous checkpoint).

## Next Steps

1. **Run Frontend Build**
   ```bash
   cd client
   npm run build
   ```

2. **Test Development Workflow**
   - Start Django: `python manage.py runserver`
   - Start Vite dev server: `npm run dev`
   - Test all pages load correctly
   - Verify backend API calls appear in Django logs

3. **PostgreSQL Validation**
   - Set up a real PostgreSQL database
   - Run migrations: `python manage.py migrate`
   - Run concurrency tests: `python manage.py test tests.test_concurrency`
   - Validate simultaneous combo orders and scans

4. **Remove Legacy DataStore**
   - Once all components confirm no DataStore references
   - Delete `client/src/api/store.ts`
   - Delete `client/src/mock/` directory
   - Remove any localStorage initialization code

5. **Production Deployment**
   - Use PostgreSQL for production
   - Configure environment variables for backend URL
   - Enable HTTPS and secure cookies
   - Configure CORS if frontend and backend are on different domains
   - Enable Django security middleware features
   - Set up monitoring and error tracking

## Rollback Plan

If issues are discovered:
1. All changes are committed with clear messages
2. Revert to the previous checkpoint: `git revert <commit-hash>`
3. The local DataStore is still available for demo fallback
4. API layer design supports gradual rollout (feature flags)
