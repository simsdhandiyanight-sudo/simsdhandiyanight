import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, CreditCard, RefreshCw, XCircle } from 'lucide-react';
import {
  paymentReviewApi,
  type ManualPaymentProof,
  type PaymentReviewDashboard,
} from '../../api/paymentReview';
import { AdminLayout } from '../../components/admin/AdminLayout';

const count = (value: number | undefined) => (value ?? 0).toLocaleString();

export default function AdminPaymentReviewPage() {
  const [dashboard, setDashboard] = useState<PaymentReviewDashboard | null>(null);
  const [proofs, setProofs] = useState<ManualPaymentProof[]>([]);
  const [error, setError] = useState('');
  const [proofError, setProofError] = useState('');
  const [loading, setLoading] = useState(true);
  const [reconciling, setReconciling] = useState<string | null>(null);
  const [processingProof, setProcessingProof] = useState<string | null>(null);
  const [loadingScreenshot, setLoadingScreenshot] = useState<string | null>(null);
  const [activeScreenshot, setActiveScreenshot] = useState<{
    applicantName: string;
    url: string;
  } | null>(null);

  useEffect(
    () => () => {
      if (activeScreenshot) URL.revokeObjectURL(activeScreenshot.url);
    },
    [activeScreenshot],
  );

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

  const loadProofs = useCallback(async () => {
    setProofError('');
    try {
      const result = await paymentReviewApi.getProofDashboard();
      setProofs(result.proofs);
    } catch (loadError) {
      setProofError(
        loadError instanceof Error
          ? loadError.message
          : 'Unable to load manual payment proofs.',
      );
    }
  }, []);

  const reconcile = async (paymentId: string) => {
    setReconciling(paymentId);
    setError('');
    try {
      await paymentReviewApi.reconcile(paymentId);
      await loadDashboard();
    } catch (reconcileError) {
      setError(reconcileError instanceof Error ? reconcileError.message : 'Unable to reconcile this payment.');
    } finally {
      setReconciling(null);
    }
  };

  const approveProof = async (proof: ManualPaymentProof) => {
    const confirmed = window.confirm(
      `Have you confirmed receipt of UTR ${proof.utr_reference} and transaction ID ${proof.transaction_id} in bank/UPI records for ₹${(proof.expected_amount / 100).toFixed(2)}? Approving will issue the final QR ticket.`,
    );
    if (!confirmed) return;
    setProcessingProof(proof.payment_id);
    setProofError('');
    try {
      await paymentReviewApi.approveProof(proof.payment_id);
      await loadProofs();
    } catch (actionError) {
      setProofError(actionError instanceof Error ? actionError.message : 'Unable to approve this payment proof.');
    } finally {
      setProcessingProof(null);
    }
  };

  const rejectProof = async (proof: ManualPaymentProof) => {
    const reason = window.prompt('Enter the reason for rejecting this payment proof:');
    if (reason === null) return;
    if (!reason.trim()) {
      setProofError('A rejection reason is required.');
      return;
    }
    setProcessingProof(proof.payment_id);
    setProofError('');
    try {
      await paymentReviewApi.rejectProof(proof.payment_id, reason.trim());
      await loadProofs();
    } catch (actionError) {
      setProofError(actionError instanceof Error ? actionError.message : 'Unable to reject this payment proof.');
    } finally {
      setProcessingProof(null);
    }
  };

  const retryRejectionEmail = async (proof: ManualPaymentProof) => {
    setProcessingProof(proof.payment_id);
    setProofError('');
    try {
      await paymentReviewApi.retryProofRejectionEmail(proof.payment_id);
      await loadProofs();
    } catch (actionError) {
      setProofError(actionError instanceof Error ? actionError.message : 'Unable to retry the rejection email.');
    } finally {
      setProcessingProof(null);
    }
  };

  const viewProofScreenshot = async (proof: ManualPaymentProof) => {
    setLoadingScreenshot(proof.payment_id);
    setProofError('');
    try {
      const image = await paymentReviewApi.getProofScreenshot(proof.screenshot_url);
      setActiveScreenshot({
        applicantName: proof.applicant_name,
        url: URL.createObjectURL(image),
      });
    } catch (screenshotError) {
      setProofError(
        screenshotError instanceof Error
          ? screenshotError.message
          : 'Unable to load the private payment screenshot.',
      );
    } finally {
      setLoadingScreenshot(null);
    }
  };

  useEffect(() => {
    void loadDashboard();
    void loadProofs();
  }, [loadDashboard, loadProofs]);

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
        {proofError && (
          <div role="alert" className="rounded-xl border border-rose-800 bg-rose-950/40 p-4 text-sm text-rose-200">
            {proofError}
          </div>
        )}

        <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900">
          <div className="border-b border-slate-800 p-5">
            <h2 className="font-semibold text-white">Manual UPI payment proofs</h2>
            <p className="mt-1 text-xs leading-relaxed text-slate-400">
              Verify the actual incoming bank/UPI transaction and match its UTR and amount before approval. A screenshot alone is not proof of receipt.
            </p>
          </div>
          {proofs.length === 0 ? (
            <p className="p-5 text-sm text-slate-400">
              No manual payment proofs are currently recorded.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1200px] text-left text-xs">
                <thead className="bg-slate-950 text-[10px] uppercase tracking-wider text-slate-400">
                  <tr>
                    <th className="px-4 py-3">Applicant / registration</th>
                    <th className="px-4 py-3">Amount / payment references</th>
                    <th className="px-4 py-3">Screenshot</th>
                    <th className="px-4 py-3">Status / audit</th>
                    <th className="px-4 py-3">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {proofs.map((proof) => (
                    <tr key={proof.payment_id} className="align-top">
                      <td className="px-4 py-4">
                        <p className="font-semibold text-white">{proof.applicant_name}</p>
                        <p className="mt-1 text-slate-400">{proof.applicant_email}</p>
                        <p className="mt-1 text-slate-300">{proof.event_name} · {proof.ticket_tier_name}</p>
                        <p className="mt-1 font-mono text-[10px] text-indigo-300">
                          Ticket ID: {proof.ticket_id || 'Not assigned'} · Reg: {proof.registration_code}
                        </p>
                      </td>
                      <td className="px-4 py-4 text-slate-200">
                        <p>{proof.currency} {(proof.expected_amount / 100).toFixed(2)}</p>
                        <p className="mt-1 font-mono">UTR: {proof.utr_reference}</p>
                        <p className="mt-1 font-mono">Transaction ID: {proof.transaction_id}</p>
                        <p className="mt-1 text-[10px] text-slate-400">
                          Submitted: {new Date(proof.submitted_at).toLocaleString()}
                        </p>
                      </td>
                      <td className="px-4 py-4">
                        <button
                          type="button"
                          onClick={() => void viewProofScreenshot(proof)}
                          disabled={loadingScreenshot !== null}
                          className="text-indigo-300 underline disabled:opacity-50"
                        >
                          {loadingScreenshot === proof.payment_id ? 'Loading screenshot…' : 'View screenshot'}
                        </button>
                      </td>
                      <td className="px-4 py-4 text-slate-300">
                        <p>{proof.payment_status}</p>
                        {proof.verified_by && (
                          <p className="mt-1 text-[10px] text-emerald-300">
                            Approved by {proof.verified_by} · {proof.verified_at && new Date(proof.verified_at).toLocaleString()}
                          </p>
                        )}
                        {proof.rejected_by && (
                          <p className="mt-1 text-[10px] text-rose-300">
                            Rejected by {proof.rejected_by} · {proof.rejected_at && new Date(proof.rejected_at).toLocaleString()}
                          </p>
                        )}
                        {proof.rejection_reason && (
                          <p className="mt-1 max-w-xs text-[10px] text-rose-200">{proof.rejection_reason}</p>
                        )}
                        {proof.rejection_email_status && (
                          <p className="mt-1 text-[10px] text-slate-400">
                            Rejection email: {proof.rejection_email_status}
                          </p>
                        )}
                      </td>
                      <td className="space-y-2 px-4 py-4">
                        {proof.payment_status === 'PENDING_VERIFICATION' && (
                          <>
                            <button
                              type="button"
                              onClick={() => void approveProof(proof)}
                              disabled={processingProof !== null}
                              className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-700 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-600 disabled:opacity-50"
                            >
                              <CheckCircle2 className="h-3.5 w-3.5" />
                              Approve payment
                            </button>
                            <button
                              type="button"
                              onClick={() => void rejectProof(proof)}
                              disabled={processingProof !== null}
                              className="inline-flex items-center gap-1.5 rounded-lg bg-rose-900 px-3 py-2 text-xs font-semibold text-white hover:bg-rose-800 disabled:opacity-50"
                            >
                              <XCircle className="h-3.5 w-3.5" />
                              Reject
                            </button>
                          </>
                        )}
                        {proof.payment_status === 'REJECTED'
                          && proof.rejection_email_status === 'FAILED' && (
                            <button
                              type="button"
                              onClick={() => void retryRejectionEmail(proof)}
                              disabled={processingProof !== null}
                              className="rounded-lg border border-amber-700 px-3 py-2 text-xs text-amber-200 hover:bg-amber-950 disabled:opacity-50"
                            >
                              Retry rejection email
                            </button>
                          )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

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
              <h2 className="font-semibold text-white">Payments needing review</h2>
              <p className="text-xs text-slate-400">Unresolved PayU verification and captured payments needing registration or ticket recovery are listed here.</p>
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
                    <th className="px-4 py-3">Action</th>
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
                        <p className="mt-1">{payment.provider} · {payment.payment_status}</p>
                        {payment.provider_status && <p className="mt-1 text-[10px] text-slate-500">Gateway: {payment.provider_status}</p>}
                        <p className="mt-1 font-mono text-[10px] text-slate-500">{payment.order_id ?? payment.payment_id}</p>
                        {payment.provider_payment_id && <p className="mt-1 font-mono text-[10px] text-slate-500">Payment ref: {payment.provider_payment_id}</p>}
                        {payment.captured_at && <p className="mt-1 text-[10px] text-slate-500">Captured: {new Date(payment.captured_at).toLocaleString()}</p>}
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
                      <td className="px-4 py-4">
                        {payment.provider === 'PAYU' && (
                          <button
                            type="button"
                            onClick={() => void reconcile(payment.payment_id)}
                            disabled={reconciling !== null}
                            className="rounded-lg border border-indigo-700 bg-indigo-950 px-3 py-2 text-xs text-indigo-200 hover:bg-indigo-900 disabled:opacity-50"
                          >
                            {reconciling === payment.payment_id ? 'Reconciling…' : 'Retry verification'}
                          </button>
                        )}
                      </td>
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
                      <td className="px-4 py-4 font-mono text-slate-300">{registration.registration_code}</td>
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
        {activeScreenshot && (
          <div
            role="dialog"
            aria-modal="true"
            aria-label={`Payment screenshot for ${activeScreenshot.applicantName}`}
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4"
            onClick={() => setActiveScreenshot(null)}
          >
            <div
              className="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-2xl border border-slate-700 bg-slate-900 p-4"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="mb-3 flex items-center justify-between gap-4">
                <h2 className="font-semibold text-white">
                  Payment screenshot · {activeScreenshot.applicantName}
                </h2>
                <button
                  type="button"
                  onClick={() => setActiveScreenshot(null)}
                  className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-200 hover:bg-slate-800"
                >
                  Close
                </button>
              </div>
              <img
                src={activeScreenshot.url}
                alt={`Payment proof submitted by ${activeScreenshot.applicantName}`}
                className="mx-auto max-h-[75vh] max-w-full rounded-lg bg-white object-contain"
              />
            </div>
          </div>
        )}
      </div>
    </AdminLayout>
  );
}
