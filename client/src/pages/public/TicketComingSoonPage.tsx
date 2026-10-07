import React from 'react';

export const TicketComingSoonPage: React.FC = () => {
  return (
    <main
      className="flex min-h-screen flex-col items-center justify-center px-4 py-8 text-center text-[#1d2b50]"
      style={{
        backgroundColor: '#fffaf0',
        backgroundImage: "linear-gradient(rgba(255, 250, 240, 0.3), rgba(255, 250, 240, 0.3)), url('/festive-garba-celebration-backdrop.png')",
        backgroundPosition: 'center',
        backgroundSize: 'cover',
      }}
    >
      <div className="flex w-full max-w-xl flex-col items-center gap-6 rounded-3xl border border-[#d8bd7c]/80 bg-[#fffaf0]/90 p-4 shadow-2xl backdrop-blur-sm sm:p-6">
        <img
          src="/dhandiya-night-poster.jpeg"
          alt="Dhandiya Night event poster"
          className="h-auto w-full rounded-2xl border border-[#d8bd7c] shadow-xl"
          fetchPriority="high"
        />
        <section className="space-y-2">
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-[#9b6e19]">
            Dhandiya Night 2026
          </p>
          <h1 className="font-display text-3xl font-bold sm:text-4xl">Tickets will be out soon</h1>
        </section>
      </div>
    </main>
  );
};
