import React, { useState } from 'react';
import { Eye, RotateCw } from 'lucide-react';

interface Ticket3DProps {
  eventName?: string;
  date?: string;
  venue?: string;
  attendeeName?: string;
  ticketId?: string;
  accentColor?: string;
  className?: string;
}

export const Ticket3D: React.FC<Ticket3DProps> = ({
  eventName = 'Dhandiya Night 2026',
  date = '16 OCT 2026 · 6–9 PM',
  venue = 'Soundarya College Campus, Bengaluru',
  attendeeName = 'Your name here',
  ticketId = 'TKT-2026-001284',
  accentColor = '#b71959',
  className = '',
}) => {
  const [is3DMode, setIs3DMode] = useState(true);
  const [isHovered, setIsHovered] = useState(false);

  return (
    <div className={`relative flex flex-col items-center select-none ${className}`}>
      <div
        className="flex h-[460px] w-full max-w-[380px] items-center justify-center px-5 [perspective:1000px]"
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        <article
          className="relative w-full max-w-[320px] overflow-hidden rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-2xl transition-transform duration-500 ease-out motion-reduce:transform-none"
          style={{
            borderTopColor: accentColor,
            borderTopWidth: 4,
            transform: is3DMode
              ? `rotateY(${isHovered ? '-2deg' : '-7deg'}) rotateX(${isHovered ? '1deg' : '2deg'}) translateY(${isHovered ? '-4px' : '0px'})`
              : 'none',
            boxShadow: `12px 18px 40px rgba(73, 49, 20, 0.2), 0 0 34px ${accentColor}24`,
          }}
        >
          <div
            className="pointer-events-none absolute inset-x-0 top-0 h-24 opacity-20"
            style={{ background: `linear-gradient(135deg, ${accentColor}, transparent 70%)` }}
          />
          <div className="relative">
            <div className="mb-5 flex items-center justify-between border-b border-slate-800 pb-3 text-[10px] font-semibold uppercase tracking-widest">
              <span className="text-indigo-300">Soundarya • Dhandiya Night</span>
              <span className="rounded-full border border-slate-700 px-2 py-1 text-slate-400">Demo</span>
            </div>

            <div className="space-y-2">
              <p className="festival-script text-lg font-bold text-indigo-400">Dance · Dandiya · Dhamaka</p>
              <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">A festive evening</p>
              <h3 className="break-words font-display text-2xl font-bold leading-tight text-white">{eventName}</h3>
              <p className="text-xs leading-relaxed text-slate-400">{venue}</p>
              <p className="font-mono text-xs text-slate-300">{date}</p>
            </div>

            <div className="my-5 border-t border-dashed border-slate-700" />

            <div className="space-y-4">
              <div>
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Attendee</p>
                <p className="truncate text-sm font-semibold text-slate-100">{attendeeName}</p>
              </div>
              <div>
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Pass ID</p>
                <p className="break-all font-mono text-xs text-indigo-200">{ticketId}</p>
              </div>
            </div>

            <div className="mt-6 rounded-xl border border-slate-800 bg-slate-950/70 p-3">
              <div className="flex h-10 items-end justify-center gap-1 opacity-70" aria-hidden="true">
                {Array.from({ length: 28 }, (_, index) => (
                  <span
                    key={index}
                    className="w-1 bg-slate-300"
                    style={{ height: `${12 + ((index * 7) % 26)}px` }}
                  />
                ))}
              </div>
              <p className="mt-2 text-center text-[9px] font-mono tracking-wider text-slate-500">
                VISUAL PREVIEW • NOT AN ENTRY TICKET
              </p>
            </div>
          </div>
        </article>
      </div>

      <button
        onClick={() => setIs3DMode(!is3DMode)}
        className="mt-2 flex cursor-pointer items-center gap-2 rounded-full border border-slate-800 bg-slate-900/80 px-4 py-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400 transition-colors hover:border-indigo-500/50 hover:text-indigo-300"
      >
        {is3DMode ? <Eye className="h-3.5 w-3.5" /> : <RotateCw className="h-3.5 w-3.5" />}
        {is3DMode ? 'View flat pass' : 'Enable subtle 3D'}
      </button>
    </div>
  );
};
