import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { AdminEventContext, eventsApi, FEATURED_EVENT_SLUG } from '../../api/events';
import { reportsApi } from '../../api/reports';
import { scansApi } from '../../api/scans';
import { DashboardSummary, ScanRecord } from '../../types';
import { AdminLayout } from '../../components/admin/AdminLayout';
import { StatCard } from '../../components/admin/StatCard';
import {
  Calendar,
  Users,
  Ticket as TicketIcon,
  CheckCircle2,
  ArrowRight,
  TrendingUp,
} from 'lucide-react';

export const AdminDashboardPage: React.FC = () => {
  const [event, setEvent] = useState<AdminEventContext | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [scans, setScans] = useState<ScanRecord[]>([]);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const currentEvent = await eventsApi.getAdminContext(FEATURED_EVENT_SLUG);
        const [currentSummary, recentScans] = await Promise.all([
          reportsApi.getDashboardSummary(currentEvent.id),
          scansApi.getPage({ eventId: currentEvent.id, page: 1 }),
        ]);
        if (active) {
          setEvent(currentEvent);
          setSummary(currentSummary);
          setScans(recentScans.results);
        }
      } catch (error) {
        if (active) setLoadError(error instanceof Error ? error.message : 'Unable to load dashboard data.');
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, []);

  const totalRegistrations = summary?.registrations ?? 0;
  const onlineCount = summary?.online_registrations ?? 0;
  const onSpotCount = summary?.on_spot_registrations ?? 0;
  const checkedInCount = summary?.used_tickets ?? 0;
  const checkInRate =
    (summary?.active_tickets ?? 0) > 0
      ? Math.round((checkedInCount / (summary?.active_tickets ?? 1)) * 100)
      : 0;

  const scanCount = (result: string) =>
    summary?.scan_results.find((item) => item.result === result)?.count ?? 0;
  const successfulScans = summary?.entry_granted ?? 0;
  const warningScans = scanCount('ALREADY_USED');
  const scanOutcomes = [
    { label: 'Granted', count: scanCount('ENTRY_GRANTED'), color: 'from-emerald-700 to-emerald-500' },
    { label: 'Already used', count: scanCount('ALREADY_USED'), color: 'from-amber-700 to-amber-500' },
    { label: 'Invalid', count: scanCount('INVALID_TICKET'), color: 'from-rose-700 to-rose-500' },
    { label: 'Cancelled', count: scanCount('CANCELLED'), color: 'from-rose-700 to-rose-500' },
    { label: 'Other', count: scanCount('WRONG_EVENT') + scanCount('EVENT_CLOSED'), color: 'from-indigo-700 to-indigo-500' },
  ];
  const maxOutcomeCount = Math.max(1, ...scanOutcomes.map((outcome) => outcome.count));

  return (
    <AdminLayout
      title="Admin Dashboard"
      breadcrumbs={[{ label: 'Dashboard Overview' }]}
      actions={
        <Link
          to="/staff/scanner"
          className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold inline-flex items-center gap-1.5 transition-colors shadow-sm"
        >
          <span>Gate Scanner</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      }
    >
      <div className="space-y-8">
        {loadError && (
          <div role="alert" className="rounded-xl border border-rose-900/70 bg-rose-950/40 px-4 py-3 text-xs text-rose-200">
            {loadError}
          </div>
        )}
        {/* Metric Cards Row */}
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
          <StatCard
            label="Dhandiya Night"
            value={event?.status.toUpperCase() ?? 'UNAVAILABLE'}
            subValue={event?.formattedDate ?? 'Event unavailable'}
            icon={<Calendar className="w-4 h-4 text-indigo-400" />}
          />

          <StatCard
            label="Total Registrations"
            value={totalRegistrations.toLocaleString()}
            subValue="Orders recorded by the backend"
            icon={<Users className="w-4 h-4 text-indigo-400" />}
          />

          <StatCard
            label="Online Passes"
            value={onlineCount}
            subValue={`${Math.round((onlineCount / (totalRegistrations || 1)) * 100)}% of total`}
            icon={<TicketIcon className="w-4 h-4 text-indigo-400" />}
          />

          <StatCard
            label="On-Spot Kiosk"
            value={onSpotCount}
            subValue="Walk-in venue registrations"
            icon={<TrendingUp className="w-4 h-4 text-emerald-400" />}
          />

          <StatCard
            label="Checked In"
            value={checkedInCount}
            subValue={`${checkInRate}% check-in rate`}
            icon={<CheckCircle2 className="w-4 h-4 text-emerald-400" />}
          />
        </div>

        {/* Charts & Visual Telemetry */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Scan results from records stored in this browser */}
          <div className="lg:col-span-8 bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
            <div>
              <div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wider font-display">
                  Scan outcomes
                </h3>
                <p className="text-xs text-slate-400">
                  Counts are aggregated from persisted scan history.
                </p>
              </div>
            </div>

            <div className="space-y-4 pt-2">
              {scanOutcomes.map((item) => (
                <div key={item.label}>
                  <div className="mb-1 flex items-center justify-between gap-3 text-xs">
                    <span className="text-slate-300">{item.label}</span>
                    <span className="font-mono font-bold text-white">{item.count}</span>
                  </div>
                  <div
                    className="h-2 overflow-hidden rounded-full bg-slate-950"
                    role="img"
                    aria-label={`${item.label}: ${item.count} scan records`}
                  >
                    <div
                      className={`h-full rounded-full bg-gradient-to-r ${item.color}`}
                      style={{ width: `${(item.count / maxOutcomeCount) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Admission Channel Breakdown */}
          <div className="lg:col-span-4 bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4 flex flex-col justify-between">
            <div>
              <h3 className="text-sm font-bold text-white uppercase tracking-wider font-display">
                Channel Distribution
              </h3>
              <p className="text-xs text-slate-400">Online pre-registration vs on-spot desk.</p>
            </div>

            {/* Proportion bars */}
            <div className="space-y-4">
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-slate-300">Online Pre-Registration</span>
                  <span className="font-mono font-bold text-indigo-400">
                    {onlineCount} ({totalRegistrations > 0 ? Math.round((onlineCount / totalRegistrations) * 100) : 0}%)
                  </span>
                </div>
                <div className="h-2 bg-slate-950 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-indigo-500 rounded-full"
                    style={{
                      width: `${totalRegistrations > 0 ? (onlineCount / totalRegistrations) * 100 : 0}%`,
                    }}
                  />
                </div>
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-slate-300">Venue On-Spot Kiosk</span>
                  <span className="font-mono font-bold text-emerald-400">
                    {onSpotCount} ({totalRegistrations > 0 ? Math.round((onSpotCount / totalRegistrations) * 100) : 0}%)
                  </span>
                </div>
                <div className="h-2 bg-slate-950 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-emerald-500 rounded-full"
                    style={{
                      width: `${totalRegistrations > 0 ? (onSpotCount / totalRegistrations) * 100 : 0}%`,
                    }}
                  />
                </div>
              </div>

              <div className="pt-3 border-t border-slate-800 text-xs text-slate-400 space-y-1">
                <div className="flex justify-between">
                  <span>Successful entries</span>
                  <span className="font-mono text-white">{successfulScans}</span>
                </div>
                <div className="flex justify-between">
                  <span>Duplicate scan blocks</span>
                  <span className="font-mono text-amber-400">{warningScans}</span>
                </div>
              </div>
            </div>

            <Link
              to="/admin/scans"
              className="w-full py-2.5 text-center text-xs font-semibold text-indigo-400 hover:text-white bg-slate-950 border border-slate-800 rounded-xl transition-colors block"
            >
              Review Scan History &rarr;
            </Link>
          </div>
        </div>

        {/* Recent Scans Table */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-white uppercase tracking-wider font-display">
                Recent Gate Logs
              </h3>
              <p className="text-xs text-slate-400">
                Most recent scan records from the event database.
              </p>
            </div>
            <Link
              to="/admin/scans"
              className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold"
            >
              View Full Monitor &rarr;
            </Link>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950 border-b border-slate-800 text-slate-400 uppercase font-mono text-[10px]">
                <tr>
                  <th className="py-2.5 px-3">Log ID</th>
                  <th className="py-2.5 px-3">Ticket ID</th>
                  <th className="py-2.5 px-3">Attendee</th>
                  <th className="py-2.5 px-3">Event</th>
                  <th className="py-2.5 px-3">Gate &bull; Operator</th>
                  <th className="py-2.5 px-3">Result</th>
                  <th className="py-2.5 px-3 text-right">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/80">
                {scans.slice(0, 5).map((s) => {
                  const isSuccess = s.result === 'ENTRY_GRANTED';
                  const isUsed = s.result === 'ALREADY_USED';

                  return (
                    <tr key={s.id} className="hover:bg-slate-800/40 transition-colors">
                      <td className="py-3 px-3 font-mono text-slate-400">{s.id}</td>
                      <td className="py-3 px-3 font-mono text-indigo-400 font-semibold">
                        {s.ticketId || '—'}
                      </td>
                      <td className="py-3 px-3 font-semibold text-white">{s.attendeeName}</td>
                      <td className="py-3 px-3 text-slate-300 truncate max-w-[140px]">
                        {s.eventName}
                      </td>
                      <td className="py-3 px-3 text-slate-400">
                        {s.gate} · {s.staffName}
                      </td>
                      <td className="py-3 px-3">
                        <span
                          className={`font-mono font-bold text-[11px] ${
                            isSuccess
                              ? 'text-emerald-400'
                              : isUsed
                              ? 'text-amber-400'
                              : 'text-rose-400'
                          }`}
                        >
                          {s.result}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-right font-mono text-slate-400">
                        {new Date(s.scannedAt).toLocaleTimeString()}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </AdminLayout>
  );
};
