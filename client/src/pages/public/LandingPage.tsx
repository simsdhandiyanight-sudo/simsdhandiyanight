import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowDown,
  ArrowRight,
  CalendarDays,
  Clock3,
  Flower2,
  MapPin,
} from 'lucide-react';
import { eventsApi, FEATURED_EVENT_SLUG } from '../../api/events';
import { EventItem } from '../../types';
import { Footer } from '../../components/common/Footer';
import { FestivalMotifs } from '../../components/common/FestivalMotifs';
import { FestivalPoster } from '../../components/common/FestivalPoster';
import { Navbar } from '../../components/common/Navbar';

const registerPath = '/register/dhandiya-night-2026';
const eventPath = '/events/dhandiya-night-2026';

const highlights = [
  {
    title: 'Dance',
    className: 'dance',
    image: '/elegant-dance-music-celebration-card.png',
    alt: 'Dance festival invitation card: Move to the music. Dance — Follow the rhythm into a night of joyful Garba and movement.',
  },
  {
    title: 'Dandiya',
    className: 'dandiya',
    image: '/ornate-dandiya-celebration.png',
    alt: 'Dandiya celebration card: Join the circle. Dandiya — Join the circle and celebrate tradition with the Soundarya community.',
  },
  {
    title: 'Dhamaka',
    className: 'dhamaka',
    image: '/ornate-dhamaka-festival-invitation.png',
    alt: 'Dhamaka festival invitation card: Make it a night. Dhamaka — A vibrant evening of lights, colour, and memories with friends.',
  },
];

