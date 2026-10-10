import React, { useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowRight, CheckCircle2, Clock3, Download, Ticket as TicketIcon } from 'lucide-react';
import { ApiError, apiBlob } from '../../api/http';
import { paymentsApi, type PaymentProofStatusResponse } from '../../api/payments';
import { mapRegistration, mapTicket } from '../../api/serializers';
import { Navbar } from '../../components/common/Navbar';
import { Footer } from '../../components/common/Footer';
import { FestivalMotifs } from '../../components/common/FestivalMotifs';
import { DigitalTicket } from '../../components/ticket/DigitalTicket';
import { Registration, Ticket } from '../../types';

const ManualPaymentProofPage: React.FC<{
  registrationId: string;
  accessToken: string;
}> = ({ registrationId, accessToken }) => {
  const [details, setDetails] = useState<PaymentProofStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [downloadError, setDownloadError] = useState('');
  const [error, setError] = useState('');
  const [utrReference, setUtrReference] = useState('');
  const [transactionId, setTransactionId] = useState('');
  const [screenshot, setScreenshot] = useState<File | null>(null);

  const refresh = useCallback(async () => {
    setError('');
    try {
      setDetails(await paymentsApi.proofStatus(registrationId, accessToken));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load your payment status.');
    } finally {
      setLoading(false);
    }
  }, [registrationId, accessToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (
      !details
      || !(
        details.payment_status === 'PENDING_VERIFICATION'
        || (details.payment_status === 'VERIFIED' && details.email_status === 'PENDING')
      )
    ) {
      return undefined;
    }
    const interval = window.setInterval(() => void refresh(), 15000);
    return () => window.clearInterval(interval);
  }, [details?.payment_status, details?.email_status, refresh]);

  const submitProof = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!screenshot) {
      setError('Please select your payment screenshot.');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const result = await paymentsApi.submitProof(
        registrationId,
        accessToken,
        utrReference.trim(),
        transactionId.trim(),
        screenshot,
        crypto.randomUUID(),
      );
      setDetails(result);
      setUtrReference('');
      setTransactionId('');
      setScreenshot(null);
      const input = document.getElementById('payment-proof-screenshot') as HTMLInputElement | null;
      if (input) input.value = '';
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Unable to submit payment proof.');
    } finally {
      setSubmitting(false);
    }
  };

  const downloadTicketId = async () => {
    if (!details) return;
    setDownloadError('');
    try {
      const file = await apiBlob(
        paymentsApi.proofConfirmationUrl(registrationId),
        { headers: { 'X-Proof-Access-Token': accessToken } },
      );
      const url = URL.createObjectURL(file);
      const link = document.createElement('a');
      link.href = url;
      link.download = `ticket-id-${details.ticket_id || details.registration_code}.pdf`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (downloadFailure) {
      setDownloadError(
        downloadFailure instanceof Error
          ? downloadFailure.message
          : 'Ticket ID confirmation could not be downloaded.',
      );
    }
  };

  const paymentPending = details?.payment_status === 'PENDING_VERIFICATION';
  const paymentRejected = details?.payment_status === 'REJECTED';
  const paymentVerified = details?.payment_status === 'VERIFIED';
  const canSubmitProof = details?.can_submit_proof === true;
  const submitted = Boolean(details?.ticket_id);

  return (
    <div className="festival-public flex min-h-screen flex-col bg-slate-950 text-slate-100">
      <Navbar />
      <main className="festival-hero mx-auto w-full max-w-3xl flex-1 px-4 pb-24 pt-32 sm:px-6">
        <FestivalMotifs />
        {loading ? (
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-8 text-center text-sm text-slate-300">
            Loading your secure payment page…
          </div>
        ) : !details ? (
          <div role="alert" className="rounded-2xl border border-rose-800 bg-rose-950/40 p-6 text-sm text-rose-200">
            {error || 'This registration link is invalid or unavailable.'}
          </div>
        ) : (
          <div className="space-y-6">
            <header className="rounded-2xl border border-slate-800 bg-slate-900 p-6 text-center sm:p-8">
              <Clock3 className="mx-auto mb-4 h-10 w-10 text-amber-300" />
              <p className="font-mono text-xs font-bold uppercase tracking-wider text-indigo-300">
                {details.event_name}
              </p>
              <h1 className="mt-2 font-display text-2xl font-bold text-white">
                {paymentPending
                  ? 'Payment proof received'
                  : paymentRejected
                    ? 'Payment proof needs correction'
                    : paymentVerified
                      ? 'Payment verified'
                      : 'Complete your UPI payment'}
              </h1>
              <p className="mt-2 text-sm text-slate-300">
                Applicant: <strong>{details.applicant_name}</strong>
              </p>
              <p className="mt-1 text-sm text-slate-300">
                Registered email: <strong>{details.applicant_email}</strong>
              </p>
              <p className="mt-3 text-2xl font-bold text-white">
                {details.currency} {details.amount.toFixed(2)}
              </p>
              {submitted && (
                <p className="mt-3 break-all font-mono text-sm font-bold text-indigo-300">
                  Ticket ID: {details.ticket_id}
                </p>
              )}
            </header>

            {paymentPending && (
              <section className="rounded-2xl border border-amber-300 bg-amber-50 p-6 text-sm leading-relaxed text-amber-950">
                <p>
                  Your payment proof has been submitted successfully. Your Ticket ID is{' '}
                  <strong>{details.ticket_id}</strong>. Please save this ID for future reference.
                  Your payment is awaiting admin verification. Your final admission ticket,
                  including its QR code, will be sent to your registered email address after
                  successful verification.
                </p>
                <p className="mt-3 text-xs text-amber-900">
                  The Ticket ID is only a tracking/reference identifier. It does not confirm
                  payment, guarantee admission, or authorize event entry.
                </p>
              </section>
            )}

            {paymentRejected && (
              <section className="rounded-2xl border border-rose-800 bg-rose-950/30 p-6 text-sm text-rose-100">
                <h2 className="font-semibold">Your proof was not approved</h2>
                <p className="mt-2">Reason: {details.rejection_reason}</p>
                {details.rejection_deadline && (
                  <p className="mt-2 text-xs text-rose-200">
                    Submit corrected proof before{' '}
                    {new Date(details.rejection_deadline).toLocaleString()}.
                  </p>
                )}
                <p className="mt-2 text-xs text-rose-200">
                  Your existing Ticket ID remains the same. It is not an entry pass.
                </p>
              </section>
            )}

            {paymentVerified && (
              <section className="rounded-2xl border border-emerald-800 bg-emerald-950/30 p-6 text-sm text-emerald-100">
                <p>Payment verified. Email delivery status: {details.email_status || 'PENDING'}.</p>
                {details.email_status === 'SENT' ? (
                  <p className="mt-2">
                    The email service accepted your final admission ticket for delivery to your
                    registered email address. Present the QR code in that ticket for entry.
                  </p>
                ) : details.email_status === 'FAILED' ? (
                  <p className="mt-2">
                    Payment remains verified, but the email could not be sent. The event team can
                    retry delivery without issuing another ticket.
                  </p>
                ) : (
                  <p className="mt-2">
                    Your final admission ticket is queued for delivery to your registered email
                    address. Do not use the Ticket ID confirmation for entry.
                  </p>
                )}
              </section>
            )}

            {!canSubmitProof
              && !paymentPending
              && !paymentRejected
              && !paymentVerified
              && details.registration_status === 'EXPIRED' && (
                <section className="rounded-2xl border border-rose-800 bg-rose-950/30 p-6 text-sm text-rose-100">
                  This reservation has expired and the inventory was released. Please start a new
                  registration if tickets are still available.
                  <Link to="/register" className="mt-4 inline-flex rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white">
                    Start a new registration
                  </Link>
                </section>
              )}

            {canSubmitProof && (
              <section className="grid gap-6 rounded-2xl border border-slate-800 bg-slate-900 p-6 md:grid-cols-2">
                <div className="space-y-3">
                  <h2 className="text-lg font-semibold text-white">Pay by UPI</h2>
                  <p className="text-sm text-slate-300">
                    Scan this QR code and pay the exact amount displayed for your pass.
                  </p>
                  <img
                    src={details.upi_qr_image_url}
                    alt="Configured UPI payment QR code"
                    className="mx-auto max-h-64 rounded-xl bg-white p-2"
                  />
                  <p className="text-xs text-slate-400">
                    Your reservation expires at{' '}
                    {details.reservation_expires_at
                      ? new Date(details.reservation_expires_at).toLocaleString()
                      : 'the displayed deadline'}.
                  </p>
                </div>

                <form className="space-y-4" onSubmit={submitProof}>
                  <h2 className="text-lg font-semibold text-white">Submit payment proof</h2>
                  <label className="block text-sm text-slate-300" htmlFor="payment-utr">
                    UTR
                  </label>
                  <input
                    id="payment-utr"
                    required
                    minLength={6}
                    maxLength={40}
                    value={utrReference}
                    onChange={(event) => setUtrReference(event.target.value)}
                    className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                  />
                  <label className="block text-sm text-slate-300" htmlFor="payment-transaction-id">
                    Transaction ID
                  </label>
                  <input
                    id="payment-transaction-id"
                    required
                    minLength={6}
                    maxLength={40}
                    value={transactionId}
                    onChange={(event) => setTransactionId(event.target.value)}
                    className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                  />
                  <label className="block text-sm text-slate-300" htmlFor="payment-proof-screenshot">
                    Payment screenshot (JPEG, PNG, or WebP; max 5 MB)
                  </label>
                  <input
                    id="payment-proof-screenshot"
                    type="file"
                    required
                    accept="image/jpeg,image/png,image/webp"
                    onChange={(event) => setScreenshot(event.target.files?.[0] || null)}
                    className="block w-full text-xs text-slate-300 file:mr-3 file:rounded-lg file:border-0 file:bg-indigo-600 file:px-3 file:py-2 file:text-white"
                  />
                  <p className="text-xs text-slate-400">
                    Payment is not confirmed by uploading a screenshot. An administrator checks
                    the actual transaction before issuing your final ticket.
                  </p>
                  {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
                  <button
                    type="submit"
                    disabled={submitting || !screenshot}
                    className="w-full rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white hover:bg-indigo-500 disabled:cursor-wait disabled:opacity-50"
                  >
                    {submitting
                      ? 'Submitting proof…'
                      : paymentRejected
                        ? 'Submit corrected proof'
                        : 'Submit payment proof'}
                  </button>
                </form>
              </section>
            )}

            {submitted && (
              <section className="space-y-3">
                <button
                  type="button"
                  onClick={() => void downloadTicketId()}
                  className="flex w-full items-center justify-center gap-2 rounded-xl border border-indigo-500/40 bg-indigo-600/20 px-4 py-3 text-sm font-semibold text-indigo-100 hover:bg-indigo-600/30"
                >
                  <Download className="h-4 w-4" />
                  Download Ticket ID
                </button>
                {downloadError && (
                  <p role="alert" className="text-center text-xs text-rose-300">{downloadError}</p>
                )}
              </section>
            )}

            {error && !canSubmitProof && (
              <p role="alert" className="rounded-xl border border-rose-800 bg-rose-950/40 p-3 text-sm text-rose-200">
                {error}
              </p>
            )}
            <button
              type="button"
              onClick={() => void refresh()}
              className="mx-auto block rounded-lg border border-slate-700 px-4 py-2 text-xs text-slate-300 hover:bg-slate-800"
            >
              Refresh payment status
            </button>
          </div>
        )}
      </main>
      <Footer />
    </div>
  );
};

const PayURegistrationSuccessPage: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const state = location.state as {
    registration?: Registration;
    ticket?: Ticket;
    tickets?: Ticket[];
  } | undefined;
  const registration = state?.registration;
  const ticket = state?.ticket;
  const tickets = state?.tickets ?? (ticket ? [ticket] : []);
  const txnid = searchParams.get('txnid') || '';
  const [paymentMessage, setPaymentMessage] = useState(
    'Payment is still being confirmed by PayU. No final ticket is available yet.',
  );

  useEffect(() => {
    if (!txnid || registration) return;
    let active = true;
    let refreshing = false;
    const refresh = async () => {
      if (refreshing) return;
      refreshing = true;
      try {
        const idempotencyKey = sessionStorage.getItem(
          `ticketing.payment-idempotency.${txnid}`,
        );
        if (!idempotencyKey) {
          setPaymentMessage('This payment cannot be verified in this browser session. Contact the event team.');
          return;
        }
        const payment = await paymentsApi.status(txnid, idempotencyKey);
        if (!active) return;
        if (payment.payment_verified && payment.registration && payment.tickets) {
          const confirmedTickets = payment.tickets.map(mapTicket);
          navigate('/registration/success', {
            replace: true,
            state: {
              registration: mapRegistration(payment.registration),
              ticket: confirmedTickets[0],
              tickets: confirmedTickets,
            },
          });
        } else if (payment.payment_status === 'FAILED') {
          setPaymentMessage('PayU reported that this payment failed or was cancelled. No tickets have been issued.');
        } else {
          setPaymentMessage(
            payment.verification_message
              || 'Payment is still being confirmed. Do not pay again while it is processing.',
          );
        }
      } catch (error) {
        if (!active) return;
        setPaymentMessage(
          error instanceof ApiError
            ? error.message
            : 'Payment status could not be checked. Please try again.',
        );
      } finally {
        refreshing = false;
      }
    };
    void refresh();
    const interval = window.setInterval(() => void refresh(), 5000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [txnid, registration, navigate]);

  return (
    <div className="festival-public flex min-h-screen flex-col bg-slate-950 text-slate-100">
      <Navbar />
      <main className="festival-hero mx-auto w-full max-w-4xl flex-1 px-4 pb-24 pt-32 sm:px-6">
        <FestivalMotifs />
        {registration && ticket ? (
          <>
            <header className="mb-8 text-center">
              <CheckCircle2 className="mx-auto mb-4 h-12 w-12 text-emerald-400" />
              <h1 className="font-display text-3xl font-bold text-white">Registration confirmed</h1>
              <p className="mt-2 text-sm text-slate-300">Payment verified. Present the final ticket QR code at entry.</p>
              <p className="mt-3 font-mono text-xs text-slate-400">
                Registration: {registration.registrationCode || registration.id}
              </p>
            </header>
            <div className="space-y-8">
              {tickets.map((issuedTicket) => (
                <DigitalTicket key={issuedTicket.id} ticket={issuedTicket} showActions />
              ))}
            </div>
          </>
        ) : txnid ? (
          <section className="mx-auto max-w-lg rounded-2xl border border-slate-800 bg-slate-900 p-8 text-center">
            <Clock3 className="mx-auto mb-4 h-10 w-10 text-amber-300" />
            <h1 className="font-display text-2xl font-bold text-white">Payment confirmation</h1>
            <p role="status" className="mt-3 text-sm leading-relaxed text-slate-300">{paymentMessage}</p>
            <p className="mt-4 break-all font-mono text-xs text-slate-500">Transaction: {txnid}</p>
          </section>
        ) : (
          <section className="mx-auto max-w-lg rounded-2xl border border-slate-800 bg-slate-900 p-8 text-center">
            <TicketIcon className="mx-auto mb-4 h-10 w-10 text-indigo-300" />
            <h1 className="font-display text-2xl font-bold text-white">No registration confirmation found</h1>
            <p className="mt-2 text-sm leading-relaxed text-slate-400">
              Use the secure payment link from your registration to view status and submit proof.
            </p>
            <Link
              to="/events"
              className="mt-6 inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white hover:bg-indigo-500"
            >
              Back to Dhandiya Night <ArrowRight className="h-4 w-4" />
            </Link>
          </section>
        )}
      </main>
      <Footer />
    </div>
  );
};

export const RegistrationSuccessPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const registrationId = searchParams.get('registration_id');
  const accessToken = new URLSearchParams(location.hash.slice(1)).get('token');
  if (registrationId && accessToken) {
    return (
      <ManualPaymentProofPage
        registrationId={registrationId}
        accessToken={accessToken}
      />
    );
  }
  return <PayURegistrationSuccessPage />;
};
