import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { eventsApi, FEATURED_EVENT_SLUG } from '../../api/events';
import { registrationsApi } from '../../api/registrations';
import { reportsApi } from '../../api/reports';
import { scansApi } from '../../api/scans';
import { ticketsApi } from '../../api/tickets';
import { EventItem, EventReport, ScanRecord, Ticket } from '../../types';
import { useAuth } from '../../context/AuthContext';
import {
  QrCode,
  UserPlus,
  Search,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  LogOut,
} from 'lucide-react';

export const StaffDashboardPage: React.FC = () => {
  const { user, logout } = useAuth();
  const [activeEvent, setActiveEvent] = useState<EventItem | null>(null);
  const [report, setReport] = useState<EventReport | null>(null);
  const [sourceCounts, setSourceCounts] = useState<{ online: number; onSpot: number } | null>(null);
  const [scans, setScans] = useState<ScanRecord[]>([]);
  const [loadingEvent, setLoadingEvent] = useState(true);
  const [dashboardError, setDashboardError] = useState('');

  const [lookupQuery, setLookupQuery] = useState('');
  const [lookupResults, setLookupResults] = useState<Ticket[]>([]);
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupError, setLookupError] = useState('');

  useEffect(() => {
    let cancelled = false;
    const loadDashboard = async () => {
      const errors: string[] = [];
      try {
        const event = await eventsApi.getById(FEATURED_EVENT_SLUG);
        if (!event) throw new Error('Dhandiya Night event details are currently unavailable.');
        if (cancelled) return;
        setActiveEvent(event);
        setLoadingEvent(false);

        if (user?.role === 'ADMIN') {
          try {
            const eventReport = await reportsApi.getEventReport(event.id);
            if (!cancelled) setReport(eventReport);
          } catch (error) {
            errors.push(error instanceof Error ? error.message : 'Unable to load event report.');
          }
        } else if (user?.role === 'REGISTRATION') {
          try {
            const [online, onSpot] = await Promise.all([
              registrationsApi.getPage({ eventId: event.id, source: 'ONLINE' }),
              registrationsApi.getPage({ eventId: event.id, source: 'ON_SPOT' }),
            ]);
            if (!cancelled) setSourceCounts({ online: online.count, onSpot: onSpot.count });
          } catch (error) {
            errors.push(error instanceof Error ? error.message : 'Unable to load registration totals.');
          }
        }

        if (user?.role === 'ADMIN' || user?.role === 'SCANNER') {
          try {
            const page = await scansApi.getPage({ eventId: event.id });
            if (!cancelled) setScans(page.results);
          } catch (error) {
            errors.push(error instanceof Error ? error.message : 'Unable to load recent scans.');
          }
        } else {
          errors.push('Recent scan history is not available for your staff role.');
        }
        if (!cancelled) setDashboardError(errors.join(' '));
      } catch (error) {
        if (!cancelled) {
          setDashboardError(error instanceof Error ? error.message : 'Unable to load the staff dashboard.');
          setLoadingEvent(false);
        }
      }
    };
    void loadDashboard();
    return () => { cancelled = true; };
  }, [user?.role]);

  useEffect(() => {
    const query = lookupQuery.trim();
    if (!query) {
      setLookupResults([]);
      setLookupError('');
      return;
    }
    if (user?.role === 'SCANNER') {
      setLookupResults([]);
      setLookupError('Attendee lookup is not available for your staff role.');
      return;
    }
    if (!activeEvent) return;

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setLookupLoading(true);
      setLookupError('');
      try {
        const page = await ticketsApi.getPage({ eventId: activeEvent.id, search: query });
        if (!cancelled) setLookupResults(page.results);
      } catch (error) {
        if (!cancelled) {
          setLookupResults([]);
          setLookupError(error instanceof Error ? error.message : 'Unable to search tickets. Please try again.');
        }
      } finally {
        if (!cancelled) setLookupLoading(false);
      }
    }, 250);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [activeEvent?.id, lookupQuery, user?.role]);

  if (loadingEvent) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" aria-label="Loading staff dashboard" />
      </div>
    );
  }

  const eventTickets = report?.ticket_statuses ?? [];
  const registeredCount = report
    ? eventTickets.filter((item) => item.status === 'ISSUED' || item.status === 'USED').reduce((sum, item) => sum + item.count, 0)
    : activeEvent?.registeredCount || 0;
  const checkedInCount = report
    ? eventTickets.find((item) => item.status === 'USED')?.count || 0
    : activeEvent?.checkedInCount || 0;
  const remainingCount = Math.max(0, registeredCount - checkedInCount);
  const onlineCount = report
    ? report.registration_sources.find((item) => item.source === 'ONLINE')?.count || 0
    : sourceCounts?.online || 0;
  const onSpotCount = report
    ? report.registration_sources.find((item) => item.source === 'ON_SPOT')?.count || 0
    : sourceCounts?.onSpot || 0;
  const sourceMetricsAvailable = Boolean(report || sourceCounts);
  const eventScans = scans
    .filter((scan) => scan.eventId === activeEvent?.id)
    .sort((a, b) => Date.parse(b.scannedAt) - Date.parse(a.scannedAt))
    .slice(0, 8);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Operational Bar */}
      <header className="bg-slate-900 border-b border-slate-800 px-4 sm:px-8 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/" className="font-display font-bold text-white text-base">
            Soundarya · Event Ops
          </Link>
          <span className="text-slate-600">·</span>
          <span className="text-xs font-mono text-indigo-400 bg-indigo-950/80 px-2 py-0.5 rounded border border-indigo-800/80">
            STAFF DESK
          </span>
        </div>

        <div className="flex items-center gap-4 text-xs">
          <div className="text-right hidden sm:block">
            <span className="font-semibold text-slate-200 block">{user?.name || 'Gate Operator'}</span>
            <span className="text-[11px] text-slate-400 font-mono">
              {user?.role} · {user?.assignedGate || 'Gate 2'}
            </span>
          </div>
          <Link
            to="/staff/login"
            onClick={logout}
            className="p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
            title="Sign out of staff desk"
          >
            <LogOut className="w-4 h-4" />
          </Link>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 p-4 sm:p-8 max-w-7xl mx-auto w-full space-y-8">
        {dashboardError && <div role="alert" className="rounded-xl border border-rose-900/60 bg-rose-950/30 px-4 py-3 text-xs leading-relaxed text-rose-200">{dashboardError}</div>}
        <div className="rounded-xl border border-amber-900/60 bg-amber-950/30 px-4 py-3 text-xs leading-relaxed text-amber-200/90">
          Dashboard counts and scan activity are loaded from the ticketing service.
        </div>
        {/* Festival Session & Quick Action Bar */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900 border border-slate-800 rounded-2xl p-4 sm:p-6">
          <div className="space-y-1">
            <span className="text-[11px] font-mono font-semibold text-indigo-400 uppercase tracking-wider block">
              ACTIVE VENUE OPERATING SESSION
            </span>
            <div className="flex items-center gap-3">
              <h1 className="font-display text-xl font-bold text-white">
                Dhandiya Night <span className="festival-script text-lg text-indigo-400">· 16 October</span>
              </h1>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Venue: {activeEvent?.venue} &bull; Live records
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <Link
              to="/staff/scanner"
              className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-bold uppercase tracking-wider inline-flex items-center gap-2 shadow-md shadow-indigo-600/30 transition-all cursor-pointer"
            >
              <QrCode className="w-4 h-4" />
              <span>LAUNCH SCANNER</span>
            </Link>

            <Link
              to="/staff/register"
              className="px-4 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-200 hover:text-white border border-slate-700 rounded-xl text-xs font-semibold inline-flex items-center gap-2 transition-all cursor-pointer"
            >
              <UserPlus className="w-4 h-4 text-indigo-400" />
              <span>ON_SPOT KIOSK</span>
            </Link>

            <Link
              to="/admin"
              className="px-3.5 py-2.5 text-xs text-slate-400 hover:text-white hover:bg-slate-800 rounded-xl transition-colors"
            >
              Admin Console &rarr;
            </Link>
          </div>
        </div>

        {/* 4 Core Operational Metric Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
              Registered Total
            </span>
            <div className="text-2xl sm:text-3xl font-extrabold text-white font-mono tabular-nums">
              {registeredCount.toLocaleString()}
            </div>
            <div className="text-xs text-slate-500 mt-1 font-mono">
              Online: {sourceMetricsAvailable ? onlineCount.toLocaleString() : '—'} · Walk-ins: {sourceMetricsAvailable ? onSpotCount.toLocaleString() : '—'}
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
            <span className="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider block mb-1">
              Checked In
            </span>
            <div className="text-2xl sm:text-3xl font-extrabold text-emerald-400 font-mono tabular-nums">
              {checkedInCount.toLocaleString()}
            </div>
            <div className="text-xs text-slate-500 mt-1 font-mono">
              {registeredCount > 0
                ? `${Math.round((checkedInCount / registeredCount) * 100)}% of registrations`
                : '0% of registrations'}
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
            <span className="text-[11px] font-semibold text-amber-400 uppercase tracking-wider block mb-1">
              Remaining Outside
            </span>
            <div className="text-2xl sm:text-3xl font-extrabold text-amber-400 font-mono tabular-nums">
              {remainingCount.toLocaleString()}
            </div>
            <div className="text-xs text-slate-500 mt-1 font-mono">
              Expected at gate
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
            <span className="text-[11px] font-semibold text-indigo-400 uppercase tracking-wider block mb-1">
              On-Spot Venue Desk
            </span>
            <div className="text-2xl sm:text-3xl font-extrabold text-indigo-300 font-mono tabular-nums">
              {sourceMetricsAvailable ? onSpotCount.toLocaleString() : '—'}
            </div>
            <div className="text-xs text-slate-500 mt-1 font-mono">
              Issued at kiosk desk
            </div>
          </div>
        </div>

        {/* 2-Column Operational Grid: Attendee Lookup Desk + Live Scans Feed */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Attendee Quick Lookup Desk */}
          <div className="lg:col-span-6 bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wider font-display">
                  Registration &amp; Ticket Lookup
                </h3>
                <p className="text-xs text-slate-400">
                  Search attendee by name, phone, or ticket ID for venue resolution.
                </p>
              </div>
              <Search className="w-4 h-4 text-indigo-400" />
            </div>

            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={lookupQuery}
                onChange={(e) => setLookupQuery(e.target.value)}
                placeholder="Type name, phone number, or TKT-..."
                className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-10 pr-4 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            {/* Results List */}
            <div className="space-y-2 max-h-72 overflow-y-auto pt-2">
              {lookupLoading ? (
                <div className="p-6 text-center text-xs text-slate-400">Searching tickets…</div>
              ) : lookupError ? (
                <div role="alert" className="p-6 text-center text-xs text-rose-300">{lookupError}</div>
              ) : lookupQuery.trim() === '' ? (
                <div className="p-6 text-center text-xs text-slate-500">
                  Enter an attendee keyword to inspect ticket status
                </div>
              ) : lookupResults.length === 0 ? (
                <div className="p-6 text-center text-xs text-rose-400 bg-slate-950 rounded-xl border border-rose-950">
                  No matching registered attendee found
                </div>
              ) : (
                lookupResults.map((t) => (
                  <div
                    key={t.id}
                    className="p-3 bg-slate-950 border border-slate-800 rounded-xl flex items-center justify-between text-xs"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-white">{t.attendeeName}</span>
                        <span
                          className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                            t.status === 'USED'
                              ? 'bg-amber-950 text-amber-300'
                              : t.status === 'ISSUED'
                              ? 'bg-emerald-950 text-emerald-300'
                              : 'bg-rose-950 text-rose-300'
                          }`}
                        >
                          {t.status}
                        </span>
                      </div>
                      <p className="text-slate-400 text-[11px]">
                        {t.attendeeEmail} &bull; {t.attendeePhone}
                      </p>
                      <p className="text-[10px] text-indigo-400 font-mono mt-0.5">
                        {t.id} &bull; {t.tierName} ({t.source})
                      </p>
                    </div>

                    <div className="text-right">
                      <Link
                        to={`/ticket/${t.id}`}
                        className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold"
                      >
                        View Pass &rarr;
                      </Link>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Recent Scans Activity Feed */}
          <div className="lg:col-span-6 bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wider font-display">
                  Recent Gate Scans
                </h3>
                <p className="text-xs text-slate-400">
                  Recent scan results for {activeEvent?.name}.
                </p>
              </div>
              <Clock className="w-4 h-4 text-indigo-400" />
            </div>

            <div className="divide-y divide-slate-800/80 max-h-80 overflow-y-auto">
              {eventScans.length === 0 ? (
                <div className="p-6 text-center text-xs text-slate-500">
                  No scan events recorded yet for this session.
                </div>
              ) : (
                eventScans.map((scan) => {
                  const timeStr = new Date(scan.scannedAt).toLocaleTimeString();
                  const isSuccess = scan.result === 'ENTRY_GRANTED';
                  const isUsed = scan.result === 'ALREADY_USED';

                  return (
                    <div key={scan.id} className="py-2.5 flex items-center justify-between text-xs">
                      <div className="flex items-center gap-3">
                        {isSuccess ? (
                          <div className="w-6 h-6 rounded-full bg-emerald-950 text-emerald-400 flex items-center justify-center shrink-0 border border-emerald-800">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                          </div>
                        ) : isUsed ? (
                          <div className="w-6 h-6 rounded-full bg-amber-950 text-amber-400 flex items-center justify-center shrink-0 border border-amber-800">
                            <AlertTriangle className="w-3.5 h-3.5" />
                          </div>
                        ) : (
                          <div className="w-6 h-6 rounded-full bg-rose-950 text-rose-400 flex items-center justify-center shrink-0 border border-rose-800">
                            <XCircle className="w-3.5 h-3.5" />
                          </div>
                        )}

                        <div>
                          <p className="font-semibold text-white">{scan.attendeeName}</p>
                          <p className="text-[10px] text-slate-400">
                            {scan.gate} &bull; {scan.staffName}
                          </p>
                        </div>
                      </div>

                      <div className="text-right">
                        <span
                          className={`font-mono text-[10px] font-bold block ${
                            isSuccess
                              ? 'text-emerald-400'
                              : isUsed
                              ? 'text-amber-400'
                              : 'text-rose-400'
                          }`}
                        >
                          {scan.result}
                        </span>
                        <span className="text-[10px] text-slate-500 font-mono">{timeStr}</span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};
