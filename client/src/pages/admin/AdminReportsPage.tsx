import React, { useEffect, useState } from 'react';
import { eventsApi, FEATURED_EVENT_SLUG } from '../../api/events';
import { reportsApi } from '../../api/reports';
import { EventItem, EventReport } from '../../types';
import { AdminLayout } from '../../components/admin/AdminLayout';
import { StatCard } from '../../components/admin/StatCard';
import {
  Download,
  Calendar,
  Users,
  CheckCircle2,
  TrendingUp,
  PieChart,
  FileSpreadsheet,
} from 'lucide-react';

export const AdminReportsPage: React.FC = () => {
  const [activeEvent, setActiveEvent] = useState<EventItem | null>(null);
  const [report, setReport] = useState<EventReport | null>(null);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const event = await eventsApi.getById(FEATURED_EVENT_SLUG);
        if (!event) throw new Error('The event is not available from the events service.');
        const eventReport = await reportsApi.getEventReport(event.id);
        if (active) {
          setActiveEvent(event);
          setReport(eventReport);
        }
      } catch (error) {
        if (active) setLoadError(error instanceof Error ? error.message : 'Unable to load event reports.');
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, []);

  const handleExportCSV = async () => {
    if (!activeEvent) return;
    setLoadError('');
    try {
      const file = await reportsApi.downloadManifest(activeEvent.id);
      const objectUrl = URL.createObjectURL(file);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = `Soundarya_Dhandiya_${activeEvent.slug}_Report.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : 'Unable to export the event manifest.');
    }
  };

  const totalRegistered = activeEvent?.registeredCount || 0;
  const totalCheckedIn = report?.ticket_statuses.find((item) => item.status === 'USED')?.count ?? 0;
  const attendanceRate = totalRegistered > 0 ? Math.round((totalCheckedIn / totalRegistered) * 100) : 0;
  const gateSummaries = report?.gates ?? [];
  const scanAttempts = gateSummaries.reduce((count, gate) => count + gate.attempts, 0);

  return (
    <AdminLayout
      title="Analytics &amp; Operational Reports"
      breadcrumbs={[{ label: 'Reports' }]}
      actions={
        <button
          onClick={handleExportCSV}
          className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold inline-flex items-center gap-1.5 transition-colors cursor-pointer shadow-sm"
        >
          <Download className="w-3.5 h-3.5" />
          <span>Export Audit CSV</span>
        </button>
      }
    >
      <div className="space-y-6">
        {loadError && (
          <p role="alert" className="rounded-xl border border-rose-900/70 bg-rose-950/40 p-3 text-xs text-rose-200">{loadError}</p>
        )}
        {/* Festival event summary */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-900 border border-slate-800 rounded-2xl p-4 sm:p-5">
          <div>
            <h2 className="text-xl font-bold font-display text-white">Event Performance Analytics</h2>
            <p className="text-xs text-slate-400">
              Review registration, ticket, and scan aggregates calculated by the backend.
            </p>
          </div>

          <span className="festival-script text-xl font-bold text-rose-700">Dhandiya Night · 16 October</span>
        </div>

        {/* 4 Stat Overview */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            label="Ticket Capacity"
            value={activeEvent?.capacity.toLocaleString() || '0'}
            subValue="Configured registration limit"
            icon={<Calendar className="w-4 h-4 text-indigo-400" />}
          />
          <StatCard
            label="Total Badges Issued"
            value={totalRegistered.toLocaleString()}
            subValue={`${Math.round((totalRegistered / (activeEvent?.capacity || 1)) * 100)}% allocation`}
            icon={<Users className="w-4 h-4 text-indigo-400" />}
          />
          <StatCard
            label="Recorded Check-ins"
            value={totalCheckedIn.toLocaleString()}
            subValue={`${attendanceRate}% of active admissions`}
            icon={<CheckCircle2 className="w-4 h-4 text-emerald-400" />}
          />
          <StatCard
            label="Scan Attempts"
            value={scanAttempts.toLocaleString()}
            subValue="Persisted scan attempts"
            icon={<TrendingUp className="w-4 h-4 text-indigo-400" />}
          />
        </div>

        {/* Detailed Breakdown Grids */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Tier Allocations */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wider font-display">
                  Pass Tier Breakdown
                </h3>
                <p className="text-xs text-slate-400">Registrations segmented by tier.</p>
              </div>
              <PieChart className="w-4 h-4 text-indigo-400" />
            </div>

            <div className="space-y-4 pt-2">
              {activeEvent?.tiers.map((tier) => {
                const tierRegs = report?.tiers.find((item) => item.tier_id === tier.id)?.count ?? 0;
                const percent = Math.min(
                  100,
                  Math.round((tierRegs / activeEvent.capacity) * 100)
                );

                return (
                  <div key={tier.id} className="space-y-1.5">
                    <div className="flex justify-between text-xs">
                      <span className="font-semibold text-white">{tier.name}</span>
                      <span className="font-mono text-slate-400">
                        {tierRegs} tickets &bull; ₹{tier.price} offer amount
                      </span>
                    </div>
                    <div className="w-full bg-slate-950 h-2 rounded-full overflow-hidden">
                      <div
                        className="bg-indigo-500 h-full rounded-full"
                        style={{ width: `${percent}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Recorded scan attempts by gate */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wider font-display">
                  Scan activity by gate
                </h3>
                <p className="text-xs text-slate-400">Counts from persisted server scan records.</p>
              </div>
              <FileSpreadsheet className="w-4 h-4 text-indigo-400" />
            </div>

            <div className="divide-y divide-slate-800 text-xs">
              {gateSummaries.length ? gateSummaries.map((gate) => (
                <div key={gate.gate} className="flex items-center justify-between gap-3 py-2.5">
                  <span className="text-slate-300">{gate.gate}</span>
                  <span className="font-mono text-slate-400">
                    {gate.attempts} attempts · {gate.granted} granted
                  </span>
                </div>
              )) : (
                <p className="py-6 text-center text-slate-500">No scan records for this event.</p>
              )}
            </div>

            <div className="pt-2">
              <button
                onClick={handleExportCSV}
                className="w-full py-3 bg-slate-950 hover:bg-slate-800 border border-slate-800 text-slate-200 hover:text-white rounded-xl text-xs font-semibold flex items-center justify-center gap-2 transition-colors cursor-pointer"
              >
                <Download className="w-4 h-4 text-indigo-400" />
                <span>Download Complete Event Manifest (.CSV)</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </AdminLayout>
  );
};
