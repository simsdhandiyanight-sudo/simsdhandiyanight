import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { eventsApi, FEATURED_EVENT_SLUG } from '../../api/events';
import { registrationsApi } from '../../api/registrations';
import { Registration } from '../../types';
import { AdminLayout } from '../../components/admin/AdminLayout';
import { Modal } from '../../components/common/Modal';
import {
  Search,
  Eye,
  ExternalLink,
  Smartphone,
  Globe,
} from 'lucide-react';

export const AdminRegistrationsPage: React.FC = () => {
  const [registrations, setRegistrations] = useState<Registration[]>([]);
  const [page, setPage] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [loadError, setLoadError] = useState('');
  // Filters
  const [search, setSearch] = useState('');
  const [sourceFilter, setSourceFilter] = useState<'all' | 'ONLINE' | 'ON_SPOT'>('all');
  const [statusFilter, setStatusFilter] = useState<'all' | 'REGISTERED'>('all');

  // Inspection Modal
  const [selectedReg, setSelectedReg] = useState<Registration | null>(null);

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(async () => {
      setLoadError('');
      try {
        const event = await eventsApi.getAdminContext(FEATURED_EVENT_SLUG);
        const response = await registrationsApi.getPage({
          page,
          eventId: event.id,
          source: sourceFilter === 'all' ? undefined : sourceFilter,
          search,
        });
        if (active) {
          setRegistrations(response.results);
          setTotalCount(response.count);
          setPageCount(Math.ceil(response.count / 50));
        }
      } catch (error) {
        if (active) setLoadError(error instanceof Error ? error.message : 'Unable to load registrations.');
      }
    }, 200);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [page, search, sourceFilter]);

  const filteredRegistrations = registrations.filter((r) => {
    const matchesSearch = !search.trim() || 
      r.id.toLowerCase().includes(search.toLowerCase()) ||
      r.attendee.fullName.toLowerCase().includes(search.toLowerCase()) ||
      r.attendee.email.toLowerCase().includes(search.toLowerCase()) ||
      r.attendee.phone.includes(search);
    const matchesStatus = statusFilter === 'all' || r.status === statusFilter;

    return matchesSearch && matchesStatus;
  });

  return (
    <AdminLayout
      title="Registrations Management"
      breadcrumbs={[{ label: 'Registrations' }]}
    >
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h2 className="text-xl font-bold font-display text-white">Attendee Registrations</h2>
            <p className="text-xs text-slate-400">
              Audit registration ledger, verify sources, and monitor admission tickets.
            </p>
          </div>
          <span className="text-xs font-mono text-slate-500">
            {totalCount} Records Found
          </span>
        </div>
        {loadError && (
          <p role="alert" className="rounded-xl border border-rose-900/70 bg-rose-950/40 p-3 text-xs text-rose-200">{loadError}</p>
        )}

        {/* Filters Toolbar */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
          {/* Search */}
          <div className="relative">
            <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search ID, name, email..."
              className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-10 pr-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          {/* Source Filter */}
          <div>
            <select
              value={sourceFilter}
              onChange={(e) => {
                setSourceFilter(e.target.value as 'all' | 'ONLINE' | 'ON_SPOT');
                setPage(1);
              }}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
            >
              <option value="all">All Channels (Online + Desk)</option>
              <option value="ONLINE">Online Pre-Registration</option>
              <option value="ON_SPOT">Venue On-Spot Kiosk</option>
            </select>
          </div>

          {/* Status Filter */}
          <div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as 'all' | 'REGISTERED')}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
            >
              <option value="all">All Statuses</option>
              <option value="REGISTERED">REGISTERED</option>
            </select>
          </div>
        </div>

        {/* Data Table */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950 border-b border-slate-800 text-slate-400 uppercase font-mono text-[10px]">
                <tr>
                  <th className="py-3 px-4">Registration ID</th>
                  <th className="py-3 px-4">Attendee</th>
                  <th className="py-3 px-4">Event &bull; Tier</th>
                  <th className="py-3 px-4">Contact</th>
                  <th className="py-3 px-4">Source</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {filteredRegistrations.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-slate-500">
                      No registrations match the selected filters.
                    </td>
                  </tr>
                ) : (
                  filteredRegistrations.map((reg) => (
                    <tr key={reg.id} className="hover:bg-slate-800/40 transition-colors">
                      <td className="py-3.5 px-4 font-mono font-semibold text-indigo-400">
                        {reg.id}
                      </td>

                      <td className="py-3.5 px-4">
                        <div className="font-semibold text-white">{reg.attendee.fullName}</div>
                        {reg.attendee.organization && (
                          <div className="text-[11px] text-slate-400">
                            {reg.attendee.organization}
                          </div>
                        )}
                      </td>

                      <td className="py-3.5 px-4">
                        <div className="text-slate-200 truncate max-w-[150px]">{reg.eventName}</div>
                        <div className="text-[11px] text-indigo-300 font-mono">{reg.tierName}</div>
                        {(reg.ticketIds?.length ?? 1) > 1 && (
                          <div className="text-[10px] text-slate-500">{reg.ticketIds?.length} admissions</div>
                        )}
                      </td>

                      <td className="py-3.5 px-4 font-mono text-[11px] text-slate-400">
                        <div>{reg.attendee.email}</div>
                        <div>{reg.attendee.phone}</div>
                      </td>

                      <td className="py-3.5 px-4 font-mono">
                        <span
                          className={`inline-flex items-center gap-1 text-[11px] ${
                            reg.source === 'ONLINE' ? 'text-indigo-400' : 'text-emerald-400'
                          }`}
                        >
                          {reg.source === 'ONLINE' ? (
                            <Globe className="w-3 h-3" />
                          ) : (
                            <Smartphone className="w-3 h-3" />
                          )}
                          <span>{reg.source}</span>
                        </span>
                      </td>

                      <td className="py-3.5 px-4 font-mono text-[11px]">
                        <span
                          className={
                            'text-emerald-400 font-semibold'
                          }
                        >
                          {reg.status}
                        </span>
                      </td>

                      <td className="py-3.5 px-4 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => setSelectedReg(reg)}
                            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors cursor-pointer"
                            title="Inspect registration details"
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </button>
                          <Link
                            to={`/ticket/${reg.ticketId}`}
                            className="p-1.5 text-indigo-400 hover:text-indigo-300 rounded-lg hover:bg-slate-800 transition-colors"
                            title="Open digital pass"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </Link>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between border-t border-slate-800 px-4 py-3 text-xs text-slate-400">
            <span>Page {page} of {Math.max(1, pageCount)}</span>
            <div className="flex gap-2">
              <button disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))} className="rounded-lg border border-slate-700 px-3 py-1.5 disabled:opacity-40">Previous</button>
              <button disabled={page >= pageCount} onClick={() => setPage((value) => value + 1)} className="rounded-lg border border-slate-700 px-3 py-1.5 disabled:opacity-40">Next</button>
            </div>
          </div>
        </div>

        {/* Registration Inspection Modal */}
        <Modal
          isOpen={!!selectedReg}
          onClose={() => setSelectedReg(null)}
          title="Registration Details"
          description={selectedReg ? `Manifest entry for ${selectedReg.id}` : ''}
        >
          {selectedReg && (
            <div className="space-y-4 text-xs">
              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-3">
                <div className="flex justify-between items-center pb-2 border-b border-slate-800">
                  <span className="text-slate-400 uppercase font-semibold">ATTENDEE</span>
                  <span className="text-sm font-bold text-white">
                    {selectedReg.attendee.fullName}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <span className="text-slate-500 block">Email</span>
                    <span className="font-mono text-slate-200">{selectedReg.attendee.email}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Phone</span>
                    <span className="font-mono text-slate-200">{selectedReg.attendee.phone}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Organization</span>
                    <span className="text-slate-200">
                      {selectedReg.attendee.organization || 'Independent'}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Role</span>
                    <span className="text-slate-200">
                      {selectedReg.attendee.jobTitle || 'Attendee'}
                    </span>
                  </div>
                </div>
              </div>

              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-2">
                <div className="flex justify-between">
                  <span className="text-slate-400">Event</span>
                  <span className="text-white font-semibold">{selectedReg.eventName}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Pass Tier</span>
                  <span className="text-indigo-400 font-mono">{selectedReg.tierName}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Channel Source</span>
                  <span className="font-mono text-emerald-400">{selectedReg.source}</span>
                </div>
                <div>
                  <span className="mb-1 block text-slate-400">
                    Ticket IDs ({selectedReg.ticketIds?.length ?? 1})
                  </span>
                  <div className="space-y-1">
                    {(selectedReg.ticketIds ?? [selectedReg.ticketId]).map((ticketId) => (
                      <Link
                        key={ticketId}
                        to={`/ticket/${ticketId}`}
                        className="block break-all font-mono text-xs font-bold text-indigo-300 hover:text-indigo-200"
                      >
                        {ticketId}
                      </Link>
                    ))}
                  </div>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Registration Timestamp</span>
                  <span className="font-mono text-slate-400">
                    {new Date(selectedReg.createdAt).toLocaleString()}
                  </span>
                </div>
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <button
                  onClick={() => setSelectedReg(null)}
                  className="px-4 py-2 bg-slate-800 text-slate-300 hover:text-white rounded-lg cursor-pointer"
                >
                  Close
                </button>
                <Link
                  to={`/ticket/${selectedReg.ticketId}`}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-lg inline-flex items-center gap-1.5"
                >
                  <span>Open Ticket</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>
          )}
        </Modal>
      </div>
    </AdminLayout>
  );
};
