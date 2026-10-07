import React from 'react';
import { ScanResultType, Ticket, ScanRecord } from '../../types';
import { CheckCircle2, AlertTriangle, XCircle, AlertOctagon, WifiOff, ArrowRight, RotateCw } from 'lucide-react';

interface ScanResultModalProps {
  isOpen: boolean;
  result: ScanResultType;
  ticket?: Ticket;
  scanRecord?: ScanRecord;
  message?: string;
  onScanNext: () => void;
  onRetry?: () => void;
}

export const ScanResultModal: React.FC<ScanResultModalProps> = ({
  isOpen,
  result,
  ticket,
  scanRecord,
  message,
  onScanNext,
  onRetry,
}) => {
  if (!isOpen) return null;

  const timestamp = scanRecord?.scannedAt
    ? new Date(scanRecord.scannedAt).toLocaleTimeString()
    : new Date().toLocaleTimeString();

  const getResultConfig = () => {
    switch (result) {
      case 'ENTRY_GRANTED':
        return {
          bg: 'bg-emerald-950 border-emerald-500/80',
          iconBg: 'bg-emerald-500/20 text-emerald-400',
          icon: <CheckCircle2 className="w-14 h-14" />,
          title: 'ENTRY GRANTED',
          titleColor: 'text-emerald-400',
          subtitle: 'Local demo ticket accepted for this scan.',
          primaryActionText: 'SCAN NEXT TICKET',
          primaryActionVariant: 'bg-emerald-500 hover:bg-emerald-400 text-slate-950',
          audioSound: 'success',
        };
      case 'ALREADY_USED':
        return {
          bg: 'bg-amber-950 border-amber-500/80',
          iconBg: 'bg-amber-500/20 text-amber-400',
          icon: <AlertTriangle className="w-14 h-14" />,
          title: 'ALREADY USED',
          titleColor: 'text-amber-400',
          subtitle: 'This ticket has already been checked in.',
          primaryActionText: 'SCAN NEXT TICKET',
          primaryActionVariant: 'bg-amber-500 hover:bg-amber-400 text-slate-950',
          audioSound: 'warning',
        };
      case 'INVALID_TICKET':
        return {
          bg: 'bg-rose-950 border-rose-500/80',
          iconBg: 'bg-rose-500/20 text-rose-400',
          icon: <XCircle className="w-14 h-14" />,
          title: 'INVALID TICKET',
          titleColor: 'text-rose-400',
          subtitle: 'Token did not match a local demo ticket.',
          primaryActionText: 'SCAN NEXT TICKET',
          primaryActionVariant: 'bg-rose-600 hover:bg-rose-500 text-white',
          audioSound: 'error',
        };
      case 'CANCELLED':
        return {
          bg: 'bg-rose-950 border-rose-500/80',
          iconBg: 'bg-rose-500/20 text-rose-400',
          icon: <XCircle className="w-14 h-14" />,
          title: 'TICKET CANCELLED',
          titleColor: 'text-rose-400',
          subtitle: 'This ticket cannot be used for entry.',
          primaryActionText: 'SCAN NEXT TICKET',
          primaryActionVariant: 'bg-rose-600 hover:bg-rose-500 text-white',
          audioSound: 'error',
        };
      case 'EVENT_CLOSED':
        return {
          bg: 'bg-slate-900 border-rose-600',
          iconBg: 'bg-rose-500/20 text-rose-400',
          icon: <AlertOctagon className="w-14 h-14" />,
          title: 'EVENT CLOSED',
          titleColor: 'text-rose-400',
          subtitle: 'Entry is currently closed for this event.',
          primaryActionText: 'SCAN NEXT TICKET',
          primaryActionVariant: 'bg-rose-600 hover:bg-rose-500 text-white',
          audioSound: 'error',
        };
      case 'WRONG_EVENT':
        return {
          bg: 'bg-amber-950 border-amber-500/80',
          iconBg: 'bg-amber-500/20 text-amber-400',
          icon: <AlertOctagon className="w-14 h-14" />,
          title: 'WRONG EVENT',
          titleColor: 'text-amber-400',
          subtitle: 'This ticket belongs to another event.',
          primaryActionText: 'SCAN NEXT TICKET',
          primaryActionVariant: 'bg-amber-500 hover:bg-amber-400 text-slate-950',
          audioSound: 'warning',
        };
      case 'NETWORK_ERROR':
        return {
          bg: 'bg-slate-900 border-rose-600',
          iconBg: 'bg-rose-500/20 text-rose-400',
          icon: <WifiOff className="w-14 h-14" />,
          title: 'CONNECTION ERROR',
          titleColor: 'text-rose-400',
          subtitle: 'Unable to verify the ticket. Do not allow entry.',
          primaryActionText: 'RETRY VERIFICATION',
          primaryActionVariant: 'bg-rose-600 hover:bg-rose-500 text-white',
          audioSound: 'error',
        };
    }
  };

  const config = getResultConfig();

  return (
    <div
      role="dialog"
      aria-live="assertive"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md"
    >
      <div
        className={`w-full max-w-sm sm:max-w-md rounded-3xl border-2 p-6 sm:p-8 shadow-2xl flex flex-col items-center text-center transition-all transform animate-in fade-in zoom-in-95 duration-150 ${config.bg}`}
      >
        {/* Status Icon */}
        <div className={`p-4 rounded-2xl mb-4 ${config.iconBg}`}>
          {config.icon}
        </div>

        {/* Status Headline */}
        <h2 className={`text-2xl sm:text-3xl font-display font-extrabold tracking-tight mb-2 ${config.titleColor}`}>
          {config.title}
        </h2>
        <p className="text-sm text-slate-200 mb-6 font-medium max-w-xs">
          {message || config.subtitle}
        </p>

        {/* Detailed Attendee & Ticket Info */}
        {(ticket || scanRecord) && (
          <div className="w-full bg-black/40 rounded-2xl p-4 mb-6 border border-white/10 text-left space-y-2.5">
            {ticket?.attendeeName && (
              <div className="flex justify-between items-center pb-2 border-b border-white/10">
                <span className="text-xs text-slate-400 uppercase font-semibold">ATTENDEE</span>
                <span className="text-sm font-bold text-white">{ticket.attendeeName}</span>
              </div>
            )}

            <div className="flex justify-between items-center text-xs">
              <span className="text-slate-400 uppercase font-semibold">EVENT</span>
              <span className="font-semibold text-slate-200 truncate max-w-[200px]">
                {ticket?.eventName || scanRecord?.eventName}
              </span>
            </div>

            <div className="flex justify-between items-center text-xs">
              <span className="text-slate-400 uppercase font-semibold">TIME</span>
              <span className="font-mono text-slate-200">{timestamp}</span>
            </div>

            <div className="flex justify-between items-center text-xs">
              <span className="text-slate-400 uppercase font-semibold">TICKET ID</span>
              <span className="font-mono text-indigo-300">
                {ticket?.id || scanRecord?.ticketId}
              </span>
            </div>

            {scanRecord?.gate && (
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-400 uppercase font-semibold">GATE / OPERATOR</span>
                <span className="text-slate-300">
                  {scanRecord.gate} · {scanRecord.staffName}
                </span>
              </div>
            )}
          </div>
        )}

        {/* Big Operational Touch Target Action Button */}
        <div className="w-full space-y-2">
          {result === 'NETWORK_ERROR' ? (
            <button
              onClick={onRetry || onScanNext}
              className={`w-full py-4 px-6 rounded-2xl font-bold text-base flex items-center justify-center gap-2 cursor-pointer shadow-lg active:scale-[0.98] transition-transform ${config.primaryActionVariant}`}
            >
              <RotateCw className="w-5 h-5" />
              <span>RETRY VERIFICATION</span>
            </button>
          ) : (
            <button
              onClick={onScanNext}
              autoFocus
              className={`w-full py-4 px-6 rounded-2xl font-bold text-base flex items-center justify-center gap-2 cursor-pointer shadow-lg active:scale-[0.98] transition-transform ${config.primaryActionVariant}`}
            >
              <span>SCAN NEXT TICKET</span>
              <ArrowRight className="w-5 h-5" />
            </button>
          )}

          {result !== 'ENTRY_GRANTED' && (
            <button
              onClick={onScanNext}
              className="w-full py-2.5 text-xs text-slate-400 hover:text-white font-medium cursor-pointer transition-colors"
            >
              Dismiss and return to camera
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
