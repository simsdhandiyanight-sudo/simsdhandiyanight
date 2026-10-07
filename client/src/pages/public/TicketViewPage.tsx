import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ticketsApi } from '../../api/tickets';
import { Ticket } from '../../types';
import { DigitalTicket } from '../../components/ticket/DigitalTicket';
import { Navbar } from '../../components/common/Navbar';
import { Footer } from '../../components/common/Footer';
import { FestivalMotifs } from '../../components/common/FestivalMotifs';
import { ShieldCheck, ArrowLeft, Info } from 'lucide-react';

export const TicketViewPage: React.FC = () => {
  const { ticketId } = useParams<{ ticketId: string }>();
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!ticketId) return;
    ticketsApi.getById(ticketId).then((data) => {
      setTicket(data);
      setLoading(false);
    });
  }, [ticketId]);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!ticket) {
    return (
      <div className="festival-public min-h-screen bg-slate-950 text-slate-100 flex flex-col">
        <Navbar />
        <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
          <h2 className="text-xl font-bold font-display text-white mb-2">Ticket Not Found</h2>
          <p className="text-slate-400 text-xs mb-6">
            We couldn't locate a ticket with ID "{ticketId}". Please check your registration link.
          </p>
          <Link
            to="/events"
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-semibold"
          >
            Return to Events
          </Link>
        </div>
        <Footer />
      </div>
    );
  }

  return (
    <div className="festival-public min-h-screen flex flex-col bg-slate-950 text-slate-100">
      <Navbar />

      <main className="festival-hero flex-1 pt-32 pb-24 max-w-2xl mx-auto px-4 sm:px-6 w-full">
        <FestivalMotifs />
        {/* Navigation back */}
        <div className="mb-6 flex items-center justify-between">
          <Link
            to="/events"
            className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Back to Dhandiya Night</span>
          </Link>

          <span className="text-xs font-mono text-slate-300 flex items-center gap-1">
            <ShieldCheck className="w-4 h-4 text-indigo-400" />
            <span>{ticket.status} · local demo</span>
          </span>
        </div>

        {/* Digital Ticket */}
        <DigitalTicket ticket={ticket} showActions={true} />

        {/* Gate Instructions Card */}
        <div className="mt-8 p-4 bg-slate-900 border border-slate-800 rounded-2xl text-xs space-y-2 text-slate-300">
          <div className="flex items-center gap-2 font-semibold text-white">
            <Info className="w-4 h-4 text-indigo-400" />
            <span>Gate Admission Instructions</span>
          </div>
          <ul className="list-disc pl-5 space-y-1 text-slate-400 leading-relaxed">
            <li>Display the QR code clearly when using a browser with camera QR support.</li>
            <li>The demo store records at most one successful entry per ticket in this browser.</li>
            <li>Production entry validation and cross-gate concurrency require the future backend.</li>
          </ul>
        </div>
      </main>

      <Footer />
    </div>
  );
};
