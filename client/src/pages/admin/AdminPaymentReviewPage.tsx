import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, CreditCard, RefreshCw } from 'lucide-react';
import {
  paymentReviewApi,
  type PaymentReviewDashboard,
} from '../../api/paymentReview';
import { AdminLayout } from '../../components/admin/AdminLayout';

const count = (value: number | undefined) => (value ?? 0).toLocaleString();

export default function AdminPaymentReviewPage() {
  const [dashboard, setDashboard] = useState<PaymentReviewDashboard | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const loadDashboard = useCallback(async () => {
    setError('');
    try {
      setDashboard(await paymentReviewApi.getDashboard());
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load payment review cases.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  const issueCounts = dashboard?.issue_counts ?? {};

  return (
    <AdminLayout
      title="Payment review"
      breadcrumbs={[{ label: 'Payment review' }]}
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
        <div className="rounded-xl border border-amber-800 bg-amber-950/40 p-4 text-sm text-amber-100">
          This page reports payment and ticket inconsistencies for authorized administrator review.
          The application supports payment verification only; it does not support refunds or settlement reversals.
        </div>
        {error && (
          <div role="alert" className="rounded-xl border border-rose-800 bg-rose-950/40 p-4 text-sm text-rose-200">
            {error}
          </div>
        )}

        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[
            ['Review required', issueCounts.PAYMENT_REVIEW_REQUIRED],
            ['Captured without tickets', issueCounts.PAYMENT_CAPTURED_WITHOUT_TICKET],
            ['Failed ticket issuance', issueCounts.TICKET_ISSUANCE_FAILED],
            ['Incomplete registration', issueCounts.PAYMENT_CAPTURED_WITH_INCOMPLETE_REGISTRATION],
            ['Duplicate captured payments', issueCounts.DUPLICATE_PAYMENT],
            ['Tickets without valid payment', issueCounts.TICKET_WITHOUT_VALID_PAYMENT],
          ].map(([label, value]) => (
            <div key={label} className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
              <p className="text-xs uppercase tracking-wider text-slate-400">{label}</p>
              <p className="mt-2 text-3xl font-bold text-white">{count(value as number | undefined)}</p>
            </div>
          ))}
        </section>

        <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900">
          <div className="flex items-center gap-3 border-b border-slate-800 p-5">
            <div className="rounded-lg bg-amber-950 p-2 text-amber-300"><CreditCard className="h-4 w-4" /></div>
            <div>
              <h2 className="font-semibold text-white">Captured payments needing review</h2>
              <p className="text-xs text-slate-400">Provider capture is retained even when registration or ticket issuance needs investigation.</p>
            </div>
          </div>
          {loading && !dashboard ? (
            <p className="p-6 text-sm text-slate-400">Loading payment review cases…</p>
          ) : dashboard?.payments.length ? (
            <div className="overflow-x-auto">
              {dashboard.has_more_payments && (
                <p className="border-b border-slate-800 bg-slate-950/50 px-4 py-3 text-xs text-amber-200">
                  Showing the latest 200 payment cases. Summary counts include all matching records.
                </p>
              )}
              <table className="w-full min-w-[1000px] text-left text-xs">
                <thead className="bg-slate-950 text-[10px] uppercase tracking-wider text-slate-400">
                  <tr>
                    <th className="px-4 py-3">Buyer / event</th>
                    <th className="px-4 py-3">Payment</th>
                    <th className="px-4 py-3">Tickets</th>
                    <th className="px-4 py-3">Issues</th>
                    <th className="px-4 py-3">Recorded failure</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {dashboard.payments.map((payment) => (
                    <tr key={payment.payment_id} className="align-top hover:bg-slate-800/30">
                      <td className="px-4 py-4">
                        <p className="font-semibold text-white">{payment.buyer_name}</p>
                        <p className="mt-1 text-slate-400">{payment.buyer_email}</p>
                        <p className="mt-1 text-slate-400">{payment.event_name} · {payment.ticket_tier_name}</p>
                      </td>
                      <td className="px-4 py-4 text-slate-300">
                        <p>{payment.currency} {(payment.amount / 100).toFixed(2)}</p>
                        <p className="mt-1 font-mono text-[10px] text-slate-500">{payment.order_id ?? payment.payment_id}</p>
                      </td>
                      <td className="px-4 py-4 text-slate-300">
                        {payment.ticket_count} / {payment.expected_ticket_count}
                        <p className="mt-1 text-[10px] text-slate-500">{payment.ticket_issuance_status}</p>
                      </td>
                      <td className="px-4 py-4">
                        <div className="flex flex-wrap gap-1.5">
                          {payment.issue_codes.map((issue) => (
                            <span key={issue} className="inline-flex items-center gap-1 rounded-full border border-amber-800 bg-amber-950/60 px-2 py-1 text-[10px] text-amber-200">
                              <AlertTriangle className="h-3 w-3" />
                              {issue}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="max-w-sm px-4 py-4 text-slate-300">{payment.failure || 'No failure detail recorded.'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="p-6 text-sm text-slate-400">No captured payment inconsistencies are currently reported.</p>
          )}
        </section>

        <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900">
          <div className="border-b border-slate-800 p-5">
            <h2 className="font-semibold text-white">Online tickets without a verified payment</h2>
            <p className="text-xs text-slate-400">Online registration records must be linked to a captured, verified payment with successful ticket issuance.</p>
          </div>
          {dashboard?.registrations_without_valid_payment.length ? (
            <div className="overflow-x-auto">
              {dashboard.has_more_registrations && (
                <p className="border-b border-slate-800 bg-slate-950/50 px-4 py-3 text-xs text-amber-200">
                  Showing the latest 200 registration cases. Summary counts include all matching records.
                </p>
              )}
              <table className="w-full min-w-[800px] text-left text-xs">
                <thead className="bg-slate-950 text-[10px] uppercase tracking-wider text-slate-400">
                  <tr>
                    <th className="px-4 py-3">Registration</th>
                    <th className="px-4 py-3">Buyer</th>
                    <th className="px-4 py-3">Event / offer</th>
                    <th className="px-4 py-3">Tickets</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {dashboard.registrations_without_valid_payment.map((registration) => (
                    <tr key={registration.registration_id} className="align-top hover:bg-slate-800/30">
                      <td className="px-4 py-4 font-mono text-slate-300">{registration.registration_id}</td>
                      <td className="px-4 py-4 text-slate-300">
                        <p className="font-semibold text-white">{registration.buyer_name}</p>
                        <p className="mt-1 text-slate-400">{registration.buyer_email}</p>
                      </td>
                      <td className="px-4 py-4 text-slate-300">{registration.event_name} · {registration.ticket_tier_name}</td>
                      <td className="px-4 py-4 text-slate-300">{registration.ticket_count} / {registration.expected_ticket_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="p-6 text-sm text-slate-400">No online ticket records without a verified payment are currently reported.</p>
          )}
        </section>
      </div>
    </AdminLayout>
  );
}
