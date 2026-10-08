import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { eventsApi, FEATURED_EVENT_SLUG } from '../../api/events';
import { scansApi } from '../../api/scans';
import { EventItem, ScanRecord, ScanResultType, Ticket } from '../../types';
import { useAuth } from '../../context/AuthContext';
import { ScannerFrame } from '../../components/scanner/ScannerFrame';
import { ScanResultModal } from '../../components/scanner/ScanResultModal';
import {
  ArrowLeft,
  Clock,
  CheckCircle2,
  AlertTriangle,
  XCircle,
} from 'lucide-react';

export const StaffScannerPage: React.FC = () => {
  const { user } = useAuth();
  const [activeEvent, setActiveEvent] = useState<EventItem | null>(null);
  const [scans, setScans] = useState<ScanRecord[]>([]);
  const [loadingEvent, setLoadingEvent] = useState(true);
  const [eventError, setEventError] = useState('');
  const [historyError, setHistoryError] = useState('');
  const [lastScannedCode, setLastScannedCode] = useState('');

  const [modalOpen, setModalOpen] = useState(false);
  const [scanResult, setScanResult] = useState<ScanResultType>('ENTRY_GRANTED');
  const [scannedTicket, setScannedTicket] = useState<Ticket | undefined>(undefined);
  const [currentScanRecord, setCurrentScanRecord] = useState<ScanRecord | undefined>(undefined);
  const [resultMessage, setResultMessage] = useState('');

  useEffect(() => {
    let cancelled = false;
    const loadScanner = async () => {
      try {
        const event = await eventsApi.getById(FEATURED_EVENT_SLUG);
        if (!event) throw new Error('Dhandiya Night event details are currently unavailable.');
        if (cancelled) return;
        setActiveEvent(event);
        setLoadingEvent(false);
        try {
          const page = await scansApi.getPage({ eventId: event.id });
          if (!cancelled) setScans(page.results);
        } catch (error) {
          if (!cancelled) setHistoryError(error instanceof Error ? error.message : 'Unable to load recent scans.');
        }
      } catch (error) {
        if (!cancelled) {
          setEventError(error instanceof Error ? error.message : 'Unable to load event details.');
          setLoadingEvent(false);
        }
      }
    };
    void loadScanner();
    return () => { cancelled = true; };
  }, []);

  const handleScanCode = async (rawCode: string) => {
    setLastScannedCode(rawCode);
    if (!activeEvent) {
      setScanResult('NETWORK_ERROR');
      setScannedTicket(undefined);
      setCurrentScanRecord(undefined);
      setResultMessage(eventError || 'The event is unavailable. Do not allow entry.');
      setModalOpen(true);
      return;
    }
    const gate = user?.assignedGate || 'Gate 2';

    try {
      const verification = await scansApi.verifyTicket(rawCode, activeEvent.id, gate);
      setScanResult(verification.result);
      setScannedTicket(verification.ticket);
      setCurrentScanRecord(verification.scanRecord);
      setResultMessage(verification.message);
      setScans((current) => [verification.scanRecord, ...current.filter((scan) => scan.id !== verification.scanRecord.id)]);
    } catch (error) {
      setScanResult('NETWORK_ERROR');
      setScannedTicket(undefined);
      setCurrentScanRecord(undefined);
      setResultMessage(error instanceof Error ? error.message : 'Unable to verify this ticket. Do not allow entry.');
    }
    setModalOpen(true);
  };

  const handleScanNext = () => {
    setModalOpen(false);
    setScannedTicket(undefined);
    setCurrentScanRecord(undefined);
    setResultMessage('');
  };

  const handleRetry = () => {
    if (lastScannedCode) void handleScanCode(lastScannedCode);
  };

  const recentEventScans = scans
    .filter((scan) => scan.eventId === activeEvent?.id && scan.gate === (user?.assignedGate || 'Gate 2'))
    .slice(0, 5);

  if (loadingEvent) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" aria-label="Loading scanner" />
      </div>
    );
  }

  return (
    <div className="scanner-ops min-h-screen bg-slate-950 text-slate-100 flex flex-col justify-between selection:bg-indigo-500">
      {/* Mobile-first Header: Reachable, compact */}
      <header className="bg-slate-900 border-b border-slate-800 px-4 py-3 flex items-center justify-between sticky top-0 z-30">
        <div className="flex items-center gap-2.5">
          {user?.role === 'ADMIN' && (
            <Link
              to="/admin"
              className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
              title="Back to Admin Panel"
              aria-label="Back to admin panel"
            >
              <ArrowLeft className="w-5 h-5" />
            </Link>
          )}
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-white text-xs sm:text-sm font-display truncate max-w-[180px] sm:max-w-xs">
                {activeEvent?.name}
              </span>
            </div>
            <p className="text-[10px] text-slate-400 font-mono">
              STAFF: {user?.name || 'Gate Operator'} &bull; {user?.assignedGate || 'Gate 2'}
            </p>
          </div>
        </div>

        <span className="rounded-full border border-amber-300/40 bg-amber-300/10 px-2.5 py-1 text-[10px] font-semibold text-amber-100">
          Dhandiya Night
        </span>
      </header>

      {/* Center Viewfinder Section */}
      <main className="flex-1 p-4 sm:p-6 flex flex-col items-center justify-center max-w-lg mx-auto w-full">
        {eventError && <div role="alert" className="mb-4 w-full rounded-xl border border-rose-900/60 bg-rose-950/30 px-4 py-3 text-xs text-rose-200">{eventError}</div>}
        {historyError && <div role="alert" className="mb-4 w-full rounded-xl border border-amber-900/60 bg-amber-950/30 px-4 py-3 text-xs text-amber-200">{historyError}</div>}
        <ScannerFrame onScan={handleScanCode} isScanning={!modalOpen} />

        {/* Recent Scans Drawer on Mobile */}
        <div className="w-full mt-6 bg-slate-900 border border-slate-800 rounded-2xl p-4">
          <div className="flex items-center justify-between mb-3 text-xs">
            <span className="font-semibold text-slate-300 uppercase tracking-wider font-mono flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-indigo-400" />
              <span>Recent scans for this gate</span>
            </span>
            <span className="text-[11px] font-mono text-slate-500">Last 5 scans</span>
          </div>

          <div className="divide-y divide-slate-800">
            {recentEventScans.length === 0 ? (
              <div className="py-4 text-center text-xs text-slate-500 font-mono">
                No tickets scanned yet this session
              </div>
            ) : (
              recentEventScans.map((s) => {
                const isSuccess = s.result === 'ENTRY_GRANTED';
                const isUsed = s.result === 'ALREADY_USED';

                return (
                  <div key={s.id} className="py-2 flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      {isSuccess ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                      ) : isUsed ? (
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                      ) : (
                        <XCircle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                      )}
                      <div>
                        <span className="font-semibold text-white block">{s.attendeeName}</span>
                        <span className="text-[10px] text-slate-400 font-mono">
                          {s.ticketId} &bull; {s.gate}
                        </span>
                      </div>
                    </div>

                    <div className="text-right">
                      <span
                        className={`text-[10px] font-mono font-bold block ${
                          isSuccess
                            ? 'text-emerald-400'
                            : isUsed
                            ? 'text-amber-400'
                            : 'text-rose-400'
                        }`}
                      >
                        {s.result}
                      </span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        {new Date(s.scannedAt).toLocaleTimeString()}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </main>

      {/* Operational Bottom Controls */}
      <footer className="p-3 bg-slate-900 border-t border-slate-800 text-center text-[11px] text-slate-500 flex items-center justify-between max-w-lg mx-auto w-full">
        <span>Soundarya Dhandiya Night · Gate Operations · Backend connected</span>
      </footer>

      {/* Modal Result Pop-up with Immediate Visual Clarity */}
      <ScanResultModal
        isOpen={modalOpen}
        result={scanResult}
        ticket={scannedTicket}
        scanRecord={currentScanRecord}
        message={resultMessage}
        onScanNext={handleScanNext}
        onRetry={handleRetry}
      />
    </div>
  );
};
