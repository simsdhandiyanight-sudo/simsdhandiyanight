import { useCallback, useEffect, useState } from 'react';
import { Mail, RefreshCw, RotateCcw } from 'lucide-react';
import {
  emailDeliveryApi,
  type EmailDeliveryDashboard,
  type EmailDeliveryRecord,
  type EmailPriority,
} from '../../api/emailDelivery';
import { AdminLayout } from '../../components/admin/AdminLayout';

const priorities: EmailPriority[] = ['STAFF', 'COMPLIMENTARY', 'REGULAR'];

const formatCount = (value: number | undefined) => (value ?? 0).toLocaleString();

export default function AdminEmailDeliveryPage() {
  const [dashboard, setDashboard] = useState<EmailDeliveryDashboard | null>(null);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState('');
  const [loading, setLoading] = useState(true);

  const loadDashboard = useCallback(async () => {
    setError('');
    try {
      setDashboard(await emailDeliveryApi.getDashboard());
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load email delivery.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  const runAction = async (record: EmailDeliveryRecord, action: 'retry' | EmailPriority) => {
    setBusyId(record.id);
    setError('');
    try {
      if (action === 'retry') {
        await emailDeliveryApi.retry(record.id);
      } else {
        await emailDeliveryApi.updatePriority(record.id, action);
      }
      await loadDashboard();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Unable to update email delivery.');
    } finally {
      setBusyId('');
    }
  };

  const quota = dashboard?.quota;

  return (
    <AdminLayout
      title="Ticket email delivery"
      breadcrumbs={[{ label: 'Email delivery' }]}
      actions={
        <button
          type="button"
          onClick={() => void loadDashboard()}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      }
    >
      <div className="space-y-6">
        {error && (
          <div role="alert" className="rounded-xl border border-rose-800 bg-rose-950/40 p-4 text-sm text-rose-200">
            {error}
          </div>
        )}
        {dashboard && !dashboard.provider_configured && (
          <div role="status" className="rounded-xl border border-amber-800 bg-amber-950/40 p-4 text-sm text-amber-200">
            Brevo is not configured. Queue processing will remain paused until the API key and sender address are set.
          </div>
        )}

        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[
            ['All ticket emails', dashboard?.total_ticket_emails],
            ['Pending', dashboard?.statuses.PENDING],
            ['Sent today', quota?.total_sent],
            ['Failed', dashboard?.statuses.FAILED],
          ].map(([label, count]) => (
            <div key={label} className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
              <p className="text-xs uppercase tracking-wider text-slate-400">{label}</p>
              <p className="mt-2 text-3xl font-bold text-white">{formatCount(count as number | undefined)}</p>
            </div>
          ))}
        </section>

        {quota && (
          <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-semibold text-white">Daily Brevo allocation</h2>
                <p className="mt-1 text-xs text-slate-400">Quota and accepted sends for {quota.date}</p>
              </div>
              <span className="rounded-full border border-indigo-800 bg-indigo-950 px-3 py-1 text-xs text-indigo-200">
                {formatCount(quota.total_sent)} / {formatCount(quota.brevo_limit)} sent
              </span>
            </div>
            <div className="mt-5 grid gap-4 md:grid-cols-2">
              {[
                {
                  label: 'Regular allocation',
                  sent: quota.regular_sent,
                  reserved: quota.regular_reserved,
                  total: quota.regular_allocation,
                  remaining: quota.remaining_regular,
                },
                {
                  label: 'Staff / complimentary allocation',
                  sent: quota.priority_sent,
                  reserved: quota.priority_reserved,
                  total: quota.priority_allocation,
                  remaining: quota.remaining_priority,
                },
              ].map((item) => (
                <div key={item.label} className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                  <div className="flex justify-between gap-2 text-sm">
                    <span className="text-slate-200">{item.label}</span>
                    <span className="font-mono text-white">{item.sent} / {item.total}</span>
                  </div>
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-800">
                    <div
                      className="h-full rounded-full bg-indigo-500"
                      style={{ width: `${Math.min(100, (item.sent / item.total) * 100)}%` }}
                    />
                  </div>
                  <p className="mt-2 text-xs text-slate-400">
                    {item.reserved} reserved · {item.remaining} available
                  </p>
                </div>
              ))}
            </div>
          </section>
        )}

        <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900">
          <div className="flex items-center gap-3 border-b border-slate-800 p-5">
            <div className="rounded-lg bg-indigo-950 p-2 text-indigo-300"><Mail className="h-4 w-4" /></div>
            <div>
              <h2 className="font-semibold text-white">Ticket delivery queue</h2>
              <p className="text-xs text-slate-400">Each queue item sends one ticket and its individual PDF.</p>
            </div>
          </div>
          {loading && !dashboard ? (
            <p className="p-6 text-sm text-slate-400">Loading delivery queue…</p>
          ) : dashboard?.queue.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1080px] text-left text-xs">
                <thead className="bg-slate-950 text-[10px] uppercase tracking-wider text-slate-400">
                  <tr>
                    <th className="px-4 py-3">Attendee / event</th>
                    <th className="px-4 py-3">Recipient</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Priority</th>
                    <th className="px-4 py-3">Attempts / provider ID</th>
                    <th className="px-4 py-3">Created / last attempt</th>
                    <th className="px-4 py-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {dashboard.queue.map((record) => (
                    <tr key={record.id} className="align-top hover:bg-slate-800/30">
                      <td className="px-4 py-4">
                        <p className="font-semibold text-white">{record.attendee_name}</p>
                        <p className="mt-1 text-slate-400">{record.event_name} · {record.ticket_id}</p>
                      </td>
                      <td className="px-4 py-4 text-slate-300">{record.recipient}</td>
                      <td className="px-4 py-4">
                        <span className="rounded-full border border-slate-700 px-2 py-1 font-mono text-[10px] text-slate-200">
                          {record.status}
                        </span>
                        {record.failure_reason && <p className="mt-2 max-w-xs text-rose-300">{record.failure_reason}</p>}
                        {record.status === 'RECONCILIATION_REQUIRED' && (
                          <p className="mt-2 max-w-xs text-amber-200">
                            Check Brevo before any manual action. Automatic retry is blocked to prevent duplicates.
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-4">
                        <select
                          aria-label={`Priority for ${record.attendee_name}`}
                          value={record.priority}
                          disabled={busyId === record.id || !['PENDING', 'FAILED'].includes(record.status)}
                          onChange={(event) => void runAction(record, event.target.value as EmailPriority)}
                          className="rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-200 disabled:opacity-50"
                        >
                          {priorities.map((priority) => <option key={priority} value={priority}>{priority}</option>)}
                        </select>
                      </td>
                      <td className="px-4 py-4 text-slate-400">
                        <p>{record.attempt_count}</p>
                        {record.provider_message_id && <p className="mt-1 max-w-[180px] break-all font-mono text-[10px]">{record.provider_message_id}</p>}
                      </td>
                      <td className="px-4 py-4 text-slate-400">
                        <p>{new Date(record.created_at).toLocaleString()}</p>
                        <p className="mt-1">
                          {record.last_attempt_at
                            ? new Date(record.last_attempt_at).toLocaleString()
                            : 'Not attempted'}
                        </p>
                      </td>
                      <td className="px-4 py-4 text-right">
                        {record.status === 'FAILED' && (
                          <button
                            type="button"
                            disabled={busyId === record.id}
                            onClick={() => void runAction(record, 'retry')}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 px-2.5 py-1.5 text-slate-200 hover:bg-slate-800 disabled:opacity-50"
                          >
                            <RotateCcw className="h-3 w-3" /> Retry
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="border-t border-slate-800 px-4 py-3 text-[11px] text-slate-500">
                Showing the most recently updated 100 ticket email records.
              </p>
            </div>
          ) : (
            <p className="p-6 text-sm text-slate-400">No ticket emails are in the queue yet.</p>
          )}
        </section>
      </div>
    </AdminLayout>
  );
}
