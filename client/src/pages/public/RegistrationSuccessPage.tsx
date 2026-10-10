import React, { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowRight, CheckCircle2, Download, Ticket as TicketIcon, Clock3 } from 'lucide-react';
import { ApiError, apiBlob } from '../../api/http';
import { paymentsApi } from '../../api/payments';
import { mapRegistration, mapTicket } from '../../api/serializers';
import { Navbar } from '../../components/common/Navbar';
import { Footer } from '../../components/common/Footer';
import { FestivalMotifs } from '../../components/common/FestivalMotifs';
import { DigitalTicket } from '../../components/ticket/DigitalTicket';
import { Registration, Ticket } from '../../types';

export const RegistrationSuccessPage: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [isDownloadingBundle, setIsDownloadingBundle] = useState(false);
  const [bundleDownloadError, setBundleDownloadError] = useState('');
  const [paymentStatus, setPaymentStatus] = useState<'loading' | 'pending' | 'failed' | 'review' | 'error'>('loading');
  const [statusMessage, setStatusMessage] = useState('');
  const state = location.state as { registration?: Registration; ticket?: Ticket; tickets?: Ticket[] } | undefined;
  const registration = state?.registration;
  const ticket = state?.ticket;
  const tickets = state?.tickets ?? (ticket ? [ticket] : []);
  const txnid = searchParams.get('txnid') || '';

  useEffect(() => {
    if (!txnid || registration) return;
    let active = true;
    let refreshing = false;
    let terminal = false;
    const refresh = async () => {
      if (refreshing || terminal) return;
      refreshing = true;
      try {
        const idempotencyKey = sessionStorage.getItem(
          `ticketing.payment-idempotency.${txnid}`,
        );
        if (!idempotencyKey) {
          terminal = true;
          setPaymentStatus('error');
          setStatusMessage('This browser session cannot access the payment confirmation. Return using the same browser session or contact the event team.');
          return;
        }
        const payment = await paymentsApi.status(txnid, idempotencyKey);
        if (!active) return;
        if (payment.payment_verified && payment.registration && payment.tickets) {
          const storageKey = sessionStorage.getItem(
            `ticketing.payment-idempotency-storage.${txnid}`,
          );
          if (storageKey) sessionStorage.removeItem(storageKey);
          sessionStorage.removeItem(`ticketing.payment-idempotency.${txnid}`);
          sessionStorage.removeItem(`ticketing.payment-idempotency-storage.${txnid}`);
          const confirmedTickets = payment.tickets.map(mapTicket);
          navigate('/registration/success', {
            replace: true,
            state: {
              registration: mapRegistration(payment.registration),
              ticket: confirmedTickets[0],
              tickets: confirmedTickets,
            },
          });
          return;
        }
        if (payment.payment_status === 'FAILED') {
          terminal = true;
          sessionStorage.removeItem(`ticketing.payment-idempotency.${txnid}`);
          sessionStorage.removeItem(`ticketing.payment-idempotency-storage.${txnid}`);
          setPaymentStatus('failed');
          setStatusMessage('PayU reported that this payment failed or was cancelled. No tickets have been issued.');
        } else if (payment.ticket_issuance_status === 'ADMIN_REVIEW_REQUIRED') {
          terminal = true;
          setPaymentStatus('review');
          setStatusMessage(payment.verification_message || 'Payment requires administrator review. Do not pay again; contact event support with your transaction reference.');
        } else {
          setPaymentStatus('pending');
          setStatusMessage('Payment is still being confirmed by PayU. This page will check again shortly; do not retry payment while it is processing.');
        }
      } catch (error) {
        if (!active) return;
        if (error instanceof ApiError && error.code === 'PAYMENT_REVIEW_REQUIRED') {
          terminal = true;
          setPaymentStatus('review');
          setStatusMessage(error.message);
          return;
        }
        setPaymentStatus('error');
        setStatusMessage(error instanceof Error ? error.message : 'Payment status could not be checked.');
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

  const downloadAllTickets = async () => {
    setIsDownloadingBundle(true);
    setBundleDownloadError('');
    try {
      if (!registration) throw new Error('Registration details are unavailable.');
      const pdf = await apiBlob(
        `/registrations/${encodeURIComponent(registration.id)}/tickets.pdf`,
      );
      const url = URL.createObjectURL(pdf);
      const link = document.createElement('a');
      link.href = url;
      link.download = `tickets-${registration.registrationCode || registration.id}.pdf`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      console.error('Failed to generate combo ticket PDF.', error);
      setBundleDownloadError('Tickets could not be downloaded. Please try again.');
    } finally {
      setIsDownloadingBundle(false);
    }
  };

  return (
    <div className="festival-public flex min-h-screen flex-col bg-slate-950 text-slate-100">
      <Navbar />

      <main className="festival-hero mx-auto w-full max-w-4xl flex-1 px-4 pb-24 pt-32 sm:px-6">
        <FestivalMotifs />
        {registration && ticket ? (
          <>
            <div className="mb-10 space-y-4 text-center">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-3xl border border-emerald-500/40 bg-emerald-500/20 text-emerald-400 shadow-lg shadow-emerald-500/10">
                <CheckCircle2 className="h-8 w-8" />
              </div>
              <div className="space-y-2">
                <p className="font-mono text-xs font-bold uppercase tracking-wider text-emerald-400">
                  Soundarya · Dhandiya Night
                </p>
                <h1 className="font-display text-3xl font-extrabold tracking-tight text-white sm:text-4xl">
                  Registration confirmed
                </h1>
                <p className="mx-auto max-w-md text-sm leading-relaxed text-slate-400">
                  {tickets.length === 1
                    ? 'Your payment is verified and your ticket is ready.'
                    : `Your payment is verified and all ${tickets.length} tickets are ready.`}
                  {' '}Keep the QR code available for entry.
                </p>
              </div>
              <div className="inline-flex max-w-full flex-wrap items-center justify-center gap-x-3 gap-y-1 rounded-xl border border-slate-800 bg-slate-900 px-4 py-2 font-mono text-xs text-slate-300">
                <span className="text-slate-500">REGISTRATION ID:</span>
                <span className="break-all font-bold text-indigo-400">
                  {registration.registrationCode || registration.id}
                </span>
              </div>
            </div>

            <div className="mb-12 space-y-8">
              {tickets.map((issuedTicket, index) => (
                <section key={issuedTicket.id} aria-label={`Admission ${index + 1} of ${tickets.length}`}>
                  {tickets.length > 1 && (
                    <h2 className="mb-3 text-center text-sm font-semibold text-slate-300">
                      Admission {index + 1} of {tickets.length}
                    </h2>
                  )}
                  <DigitalTicket
                    ticket={issuedTicket}
                    showActions
                  />
                </section>
              ))}
            </div>

            {tickets.length > 1 && (
              <div className="mx-auto mb-6 max-w-md">
                <button
                  type="button"
                  onClick={() => void downloadAllTickets()}
                  disabled={isDownloadingBundle}
                  aria-busy={isDownloadingBundle}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-rose-700 to-fuchsia-700 px-4 py-3 text-sm font-semibold text-white shadow-md transition-colors hover:from-rose-800 hover:to-fuchsia-800 disabled:cursor-wait disabled:opacity-60"
                >
                  <Download className="h-4 w-4" />
                  <span>{isDownloadingBundle ? 'Preparing all tickets…' : `Download all ${tickets.length} tickets (PDF)`}</span>
                </button>
                {bundleDownloadError && (
                  <p role="alert" className="mt-2 text-center text-xs text-rose-700">
                    {bundleDownloadError}
                  </p>
                )}
              </div>
            )}

            <div className="mx-auto grid max-w-md grid-cols-1 gap-3 border-t border-slate-800 pt-6 sm:grid-cols-2">
              <Link
                to={`/ticket/${ticket.id}`}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-xs font-semibold text-white shadow-md transition-colors hover:bg-indigo-500"
              >
                <TicketIcon className="h-4 w-4" />
                <span>Full pass view</span>
              </Link>
              <Link
                to="/events"
                className="flex w-full items-center justify-center gap-2 rounded-xl border border-slate-800 bg-slate-900 px-4 py-3 text-xs font-semibold text-slate-300 transition-colors hover:bg-slate-800 hover:text-white"
              >
                <span>Back to Dhandiya Night</span>
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </>
        ) : txnid ? (
          <div className="mx-auto max-w-lg rounded-2xl border border-slate-800 bg-slate-900 p-8 text-center">
            {paymentStatus === 'failed' ? (
              <TicketIcon className="mx-auto mb-4 h-10 w-10 text-rose-300" />
            ) : paymentStatus === 'pending' || paymentStatus === 'review' ? (
              <Clock3 className="mx-auto mb-4 h-10 w-10 text-amber-300" />
            ) : (
              <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" role="status" aria-label="Checking payment" />
            )}
            <h1 className="font-display text-2xl font-bold text-white">
              {paymentStatus === 'failed'
                ? 'Payment not completed'
                : paymentStatus === 'review'
                  ? 'Payment needs review'
                  : 'Confirming your payment'}
            </h1>
            <p role="status" className="mt-2 text-sm leading-relaxed text-slate-400">
              {statusMessage || 'Checking the payment status securely with PayU…'}
            </p>
            <p className="mt-4 break-all font-mono text-xs text-slate-500">Transaction: {txnid}</p>
            {paymentStatus === 'failed' && (
              <Link
                to="/register"
                className="mt-6 inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-indigo-500"
              >
                Try again <ArrowRight className="h-4 w-4" />
              </Link>
            )}
            <Link
              to="/events"
              className="mt-6 ml-3 inline-flex items-center justify-center gap-2 rounded-xl border border-slate-700 px-5 py-3 text-sm font-semibold text-slate-300 transition-colors hover:bg-slate-800"
            >
              Back to Dhandiya Night
            </Link>
          </div>
        ) : (
          <div className="mx-auto max-w-lg rounded-2xl border border-slate-800 bg-slate-900 p-8 text-center">
            <TicketIcon className="mx-auto mb-4 h-10 w-10 text-indigo-300" />
            <h1 className="font-display text-2xl font-bold text-white">No registration confirmation found</h1>
            <p className="mt-2 text-sm leading-relaxed text-slate-400">
              This confirmation page needs the registration details from this browser session. Return to Dhandiya Night to start a demo registration.
            </p>
            <Link
              to="/events"
              className="mt-6 inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-indigo-500"
            >
              Dhandiya Night <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        )}
      </main>

      <Footer />
    </div>
  );
};
