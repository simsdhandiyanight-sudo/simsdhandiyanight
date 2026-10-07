import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Ban, CheckCircle2, Filter, Search, XCircle } from 'lucide-react';
import { eventsApi, FEATURED_EVENT_SLUG } from '../../api/events';
import { reportsApi } from '../../api/reports';
import { scansApi } from '../../api/scans';
import { AdminLayout } from '../../components/admin/AdminLayout';
import { DashboardSummary, ScanRecord, ScanResultType } from '../../types';

type ScanFilter = 'all' | ScanResultType;

export const AdminScansPage: React.FC = () => {
  const [scans, setScans] = useState<ScanRecord[]>([]);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [filterResult, setFilterResult] = useState<ScanFilter>('all');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(async () => {
      setLoadError('');
      try {
        const event = await eventsApi.getById(FEATURED_EVENT_SLUG);
        if (!event) throw new Error('The event is not available from the events service.');
        const [response, currentSummary] = await Promise.all([
          scansApi.getPage({
            page,
            eventId: event.id,
            result: filterResult === 'all' ? undefined : filterResult,
            search,
          }),
          reportsApi.getDashboardSummary(event.id),
        ]);
        if (active) {
          setScans(response.results);
          setTotalCount(response.count);
          setPageCount(Math.ceil(response.count / 50));
          setSummary(currentSummary);
        }
      } catch (error) {
        if (active) setLoadError(error instanceof Error ? error.message : 'Unable to load scan history.');
      }
    }, 200);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [filterResult, page, search]);

  const filteredScans = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    return scans
      .filter((scan) => filterResult === 'all' || scan.result === filterResult)
      .filter((scan) =>
        !normalizedSearch ||
        [scan.attendeeName, scan.ticketId || '', scan.staffName, scan.gate]
          .some((value) => value.toLowerCase().includes(normalizedSearch))
      );
  }, [filterResult, scans, search]);

  const countFor = (result: string) =>
    summary?.scan_results.find((item) => item.result === result)?.count ?? 0;
  const totalGranted = summary?.entry_granted ?? 0;
  const totalAlreadyUsed = countFor('ALREADY_USED');
  const totalInvalidOrCancelled = countFor('INVALID_TICKET') + countFor('CANCELLED');
  const totalOtherIssues = countFor('WRONG_EVENT') + countFor('EVENT_CLOSED');

  return (
    <AdminLayout title="Scan history" breadcrumbs={[{ label: 'Scan history' }]}>
      <div className="space-y-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="font-display text-xl font-bold text-white">Ticket scan history</h2>
            <p className="mt-1 text-xs leading-relaxed text-slate-400">
              Recorded ticket validation attempts from the backend.
            </p>
          </div>
          <span className="w-fit rounded-full border border-amber-900/70 bg-amber-950/40 px-3 py-1.5 text-[11px] font-semibold text-amber-300">
            {totalCount} records
          </span>
        </div>
        {loadError && (
          <p role="alert" className="rounded-xl border border-rose-900/70 bg-rose-950/40 p-3 text-xs text-rose-200">{loadError}</p>
        )}

        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <Metric
            label="ENTRY GRANTED"
            value={totalGranted}
            description="Locally recorded admissions"
            icon={<CheckCircle2 className="h-4 w-4 text-emerald-400" />}
            valueClass="text-emerald-300"
          />
          <Metric
            label="ALREADY USED"
            value={totalAlreadyUsed}
            description="Duplicate attempts"
            icon={<AlertTriangle className="h-4 w-4 text-amber-400" />}
            valueClass="text-amber-300"
          />
          <Metric
            label="INVALID / CANCELLED"
            value={totalInvalidOrCancelled}
            description="Unrecognized or cancelled tickets"
            icon={<XCircle className="h-4 w-4 text-rose-400" />}
            valueClass="text-rose-300"
          />
          <Metric
            label="OTHER ISSUES"
            value={totalOtherIssues}
            description="Wrong event, closed, or network error"
            icon={<Ban className="h-4 w-4 text-indigo-400" />}
            valueClass="text-indigo-300"
          />
        </div>

        <div className="flex flex-col gap-3 rounded-2xl border border-slate-800 bg-slate-900 p-3 sm:flex-row sm:items-center">
          <label className="flex min-w-0 flex-1 items-center gap-2 rounded-lg border border-slate-800 bg-slate-950 px-3 py-2">
            <Search className="h-4 w-4 shrink-0 text-slate-500" />
            <span className="sr-only">Search scan history</span>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search attendee, ticket, gate, or operator"
              className="min-w-0 flex-1 bg-transparent text-xs text-white placeholder:text-slate-500 focus:outline-none"
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-400">
            <Filter className="h-4 w-4 shrink-0" />
            <span className="sr-only">Filter by result</span>
            <select
              value={filterResult}
              onChange={(event) => {
                setFilterResult(event.target.value as ScanFilter);
                setPage(1);
              }}
              className="max-w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-xs text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="all">All results</option>
              <option value="ENTRY_GRANTED">Entry granted</option>
              <option value="ALREADY_USED">Already used</option>
              <option value="INVALID_TICKET">Invalid ticket</option>
              <option value="CANCELLED">Cancelled</option>
              <option value="WRONG_EVENT">Wrong event</option>
              <option value="EVENT_CLOSED">Event closed</option>
            </select>
          </label>
          <span className="whitespace-nowrap text-[11px] font-mono text-slate-500">
            {filteredScans.length} shown
          </span>
        </div>

        <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-left text-xs">
              <thead className="border-b border-slate-800 bg-slate-950 text-[10px] font-mono uppercase text-slate-400">
                <tr>
                  <th className="px-4 py-3">Timestamp</th>
                  <th className="px-4 py-3">Attendee</th>
                  <th className="px-4 py-3">Gate</th>
                  <th className="px-4 py-3">Operator</th>
                  <th className="px-4 py-3">Ticket ID</th>
                  <th className="px-4 py-3">Result</th>
                  <th className="px-4 py-3">Notes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {filteredScans.map((scan) => (
                  <tr key={scan.id} className="transition-colors hover:bg-slate-800/40">
                    <td className="whitespace-nowrap px-4 py-3.5 font-mono text-slate-300">
                      {new Date(scan.scannedAt).toLocaleString()}
                    </td>
                    <td className="px-4 py-3.5 font-semibold text-white">{scan.attendeeName}</td>
                    <td className="whitespace-nowrap px-4 py-3.5 font-mono font-bold text-indigo-300">{scan.gate}</td>
                    <td className="px-4 py-3.5 text-slate-400">{scan.staffName}</td>
                    <td className="whitespace-nowrap px-4 py-3.5 font-mono text-slate-300">{scan.ticketId || '—'}</td>
                    <td className="px-4 py-3.5">
                      <ResultBadge result={scan.result} />
                    </td>
                    <td className="max-w-xs truncate px-4 py-3.5 text-[11px] text-slate-400">
                      {scan.notes || '—'}
                    </td>
                  </tr>
                ))}
                {filteredScans.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-12 text-center text-sm text-slate-500">
                      No scan records match these filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
        <div className="flex items-center justify-between border-t border-slate-800 px-4 py-3 text-xs text-slate-400">
          <span>Page {page} of {Math.max(1, pageCount)}</span>
          <div className="flex gap-2">
            <button disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))} className="rounded-lg border border-slate-700 px-3 py-1.5 disabled:opacity-40">Previous</button>
            <button disabled={page >= pageCount} onClick={() => setPage((value) => value + 1)} className="rounded-lg border border-slate-700 px-3 py-1.5 disabled:opacity-40">Next</button>
          </div>
        </div>
      </div>
    </AdminLayout>
  );
};

