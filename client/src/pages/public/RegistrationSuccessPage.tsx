import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ArrowRight, CheckCircle2, Ticket as TicketIcon } from 'lucide-react';
import { Navbar } from '../../components/common/Navbar';
import { Footer } from '../../components/common/Footer';
import { FestivalMotifs } from '../../components/common/FestivalMotifs';
import { DigitalTicket } from '../../components/ticket/DigitalTicket';
import { Registration, Ticket } from '../../types';

export const RegistrationSuccessPage: React.FC = () => {
  const location = useLocation();
  const state = location.state as { registration?: Registration; ticket?: Ticket; tickets?: Ticket[] } | undefined;
  const registration = state?.registration;
  const ticket = state?.ticket;
  const tickets = state?.tickets ?? (ticket ? [ticket] : []);

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
                  {tickets.length === 1 ? 'Your demo pass is ready.' : `Your ${tickets.length} demo passes are ready.`} This prototype stores registration data in this browser; it is not valid real-world event admission.
                </p>
              </div>
              <div className="inline-flex max-w-full flex-wrap items-center justify-center gap-x-3 gap-y-1 rounded-xl border border-slate-800 bg-slate-900 px-4 py-2 font-mono text-xs text-slate-300">
                <span className="text-slate-500">REGISTRATION ID:</span>
                <span className="break-all font-bold text-indigo-400">{registration.id}</span>
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
                  <DigitalTicket ticket={issuedTicket} showActions />
                </section>
              ))}
            </div>

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
