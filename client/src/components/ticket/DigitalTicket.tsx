import React, { useRef, useState } from 'react';
import { Ticket as TicketType } from '../../types';
import { QRCodeDisplay } from './QRCodeDisplay';
import { Badge } from '../common/Badge';
import { Copy, Check, Download, MapPin, Calendar, Clock, Sparkles } from 'lucide-react';

interface DigitalTicketProps {
  ticket: TicketType;
  showActions?: boolean;
}

export const DigitalTicket: React.FC<DigitalTicketProps> = ({ ticket, showActions = true }) => {
  const ticketRef = useRef<HTMLDivElement>(null);
  const [copiedValue, setCopiedValue] = useState('');
  const [copyMessage, setCopyMessage] = useState('');
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState('');

  const handleCopy = async (value: string, label: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedValue(value);
      setCopyMessage(`${label} copied.`);
      window.setTimeout(() => setCopiedValue(''), 2000);
    } catch {
      setCopiedValue('');
      setCopyMessage(`Could not copy ${label.toLowerCase()}.`);
    }
  };

  const handleDownloadTicket = async () => {
    if (!ticketRef.current) {
      setDownloadError('Ticket is not ready to download. Please try again.');
      return;
    }

    setIsDownloading(true);
    setDownloadError('');
    try {
      const [{ toPng }, { jsPDF }] = await Promise.all([
        import('html-to-image'),
        import('jspdf'),
      ]);
      await document.fonts.ready;
      const ticketImage = await toPng(ticketRef.current, {
        backgroundColor: '#fffaf0',
        filter: (element) => !(element instanceof HTMLButtonElement),
        pixelRatio: 2,
        skipFonts: true,
      });
      const pageWidth = 105;
      const image = new Image();
      image.src = ticketImage;
      await image.decode();
      const pageHeight = pageWidth * (image.height / image.width);
      const pdf = new jsPDF({
        orientation: 'portrait',
        unit: 'mm',
        format: [pageWidth, pageHeight],
      });
      pdf.addImage(ticketImage, 'PNG', 0, 0, pageWidth, pageHeight);
      pdf.save(`${ticket.id}.pdf`);
    } catch (error) {
      console.error('Failed to generate ticket PDF.', error);
      setDownloadError('Ticket could not be downloaded. Please try again.');
    } finally {
      setIsDownloading(false);
    }
  };

  const getStatusBadge = () => {
    switch (ticket.status) {
      case 'ISSUED':
        return (
          <Badge variant="success" dot>
            ACTIVE ENTRY PASS
          </Badge>
        );
      case 'USED':
        return (
          <Badge variant="warning" dot>
            CHECKED IN ({ticket.gate || 'GATE'})
          </Badge>
        );
      case 'CANCELLED':
        return (
          <Badge variant="error" dot>
            CANCELLED
          </Badge>
        );
    }
  };

  return (
    <div className="flex flex-col items-center max-w-md w-full mx-auto">
      {/* Physical Ticket Shell */}
      <div
        ref={ticketRef}
        className="festival-ticket-shell w-full bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-2xl relative transition-all duration-200"
      >
        {/* Top Header Foil Strip */}
        <div className="bg-gradient-to-r from-indigo-700 via-indigo-600 to-violet-600 px-6 py-4 flex items-center justify-between text-white relative overflow-hidden">
          <div className="flex items-center gap-2 z-10">
            <Sparkles className="w-4 h-4 text-indigo-200" />
            <span className="text-xs font-semibold tracking-wider uppercase font-mono">
              SOUNDARYA · DHANDIYA NIGHT
            </span>
          </div>
          <div className="z-10 flex items-center gap-2">
            <span className="text-[11px] font-mono bg-white/20 px-2 py-0.5 rounded text-white font-medium">
              SOURCE: {ticket.source}
            </span>
          </div>
          <div className="absolute inset-0 bg-white/5 opacity-40 pointer-events-none" />
        </div>

        <div className="festival-ticket-art">
          <img
            src="/dhandiya-night-poster.jpeg"
            alt="Dhandiya Night festival artwork"
            loading="lazy"
          />
          <span className="absolute bottom-2 right-2 rounded-full border border-amber-200 bg-amber-50/95 px-2.5 py-1 text-[9px] font-bold uppercase tracking-wider text-blue-950">
            Daksha Student Council
          </span>
        </div>

        {/* Main Event Section */}
        <div className="p-6 sm:p-7 space-y-5">
          <div className="space-y-1">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-indigo-400 font-mono tracking-wider">
                {ticket.tierName.toUpperCase()}
              </span>
              {getStatusBadge()}
            </div>
            <h2 className="text-2xl font-bold font-display text-white tracking-tight">
              {ticket.eventName}
            </h2>
          </div>

          {/* Time & Venue Matrix */}
          <div className="grid grid-cols-2 gap-3 text-xs bg-slate-950/70 p-3.5 rounded-xl border border-slate-800/80">
            <div className="flex items-start gap-2 text-slate-300">
              <Calendar className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-[10px] text-slate-500 font-semibold uppercase">DATE</p>
                <p className="font-semibold text-slate-200 font-mono">{ticket.eventDate}</p>
              </div>
            </div>
            <div className="flex items-start gap-2 text-slate-300">
              <Clock className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-[10px] text-slate-500 font-semibold uppercase">TIME</p>
                <p className="font-semibold text-slate-200 font-mono">{ticket.eventTime}</p>
              </div>
            </div>
            <div className="col-span-2 flex items-start gap-2 text-slate-300 pt-2 border-t border-slate-800/80">
              <MapPin className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-[10px] text-slate-500 font-semibold uppercase">VENUE</p>
                <p className="font-medium text-slate-200">{ticket.venue}</p>
              </div>
            </div>
          </div>

          {/* Attendee Info Card */}
          <div className="flex items-center justify-between p-3.5 bg-slate-950/40 rounded-xl border border-slate-800/50">
            <div>
              <p className="text-[10px] text-slate-500 uppercase font-semibold tracking-wider">
                REGISTERED ATTENDEE
              </p>
              <p className="text-sm font-semibold text-slate-100">{ticket.attendeeName}</p>
              <p className="text-xs text-slate-400 truncate max-w-[200px]">{ticket.attendeeEmail}</p>
            </div>
            <div className="text-right">
              <p className="text-[10px] text-slate-500 uppercase font-semibold tracking-wider">
                REGISTRATION ID
              </p>
              <p className="text-xs font-mono text-indigo-300 font-semibold">{ticket.registrationId}</p>
            </div>
          </div>
        </div>

        {/* Perforated Divider with Cutout Notches */}
        <div className="relative flex items-center justify-between px-3 py-2 bg-slate-950/90 border-y border-dashed border-slate-800">
          <div className="w-5 h-5 -ml-6 bg-slate-950 rounded-full border border-slate-800" />
          <div className="flex-1 border-t border-dashed border-slate-700/60 mx-4" />
          <span className="text-[10px] font-mono text-slate-500 uppercase tracking-widest px-2">
            SCAN AT GATE
          </span>
          <div className="flex-1 border-t border-dashed border-slate-700/60 mx-4" />
          <div className="w-5 h-5 -mr-6 bg-slate-950 rounded-full border border-slate-800" />
        </div>

        {/* QR Code & Barcode Section */}
        <div className="p-6 bg-slate-900 flex flex-col items-center space-y-4">
          <QRCodeDisplay value={ticket.qrToken} size={168} />

          <div className="w-full text-center space-y-1">
            <div className="inline-flex items-center gap-2 px-3 py-1 bg-slate-950 rounded-lg border border-slate-800 text-xs font-mono text-slate-300">
              <span>{ticket.id}</span>
              <button
                onClick={() => void handleCopy(ticket.id, 'Ticket ID')}
                className="hover:text-indigo-400 transition-colors cursor-pointer"
                title="Copy Ticket ID"
                aria-label="Copy ticket ID"
              >
                {copiedValue === ticket.id ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              </button>
            </div>
            <p className="text-[11px] text-slate-500">
              Prototype ticket • local demo status, not server-validated
            </p>
            <button
              type="button"
              onClick={() => void handleCopy(ticket.qrToken, 'Scan token')}
              className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-slate-800 px-2.5 py-1.5 text-[10px] font-medium text-slate-400 transition-colors hover:border-indigo-500/50 hover:text-indigo-300"
            >
              {copiedValue === ticket.qrToken ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
              {copiedValue === ticket.qrToken ? 'Scan token copied' : 'Copy scan token for manual entry'}
            </button>
            <span className="sr-only" role="status">{copyMessage}</span>
          </div>

          {/* Barcode styling lines */}
          <div className="w-full flex justify-center gap-1 pt-1 opacity-70">
            {Array.from({ length: 32 }).map((_, i) => (
              <div
                key={i}
                className={`h-7 bg-slate-400 ${
                  i % 4 === 0 ? 'w-1.5' : i % 2 === 0 ? 'w-1' : 'w-0.5'
                }`}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Action Buttons Toolbar */}
      {showActions && (
        <div className="mt-4 w-full">
          <button
            type="button"
            onClick={handleDownloadTicket}
            disabled={isDownloading}
            aria-busy={isDownloading}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-amber-300/70 bg-gradient-to-r from-rose-700 to-fuchsia-700 px-4 py-3 text-sm font-semibold text-white shadow-md transition-colors hover:from-rose-800 hover:to-fuchsia-800"
          >
            <Download className="h-4 w-4" />
            <span>{isDownloading ? 'Preparing Ticket…' : 'Download Ticket'}</span>
          </button>
          {downloadError && <p role="alert" className="mt-2 text-center text-xs text-rose-700">{downloadError}</p>}
        </div>
      )}
      {copyMessage && <p role="status" className="mt-2 text-center text-[11px] text-slate-400">{copyMessage}</p>}
    </div>
  );
};
