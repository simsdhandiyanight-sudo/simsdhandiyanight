import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { eventsApi, FEATURED_EVENT_SLUG } from '../../api/events';
import { registrationsApi } from '../../api/registrations';
import { EventItem, Ticket } from '../../types';
import { DigitalTicket } from '../../components/ticket/DigitalTicket';
import {
  CheckCircle2,
  Printer,
  QrCode,
  RotateCcw,
  ArrowLeft,
  Zap,
} from 'lucide-react';

export const OnSpotRegistrationPage: React.FC = () => {
  const [activeEvent, setActiveEvent] = useState<EventItem | null>(null);
  const [loadingEvent, setLoadingEvent] = useState(true);
  const [eventLoadError, setEventLoadError] = useState('');

  useEffect(() => {
    let cancelled = false;
    eventsApi.getById(FEATURED_EVENT_SLUG).then((event) => {
      if (cancelled) return;
      setActiveEvent(event);
      setTierId(event?.tiers[0]?.id || '');
      setLoadingEvent(false);
    }).catch((error: unknown) => {
      if (cancelled) return;
      setEventLoadError(error instanceof Error ? error.message : 'Unable to load event details. Please try again.');
      setLoadingEvent(false);
    });
    return () => { cancelled = true; };
  }, []);

  // Fast Form state
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [organization, setOrganization] = useState('');
  const [tierId, setTierId] = useState('');
  const [errorMessage, setErrorMessage] = useState('');

  // Result state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [generatedTicket, setGeneratedTicket] = useState<Ticket | null>(null);
  const [showFullPass, setShowFullPass] = useState(false);
  const eventUnavailableMessage = eventLoadError || (loadingEvent
    ? 'Loading event details…'
    : !activeEvent
      ? 'No event is available for registration.'
      : activeEvent.status !== 'open'
        ? 'Registration is not open for this event.'
        : activeEvent.registeredCount >= activeEvent.capacity
          ? 'This event has reached its registration capacity.'
          : activeEvent.tiers.every((tier) => tier.available < 1)
            ? 'All ticket tiers are sold out.'
            : '');

  const handleRegisterOnSpot = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeEvent || !tierId || !name.trim()) return;
    setIsSubmitting(true);
    setErrorMessage('');
    try {
      const result = await registrationsApi.create({
        eventId: activeEvent.id,
        attendee: {
          fullName: name.trim(),
          email: email.trim(),
          phone: phone.trim(),
          organization: organization.trim() || undefined,
        },
        tierId,
        source: 'ON_SPOT',
      });
      setGeneratedTicket(result.ticket);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Registration failed. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResetForNext = () => {
    setName('');
    setPhone('');
    setEmail('');
    setOrganization('');
    setGeneratedTicket(null);
    setShowFullPass(false);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Header */}
      <header className="bg-slate-900 border-b border-slate-800 px-4 sm:px-8 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            to="/staff/dashboard"
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <span className="font-display font-bold text-white text-base">
            Soundarya · On-Spot Desk
          </span>
          <span className="text-xs font-mono text-emerald-400 bg-emerald-950/80 px-2 py-0.5 rounded border border-emerald-800/80">
            FAST ENTRY KIOSK
          </span>
        </div>

        <div className="flex items-center gap-2">
          <Link
            to="/staff/scanner"
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 rounded-lg flex items-center gap-1.5"
          >
            <QrCode className="w-3.5 h-3.5 text-indigo-400" />
            <span>Open Scanner</span>
          </Link>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 p-4 sm:p-8 max-w-2xl mx-auto w-full flex flex-col justify-center">
        {!generatedTicket ? (
          /* Operational Fast Form */
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow-2xl space-y-6">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-[11px] font-mono font-bold text-indigo-400 uppercase tracking-wider flex items-center gap-1.5">
                  <Zap className="w-3.5 h-3.5" />
                  <span>FAST WALK-IN REGISTRATION</span>
                </div>
                <h1 className="text-2xl font-bold font-display text-white mt-1">
                  Attendee Fast Check-In
                </h1>
                <p className="text-xs text-slate-400">
                  Create a local demo registration and ticket for venue arrivals.
                </p>
              </div>

              <div className="text-right">
                <span className="text-[10px] text-slate-500 font-semibold uppercase block">
                  FESTIVAL EVENT
                </span>
                <span className="font-display text-sm font-bold text-slate-200">Dhandiya Night</span>
              </div>
            </div>

            <div className="rounded-xl border border-amber-900/60 bg-amber-950/30 px-3 py-2 text-[11px] leading-relaxed text-amber-200/90">
              Registration and ticket data are saved to the ticketing service.
            </div>
            {errorMessage && (
              <div role="alert" className="rounded-xl border border-rose-900/70 bg-rose-950/40 px-3 py-2 text-xs text-rose-200">
                {errorMessage}
              </div>
            )}
            {eventUnavailableMessage && (
              <div role="status" className="rounded-xl border border-amber-900/60 bg-amber-950/30 px-3 py-2 text-xs text-amber-200 flex items-center gap-2">
                {loadingEvent && <span className="w-4 h-4 border-2 border-amber-300 border-t-transparent rounded-full animate-spin" aria-label="Loading event" />}

                {eventUnavailableMessage}
              </div>
            )}

            <form onSubmit={handleRegisterOnSpot} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1">
                  Full Name <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  required
                  autoFocus
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Sumanth Patel"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1">
                    Phone Number
                  </label>
                  <input
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="+91 98450 00000"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1">
                    Email Address
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="attendee@example.com (optional)"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1">
                    Organization / Affiliation
                  </label>
                  <input
                    type="text"
                    value={organization}
                    onChange={(e) => setOrganization(e.target.value)}
                    placeholder="Company or College"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1">
                    Pass Tier
                  </label>
                  <select
                    value={tierId}
                    onChange={(e) => setTierId(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-white focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer"
                  >
                    {activeEvent?.tiers.map((t) => (
                      <option key={t.id} value={t.id} disabled={t.available < 1}>
                        {t.name} · {t.available} available
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="pt-2">
                <button
                  type="submit"
                  disabled={
                    isSubmitting ||
                    !name.trim() ||
                    !activeEvent ||
                    activeEvent.status !== 'open' ||
                    !tierId ||
                    activeEvent.registeredCount >= activeEvent.capacity
                    ||
                    activeEvent.tiers.every((tier) => tier.available < 1)
                  }
                  className="w-full py-4 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-slate-950 font-bold rounded-2xl text-sm uppercase tracking-wider flex items-center justify-center gap-2 shadow-lg shadow-emerald-600/20 transition-all cursor-pointer"
                >
                  {isSubmitting ? (
                    <span className="w-5 h-5 border-2 border-slate-950 border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <>
                      <CheckCircle2 className="w-5 h-5" />
                      <span>REGISTER &amp; GENERATE TICKET</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        ) : (
          /* Confirmation Screen optimized for repeat venue use */
          <div className="bg-slate-900 border-2 border-emerald-500/80 rounded-3xl p-6 sm:p-8 shadow-2xl text-center space-y-6 animate-in fade-in duration-150">
            <div className="w-14 h-14 bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 rounded-2xl mx-auto flex items-center justify-center">
              <CheckCircle2 className="w-7 h-7" />
            </div>

            <div className="space-y-1">
              <div className="text-xs font-mono font-bold text-emerald-400 uppercase tracking-wider">
                REGISTRATION COMPLETE
              </div>
              <h2 className="text-2xl font-bold font-display text-white">Ticket Generated</h2>
              <p className="text-xs text-slate-300">
                Ticket created and saved to the ticketing service.
              </p>
            </div>

            {/* Compact Pass Card Summary */}
            <div className="bg-slate-950 border border-slate-800 rounded-2xl p-4 text-left space-y-2">
              <div className="flex justify-between items-center pb-2 border-b border-slate-800 text-xs">
                <span className="text-slate-400 uppercase font-semibold">ATTENDEE</span>
                <span className="font-bold text-white text-sm">{generatedTicket.attendeeName}</span>
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-400 uppercase font-semibold">TICKET ID</span>
                <span className="font-mono font-bold text-indigo-400">{generatedTicket.id}</span>
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-400 uppercase font-semibold">SOURCE</span>
                <span className="font-mono text-emerald-400">ON_SPOT (DESK)</span>
              </div>
            </div>

            {/* If user expands full pass modal */}
            {showFullPass && (
              <div className="pt-4 border-t border-slate-800">
                <DigitalTicket ticket={generatedTicket} showActions={false} />
              </div>
            )}

            {/* Operational Action Controls */}
            <div className="grid grid-cols-2 gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowFullPass(!showFullPass)}
                className="py-3 px-4 bg-slate-800 hover:bg-slate-700 text-white rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 cursor-pointer transition-colors"
              >
                <QrCode className="w-4 h-4 text-indigo-400" />
                <span>{showFullPass ? 'Hide QR' : 'Show QR Pass'}</span>
              </button>

              <button
                type="button"
                onClick={() => window.print()}
                className="py-3 px-4 bg-slate-800 hover:bg-slate-700 text-white rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 cursor-pointer transition-colors"
              >
                <Printer className="w-4 h-4 text-slate-400" />
                <span>Print Ticket</span>
              </button>
            </div>

            {/* Register Another Attendee Button */}
            <button
              type="button"
              autoFocus
              onClick={handleResetForNext}
              className="w-full py-4 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-2xl text-xs uppercase tracking-wider flex items-center justify-center gap-2 shadow-lg shadow-indigo-600/30 cursor-pointer transition-transform active:scale-[0.98]"
            >
              <RotateCcw className="w-4 h-4" />
              <span>REGISTER ANOTHER ATTENDEE</span>
            </button>
          </div>
        )}
      </main>
    </div>
  );
};
