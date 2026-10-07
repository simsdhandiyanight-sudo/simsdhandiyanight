import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { eventsApi, FEATURED_EVENT_SLUG } from '../../api/events';
import { ticketsApi } from '../../api/tickets';
import { Ticket, TicketStatus } from '../../types';
import { AdminLayout } from '../../components/admin/AdminLayout';
import { Modal } from '../../components/common/Modal';
import {
  Search,
  ExternalLink,
  Ban,
  ShieldAlert,
} from 'lucide-react';

export const AdminTicketsPage: React.FC = () => {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | TicketStatus>('all');
  const [page, setPage] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [loadError, setLoadError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);

  // Cancel Confirmation Modal State
  const [ticketToCancel, setTicketToCancel] = useState<Ticket | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const [cancelError, setCancelError] = useState('');

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(async () => {
      setLoadError('');
      try {
        const event = await eventsApi.getById(FEATURED_EVENT_SLUG);
        if (!event) throw new Error('The event is not available from the events service.');
        const response = await ticketsApi.getPage({
          page,
          eventId: event.id,
          status: statusFilter === 'all' ? undefined : statusFilter,
          search,
        });
        if (active) {
          setTickets(response.results);
          setTotalCount(response.count);
          setPageCount(Math.ceil(response.count / 50));
        }
      } catch (error) {
        if (active) setLoadError(error instanceof Error ? error.message : 'Unable to load tickets.');
      }
    }, 200);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [page, reloadKey, search, statusFilter]);

  const filteredTickets = tickets;

  const handleConfirmCancel = async () => {
    if (!ticketToCancel) return;
    setIsCancelling(true);
    setCancelError('');
    try {
      const cancelled = await ticketsApi.cancel(ticketToCancel.id);
      if (!cancelled) {
        setCancelError('This ticket is no longer available for cancellation. It may have already been used or cancelled.');
        return;
      }
      setTicketToCancel(null);
      setReloadKey((key) => key + 1);
    } catch (error) {
      setCancelError(error instanceof Error ? error.message : 'Could not cancel this demo ticket.');
    } finally {
      setIsCancelling(false);
    }
  };

  return (
    <AdminLayout
      title="Ticket Pass Management"
      breadcrumbs={[{ label: 'Tickets' }]}
    >
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h2 className="text-xl font-bold font-display text-white">Digital Ticket Passes</h2>
            <p className="text-xs text-slate-400">
              Review ticket status and locally recorded check-in details.
            </p>
          </div>
          <span className="text-xs font-mono text-slate-500">
            {totalCount} Digital Passes
          </span>
        </div>
        {loadError && (
          <p role="alert" className="rounded-xl border border-rose-900/70 bg-rose-950/40 p-3 text-xs text-rose-200">{loadError}</p>
        )}

        {/* Filters Toolbar */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs">
          <div className="relative flex-1 w-full sm:max-w-xs">
            <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search Ticket ID, Attendee, Event..."
              className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-10 pr-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto">
            <span className="text-slate-400 font-semibold uppercase text-[10px]">Filter Status:</span>
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value as 'all' | TicketStatus);
                setPage(1);
              }}
              className="bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer text-xs"
            >
              <option value="all">All Passes</option>
              <option value="ISSUED">ISSUED (Active)</option>
              <option value="USED">USED (Checked In)</option>
              <option value="CANCELLED">CANCELLED (Revoked)</option>
            </select>
          </div>
        </div>

        <div className="p-3.5 bg-slate-900/60 border border-slate-800 rounded-2xl flex items-center justify-between text-xs text-slate-400">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-indigo-400 shrink-0" />
            <span>
              Ticket status and entry history are managed by the backend.
            </span>
          </div>
          <Link
            to="/staff/scanner"
            className="text-indigo-400 hover:text-indigo-300 font-semibold whitespace-nowrap ml-2"
          >
            Open Scanner Desk &rarr;
          </Link>
        </div>

        {/* Tickets Data Table */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950 border-b border-slate-800 text-slate-400 uppercase font-mono text-[10px]">
                <tr>
                  <th className="py-3 px-4">Ticket ID</th>
                  <th className="py-3 px-4">Attendee</th>
                  <th className="py-3 px-4">Event &bull; Tier</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Channel</th>
                  <th className="py-3 px-4">Issued &bull; Checked In</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {filteredTickets.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-slate-500">
                      No tickets match the search criteria.
                    </td>
                  </tr>
                ) : (
                  filteredTickets.map((tkt) => {
                    const isIssued = tkt.status === 'ISSUED';
                    const isUsed = tkt.status === 'USED';
                    return (
                      <tr key={tkt.id} className="hover:bg-slate-800/40 transition-colors">
                        <td className="py-3.5 px-4 font-mono font-bold text-indigo-400">
                          {tkt.id}
                        </td>

                        <td className="py-3.5 px-4">
                          <div className="font-semibold text-white">{tkt.attendeeName}</div>
                          <div className="text-[11px] text-slate-400 font-mono">
                            {tkt.attendeeEmail || 'Buyer contact is available on the registration'}
                          </div>
                        </td>

                        <td className="py-3.5 px-4">
                          <div className="text-slate-200 truncate max-w-[150px]">
                            {tkt.eventName}
                          </div>
                          <div className="text-[11px] text-slate-400 font-mono">
                            {tkt.tierName}
                          </div>
                        </td>

                        <td className="py-3.5 px-4 font-mono text-[11px]">
                          <span
                            className={`font-semibold ${
                              isIssued
                                ? 'text-emerald-400'
                                : isUsed
                                ? 'text-amber-400'
                                : 'text-rose-400'
                            }`}
                          >
                            {tkt.status}
                          </span>
                        </td>

                        <td className="py-3.5 px-4 font-mono text-[11px] text-slate-300">
                          {tkt.source}
                        </td>

                        <td className="py-3.5 px-4 font-mono text-[11px] text-slate-400">
                          <div>Issued: {new Date(tkt.issuedAt).toLocaleDateString()}</div>
                          {tkt.usedAt && (
                            <div className="text-amber-300">
                              Used: {new Date(tkt.usedAt).toLocaleTimeString()} ({tkt.gate || 'Gate'})
                            </div>
                          )}
                        </td>

                        <td className="py-3.5 px-4 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <Link
                              to={`/ticket/${tkt.id}`}
                              className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
                              title="View digital pass"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                            </Link>

                            {isIssued && (
                              <button
                                onClick={() => {
                                  setCancelError('');
                                  setTicketToCancel(tkt);
                                }}
                                className="p-1.5 text-slate-400 hover:text-rose-400 rounded-lg hover:bg-slate-800 transition-colors cursor-pointer"
                                title="Revoke and cancel pass"
                              >
                                <Ban className="w-3.5 h-3.5" />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })
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

        {/* Cancellation Confirmation Modal */}
        <Modal
          isOpen={!!ticketToCancel}
          onClose={() => {
            setTicketToCancel(null);
            setCancelError('');
          }}
          title="Revoke &amp; Cancel Ticket"
          description="Confirm cancellation of this individual ticket."
        >
          {ticketToCancel && (
            <div className="space-y-4 text-xs">
              <div className="p-4 bg-rose-950/40 border border-rose-900/60 rounded-xl space-y-2">
                <p className="text-rose-300 font-semibold">
                  Are you sure you want to cancel ticket {ticketToCancel.id}?
                </p>
                <p className="text-slate-300">
                  This ticket for <strong className="text-white">{ticketToCancel.attendeeName}</strong> will change to CANCELLED. Used tickets cannot be cancelled.
                </p>
              </div>
              {cancelError && (
                <p role="alert" className="rounded-lg border border-rose-900/70 bg-rose-950/40 p-3 text-rose-200">
                  {cancelError}
                </p>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setTicketToCancel(null)}
                  disabled={isCancelling}
                  className="px-4 py-2 bg-slate-800 text-slate-300 hover:text-white rounded-lg cursor-pointer"
                >
                  Keep Ticket
                </button>

                <button
                  type="button"
                  onClick={handleConfirmCancel}
                  disabled={isCancelling}
                  className="px-5 py-2 bg-rose-600 hover:bg-rose-500 text-white font-bold rounded-lg cursor-pointer shadow-sm"
                >
                  {isCancelling ? 'Cancelling...' : 'Confirm Cancellation'}
                </button>
              </div>
            </div>
          )}
        </Modal>
      </div>
    </AdminLayout>
  );
};