interface MetricProps {
  label: string;
  value: number;
  description: string;
  icon: React.ReactNode;
  valueClass: string;
}

const Metric: React.FC<MetricProps> = ({ label, value, description, icon, valueClass }) => (
  <div className="rounded-2xl border border-slate-800 bg-slate-900 p-4 sm:p-5">
    <div className="mb-2 flex items-center justify-between gap-2">
      <span className="font-mono text-[10px] font-semibold tracking-wider text-slate-400">{label}</span>
      {icon}
    </div>
    <div className={`font-mono text-3xl font-extrabold tabular-nums ${valueClass}`}>{value}</div>
    <p className="mt-1 text-[11px] leading-relaxed text-slate-500">{description}</p>
  </div>
);

const resultStyle: Record<ScanResultType, string> = {
  ENTRY_GRANTED: 'border-emerald-800/80 bg-emerald-950/80 text-emerald-300',
  ALREADY_USED: 'border-amber-800/80 bg-amber-950/80 text-amber-300',
  INVALID_TICKET: 'border-rose-800/80 bg-rose-950/80 text-rose-300',
  CANCELLED: 'border-rose-800/80 bg-rose-950/80 text-rose-300',
  WRONG_EVENT: 'border-amber-800/80 bg-amber-950/80 text-amber-300',
  EVENT_CLOSED: 'border-slate-700 bg-slate-800 text-slate-300',
  NETWORK_ERROR: 'border-indigo-800/80 bg-indigo-950/80 text-indigo-300',
};

const ResultBadge: React.FC<{ result: ScanResultType }> = ({ result }) => (
  <span className={`inline-flex whitespace-nowrap rounded border px-2 py-0.5 font-mono text-[10px] font-bold ${resultStyle[result]}`}>
    {result}
  </span>
);