export const LandingPage: React.FC = () => {
  const [event, setEvent] = useState<EventItem | null>(null);
  const [eventError, setEventError] = useState('');
  const [eventLoading, setEventLoading] = useState(true);
  const heroRef = useRef<HTMLElement>(null);

  useEffect(() => {
    let cancelled = false;
    eventsApi.getById(FEATURED_EVENT_SLUG).then((loadedEvent) => {
      if (!cancelled) {
        setEvent(loadedEvent);
        setEventLoading(false);
        if (!loadedEvent) setEventError('Dhandiya Night event details are currently unavailable.');
      }
    }).catch((error: unknown) => {
      if (!cancelled) {
        setEventError(error instanceof Error ? error.message : 'Unable to load event details. Please try again.');
        setEventLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const revealItems = document.querySelectorAll<HTMLElement>('.festival-reveal');
    if (!('IntersectionObserver' in window)) {
      revealItems.forEach((item) => item.classList.add('is-visible'));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12 }
    );
    revealItems.forEach((item) => observer.observe(item));
    return () => observer.disconnect();
  }, []);

  const handlePointerMove = (pointer: React.PointerEvent<HTMLElement>) => {
    if (pointer.pointerType === 'touch' || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      return;
    }
    const bounds = pointer.currentTarget.getBoundingClientRect();
    const x = (pointer.clientX - bounds.left) / bounds.width - 0.5;
    const y = (pointer.clientY - bounds.top) / bounds.height - 0.5;
    heroRef.current?.style.setProperty('--pointer-x', `${x.toFixed(3)}`);
    heroRef.current?.style.setProperty('--pointer-y', `${y.toFixed(3)}`);
  };

  const resetPointer = () => {
    heroRef.current?.style.setProperty('--pointer-x', '0');
    heroRef.current?.style.setProperty('--pointer-y', '0');
  };

  return (
    <div className="festival-public min-h-screen">
      <Navbar />

      <main>
        <section
          ref={heroRef}
          className="festival-home-hero"
          onPointerMove={handlePointerMove}
          onPointerLeave={resetPointer}
        >
          <div className="festival-home-hero__texture" aria-hidden="true" />
          <div className="festival-home-hero__lights" aria-hidden="true" />
          <FestivalMotifs />

          <h1 className="sr-only">Dhandiya Night</h1>

          <div className="festival-home-poster" aria-label="Dhandiya Night festival invitation">
            <span className="festival-home-poster__frame festival-home-poster__frame--back" aria-hidden="true" />
            <FestivalPoster priority className="festival-poster--home" />
          </div>

          <div className="festival-home-invitation">
            <div className="festival-home-invitation__details">
              <div className="festival-home-invitation__detail">
                <CalendarDays aria-hidden="true" />
                <span><small>DATE</small><strong>{event?.formattedDate || '16th October 2026'}</strong></span>
              </div>
              <div className="festival-home-invitation__detail">
                <Clock3 aria-hidden="true" />
                <span><small>TIME</small><strong>{event?.time || '6:00 PM – 9:00 PM'}</strong></span>
              </div>
              <div className="festival-home-invitation__detail">
                <MapPin aria-hidden="true" />
                <span><small>VENUE</small><strong>Soundarya College Campus</strong></span>
              </div>
            </div>
            {eventLoading && <p role="status" className="mt-3 text-sm text-slate-300 flex items-center gap-2"><span className="w-4 h-4 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />Loading event details…</p>}
            {eventError && <p role="alert" className="mt-3 text-sm text-rose-300">{eventError}</p>}
            <p className="festival-home-invitation__tagline">Dance <i>•</i> Dandiya <i>•</i> Dhamaka</p>
            <div className="festival-home-invitation__actions">
              <Link to={registerPath} className="festival-invitation-button">
                <span>Register Now</span>
                <ArrowRight aria-hidden="true" />
              </Link>
              <Link to={eventPath} className="festival-home-invitation__secondary">
                Event Details
              </Link>
            </div>
          </div>

          <a className="festival-home-hero__scroll" href="#celebration">
            <span>THE NIGHT AWAITS</span>
            <ArrowDown aria-hidden="true" />
          </a>
        </section>

        <section id="celebration" className="festival-experience">
          <div className="festival-experience__ornament festival-experience__ornament--left" aria-hidden="true" />
          <div className="festival-experience__ornament festival-experience__ornament--right" aria-hidden="true" />
          <header className="festival-section-heading festival-reveal">
            <p>AN EVENING MADE FOR</p>
            <h2>Three beats. <em>One unforgettable night.</em></h2>
            <span className="festival-section-heading__rule"><i>✿</i></span>
          </header>

          <div className="festival-experience__cards">
            {highlights.map(({ title, className, image, alt }, index) => (
              <article
                key={title}
                className={`festival-experience-card festival-experience-card--${className} festival-reveal`}
                style={{ transitionDelay: `${index * 90}ms` }}
              >
                <img src={image} alt={alt} loading="lazy" />
              </article>
            ))}
          </div>
        </section>

        <section id="about" className="festival-about">
          <div className="festival-about__inner">
            <div className="festival-about__art festival-reveal">
              <span className="festival-about__sunburst" aria-hidden="true" />
              <FestivalPoster className="festival-poster--about" />
              <span className="festival-about__caption">SOUNDARYA · BENGALURU</span>
              <Flower2 className="festival-about__flower" aria-hidden="true" />
            </div>
            <div className="festival-about__copy festival-reveal">
              <p className="festival-about__eyebrow"><span /> A SOUNDARYA CELEBRATION</p>
              <h2>Come for the music.<br /><em>Stay for the magic.</em></h2>
              <p className="festival-about__body">
                When the evening lights up, the circle comes alive. Gather your friends for a joyful
                celebration of Garba, Dandiya, and the colour of tradition—hosted by Daksha Student
                Council at Soundarya Institute.
              </p>
              <div className="festival-about__signature">
                <span className="festival-about__signature-mark"><Flower2 /></span>
                <span><strong>Dhandiya Night</strong><small>Dance · Dandiya · Dhamaka</small></span>
              </div>
              <Link to={eventPath} className="festival-text-link">
                Discover the celebration <ArrowRight aria-hidden="true" />
              </Link>
            </div>
          </div>
        </section>

        <section className="festival-last-call">
          <span className="festival-last-call__flower festival-last-call__flower--left" aria-hidden="true">✿</span>
          <div className="festival-last-call__content festival-reveal">
            <p>THE DANCE FLOOR IS CALLING</p>
            <h2>Be part of the <em>celebration.</em></h2>
            <Link to={registerPath} className="festival-invitation-button festival-invitation-button--light">
              <span>Register Now</span><ArrowRight aria-hidden="true" />
            </Link>
          </div>
          <span className="festival-last-call__flower festival-last-call__flower--right" aria-hidden="true">✿</span>
        </section>
      </main>

      <Footer />
    </div>
  );
};
