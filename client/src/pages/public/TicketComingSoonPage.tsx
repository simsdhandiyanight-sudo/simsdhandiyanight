import React, { useEffect, useMemo, useState } from 'react';

const RELEASE_TIME = new Date('2026-10-10T12:00:00+05:30').getTime();

export const TicketComingSoonPage: React.FC = () => {
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNow(Date.now());
    }, 1000);

    return () => window.clearInterval(timer);
  }, []);

  const timeLeft = useMemo(() => {
    const diff = Math.max(RELEASE_TIME - now, 0);
    const totalSeconds = Math.floor(diff / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    return {
      hours: String(hours).padStart(2, '0'),
      minutes: String(minutes).padStart(2, '0'),
      seconds: String(seconds).padStart(2, '0'),
      isLive: diff === 0,
    };
  }, [now]);

  return (
    <main
      className="flex min-h-screen flex-col items-center justify-center px-4 py-8 text-center text-[#1d2b50]"
      style={{
        backgroundColor: '#fffaf0',
        backgroundImage: "linear-gradient(rgba(255, 250, 240, 0.3), rgba(255, 250, 240, 0.3)), url('/festive-garba-celebration-backdrop.webp')",
        backgroundPosition: 'center',
        backgroundSize: 'cover',
      }}
    >
      <div className="flex w-full max-w-xl flex-col items-center gap-6 rounded-3xl border border-[#d8bd7c]/80 bg-[#fffaf0]/90 p-4 shadow-2xl backdrop-blur-sm sm:p-6">
        <img
          src="/dandiya-night-poster.png"
          sizes="(max-width: 768px) 90vw, 576px"
          alt="Dhandiya Night event poster"
          className="h-auto w-full rounded-2xl border border-[#d8bd7c] shadow-xl"
          fetchPriority="high"
        />
        <section className="space-y-4">
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-[#9b6e19]">
            Dhandiya Night 2026
          </p>
          <h1 className="font-display text-3xl font-bold sm:text-4xl">Tickets will be out soon</h1>

          <div className="flex items-center justify-center gap-3 rounded-2xl border border-[#d8bd7c] bg-[#fffdf7] px-4 py-3 shadow-inner sm:gap-4">
            {[
              { label: 'Hours', value: timeLeft.hours },
              { label: 'Minutes', value: timeLeft.minutes },
              { label: 'Seconds', value: timeLeft.seconds },
            ].map((item) => (
              <div key={item.label} className="min-w-[58px] rounded-xl border border-[#efe0b7] bg-[#fffaf0] px-2 py-2 shadow-sm">
                <div className="font-display text-2xl font-bold text-[#1d2b50] sm:text-3xl">{item.value}</div>
                <div className="mt-1 font-mono text-[9px] uppercase tracking-[0.18em] text-[#8d6f2c]">{item.label}</div>
              </div>
            ))}
          </div>

          <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-[#8d6f2c]">
            {timeLeft.isLive ? 'Tickets are live now' : 'Live countdown to ticket release'}
          </p>
        </section>
      </div>
    </main>
  );
};
