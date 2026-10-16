import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, MapPin } from 'lucide-react';
import { Footer } from '../../components/common/Footer';
import { Navbar } from '../../components/common/Navbar';

export const RegistrationClosedPage: React.FC = () => (
  <div className="festival-public flex min-h-screen flex-col">
    <Navbar />
    <main className="flex flex-1 items-center justify-center px-4 pb-16 pt-28 sm:px-6">
      <section className="w-full max-w-2xl rounded-2xl border border-amber-700/30 bg-white/80 p-6 text-center shadow-xl sm:p-10">
        <p className="text-sm font-bold uppercase tracking-[0.18em] text-rose-800">
          Dhandiya Night 2026
        </p>
        <h1 className="mt-3 font-display text-3xl font-bold text-rose-950 sm:text-4xl">
          Online registrations are closed
        </h1>
        <p className="mt-4 text-base leading-relaxed text-slate-700">
          Online registrations for Dhandiya Night are now closed. On-the-spot tickets will be
          available from 5:00 PM onwards at the venue.
        </p>
        <div className="mt-6 rounded-xl border border-amber-500/40 bg-amber-50 p-5 text-left text-sm leading-relaxed text-slate-800">
          <h2 className="flex items-center gap-2 font-semibold text-rose-900">
            <MapPin aria-hidden="true" className="h-5 w-5 shrink-0" />
            Soundarya Institute of Management and Science
          </h2>
          <address className="mt-3 not-italic">
            Soundarya Nagar, Sidedahalli, Nagasandra Post,
            <br />
            296, 9th Cross Road, Prakruthi Layout,
            <br />
            Siddeshwar Layout, Soundarya Layout,
            <br />
            Bengaluru, Karnataka – 560073.
          </address>
          <a
            className="mt-3 inline-block font-semibold text-rose-900 underline hover:text-rose-700"
            href="https://maps.app.goo.gl/1yx4m8NBTvXcoT2k9"
            target="_blank"
            rel="noreferrer"
          >
            Click here for directions to the venue →
          </a>
        </div>
        <Link
          to="/events/dhandiya-night-2026"
          className="mt-6 inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-rose-800 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-rose-900"
        >
          <ArrowLeft aria-hidden="true" className="h-4 w-4" />
          View event details
        </Link>
      </section>
    </main>
    <Footer />
  </div>
);
