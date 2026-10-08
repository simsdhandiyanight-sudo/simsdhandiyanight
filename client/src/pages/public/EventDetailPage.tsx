import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { eventsApi, FEATURED_EVENT_SLUG } from '../../api/events';
import { Navbar } from '../../components/common/Navbar';
import { Footer } from '../../components/common/Footer';
import { FestivalMotifs } from '../../components/common/FestivalMotifs';
import { FestivalPoster } from '../../components/common/FestivalPoster';
import { FEATURED_EVENT } from '../../mock/featuredEvent';
import { EventItem } from '../../types';
import {
  Calendar,
  Clock,
  MapPin,
  CheckCircle2,
  ArrowRight,
  ChevronDown,
  ChevronUp,

  Sparkles,
} from 'lucide-react';

export const EventDetailPage: React.FC = () => {
  const [openFaq, setOpenFaq] = useState<number | null>(0);
  const [event, setEvent] = useState<EventItem>(FEATURED_EVENT);
  const [registrationAvailable, setRegistrationAvailable] = useState(false);
  const [eventApiError, setEventApiError] = useState('');

  useEffect(() => {
    let cancelled = false;
    eventsApi.getById(FEATURED_EVENT_SLUG).then((backendEvent) => {
      if (cancelled) return;
      if (!backendEvent) {
        setEventApiError('Ticketing is not configured on the server yet.');
        return;
      }
      setEvent(backendEvent);
      setRegistrationAvailable(
        backendEvent.status === 'open'
        && backendEvent.tiers.some((tier) => tier.available > 0),
      );
    }).catch((error: unknown) => {
      if (cancelled) return;
      setEventApiError(
        error instanceof Error
          ? `Unable to check ticket availability: ${error.message}`
          : 'Unable to check ticket availability.',
      );
    });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="festival-public min-h-screen flex flex-col bg-slate-950 text-slate-100">
      <Navbar />

      <main className="flex-1 pt-28 pb-24">
        {/* Event Hero */}
        <section className="festival-hero relative border-b border-slate-900 bg-gradient-to-b from-indigo-950/20 via-slate-950 to-slate-950 py-12 lg:py-20">
          <FestivalMotifs />
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-center">
              {/* Event Details Left */}
              <div className="lg:col-span-7 space-y-6">
                <div className="flex items-center gap-3 text-xs">
                  <span className="uppercase font-mono tracking-wider font-semibold text-indigo-400">
                    Soundarya Institute
                  </span>
                  <span className="text-slate-600">·</span>
                  <span className={`font-mono ${registrationAvailable ? 'text-emerald-400' : 'text-indigo-300'}`}>
                    {registrationAvailable ? '● REGISTRATION OPEN' : 'EVENT INFORMATION'}
                  </span>
                </div>

                <h1 className="text-3xl sm:text-5xl lg:text-6xl font-display font-extrabold text-white tracking-tight leading-[1.1] text-balance">
                  {event.name}
                </h1>

                <p className="text-base sm:text-lg text-slate-300 max-w-xl leading-relaxed">
                  <span className="festival-script text-2xl font-bold text-indigo-400">{event.tagline}</span>
                </p>

                {/* Key Date / Time / Venue Badgeless Metadata */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 p-4 bg-slate-900/80 border border-slate-800 rounded-2xl text-xs">
                  <div className="flex items-start gap-2.5">
                    <Calendar className="w-4 h-4 text-indigo-400 mt-0.5 shrink-0" />
                    <div>
                      <span className="text-[10px] text-slate-500 font-semibold uppercase block">Date</span>
                      <span className="font-semibold text-slate-200 font-mono">{event.formattedDate}</span>
                    </div>
                  </div>

                  <div className="flex items-start gap-2.5">
                    <Clock className="w-4 h-4 text-indigo-400 mt-0.5 shrink-0" />
                    <div>
                      <span className="text-[10px] text-slate-500 font-semibold uppercase block">Hours</span>
                      <span className="font-semibold text-slate-200 font-mono">{event.time}</span>
                    </div>
                  </div>

                  <div className="flex items-start gap-2.5">
                    <MapPin className="w-4 h-4 text-indigo-400 mt-0.5 shrink-0" />
                    <div>
                      <span className="text-[10px] text-slate-500 font-semibold uppercase block">Location</span>
                      <span className="font-semibold text-slate-200">{event.city}</span>
                    </div>
                  </div>
                </div>

                {/* Main CTA */}
                <div className="flex flex-wrap items-center gap-4 pt-2">
                  {registrationAvailable ? (
                    <Link
                      to={`/register/${event.slug}`}
                      className="px-8 py-4 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-bold text-sm tracking-wide shadow-lg shadow-indigo-600/30 transition-all hover:translate-y-[-1px] inline-flex items-center gap-2 uppercase"
                    >
                      <span>Reserve your pass</span>
                      <ArrowRight className="w-4 h-4" />
                    </Link>
                  ) : (
                    <p role={eventApiError ? 'status' : undefined} className="text-sm text-slate-400">
                      {eventApiError || 'Checking ticket availability…'}
                    </p>
                  )}
                </div>
              </div>

              {/* Official festival artwork */}
              <div className="lg:col-span-5 flex justify-center">
                <FestivalPoster className="w-full max-w-md" />
              </div>
            </div>
          </div>
        </section>

        {/* Detailed Sections: Description, Tiers, Highlights, Schedule, FAQs */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12">
            {/* Left Content column */}
            <div className="lg:col-span-8 space-y-16">
              {/* Overview */}
              <section className="space-y-4">
                <h2 className="text-2xl font-display font-bold text-white tracking-tight">
                  About This Event
                </h2>
                <div className="space-y-3 text-sm sm:text-base text-slate-300 leading-relaxed">
                  {event.description.split(/\r?\n/).map((paragraph, index) => (
                    <p key={index}>{paragraph}</p>
                  ))}
                </div>
                <div className="p-4 bg-slate-900 border border-slate-800 rounded-2xl flex items-start gap-3 text-xs text-slate-300">
                  <MapPin className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold text-white block">Venue Address:</span>
                    <span>{event.venue} — {event.address}</span>
                  </div>
                </div>
              </section>

              {/* Highlights */}
              {event.highlights && event.highlights.length > 0 && (
                <section className="space-y-4">
                  <h2 className="text-2xl font-display font-bold text-white tracking-tight">
                    Event Highlights
                  </h2>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {event.highlights.map((h, idx) => (
                      <div
                        key={idx}
                        className="p-4 bg-slate-900 border border-slate-800 rounded-xl flex items-start gap-3 text-xs text-slate-300"
                      >
                        <CheckCircle2 className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                        <span>{h}</span>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Schedule */}
              {event.schedule && event.schedule.length > 0 && (
                <section className="space-y-4">
                  <h2 className="text-2xl font-display font-bold text-white tracking-tight">
                    Program Schedule
                  </h2>
                  <div className="bg-slate-900 border border-slate-800 rounded-2xl divide-y divide-slate-800">
                    {event.schedule.map((item, idx) => (
                      <div key={idx} className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                        <div className="flex items-start gap-4">
                          <span className="text-xs font-mono font-bold text-indigo-400 shrink-0 w-20">
                            {item.time}
                          </span>
                          <div>
                            <p className="text-sm font-semibold text-white">{item.title}</p>
                            {item.speaker && (
                              <p className="text-xs text-slate-400 mt-0.5">{item.speaker}</p>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* FAQs */}
              {event.faqs && event.faqs.length > 0 && (
                <section className="space-y-4">
                  <h2 className="text-2xl font-display font-bold text-white tracking-tight">
                    Frequently Asked Questions
                  </h2>
                  <div className="space-y-3">
                    {event.faqs.map((faq, idx) => {
                      const isExpanded = openFaq === idx;
                      return (
                        <div
                          key={idx}
                          className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden transition-colors"
                        >
                          <button
                            onClick={() => setOpenFaq(isExpanded ? null : idx)}
                            className="w-full p-4 sm:p-5 text-left flex items-center justify-between gap-4 cursor-pointer hover:bg-slate-800/40"
                          >
                            <span className="text-sm font-semibold text-white">
                              {faq.question}
                            </span>
                            {isExpanded ? (
                              <ChevronUp className="w-4 h-4 text-slate-400 shrink-0" />
                            ) : (
                              <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />
                            )}
                          </button>
                          {isExpanded && (
                            <div className="px-4 pb-5 pt-1 sm:px-5 text-xs text-slate-300 leading-relaxed border-t border-slate-800/60">
                              {faq.answer}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}
            </div>

            {/* Right Sticky Column: Pass Options */}
            <div className="lg:col-span-4">
              <div className="sticky top-24 space-y-4">
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-5">
                  <div className="flex items-center justify-between pb-4 border-b border-slate-800">
                    <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                      AVAILABLE PASS TIERS
                    </span>
                    <span className="text-xs font-mono text-emerald-400">Immediate Issuance</span>
                  </div>

                  <div className="space-y-3">
                    {event.tiers.map((tier) => (
                      <div
                        key={tier.id}
                        className="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-2 hover:border-slate-700 transition-colors"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-sm text-white">{tier.name}</span>
                          <span className="font-mono font-bold text-sm text-indigo-300">
                            ₹{tier.price}
                          </span>
                        </div>
                        <p className="text-xs text-slate-400 leading-relaxed">
                          {tier.description}
                        </p>
                        <div className="pt-2 border-t border-slate-900 flex justify-between items-center text-[11px] text-slate-500 font-mono">
                          <span>
                            {tier.available > 0
                              ? (tier.admissionCount ?? 1) > 1
                                ? `${tier.available} combo offers left`
                                : `${tier.available} tickets left`
                              : 'Sold out'}
                          </span>
                          {registrationAvailable && tier.available > 0 && (
                            <Link
                              to={`/register/${event.slug}?tier=${tier.id}`}
                              className="text-indigo-400 hover:text-indigo-300 font-semibold"
                            >
                              Select Tier &rarr;
                            </Link>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>

                  {registrationAvailable && (
                    <Link
                      to={`/register/${event.slug}`}
                      className="w-full py-3.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-bold text-xs uppercase tracking-wider flex items-center justify-center gap-2 shadow-md shadow-indigo-600/30 transition-all"
                    >
                      <span>REGISTER NOW</span>
                      <ArrowRight className="w-4 h-4" />
                    </Link>
                  )}
                </div>

                <div className="p-4 bg-slate-900/60 border border-slate-800/80 rounded-2xl text-xs text-slate-400 space-y-2">
                  <div className="flex items-center gap-2 text-slate-300 font-semibold">
                    <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                    <span>Instant Digital QR Access</span>
                  </div>
                  <p>
                    Pass is generated immediately on submission and can be added to your mobile wallet or scanned at entrance gates.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
};
