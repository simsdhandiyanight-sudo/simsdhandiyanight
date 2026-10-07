import React, { useEffect, useRef, useState } from 'react';
import { Camera, Flashlight, KeyRound, RefreshCw } from 'lucide-react';

interface ScannerFrameProps {
  onScan: (code: string) => void;
  isScanning?: boolean;
  className?: string;
}

type DetectedBarcode = { rawValue: string };
type BarcodeDetectorInstance = {
  detect: (source: HTMLVideoElement) => Promise<DetectedBarcode[]>;
};
type BarcodeDetectorConstructor = new (options: { formats: string[] }) => BarcodeDetectorInstance;
type TorchCapabilities = MediaTrackCapabilities & { torch?: boolean };


export const ScannerFrame: React.FC<ScannerFrameProps> = ({
  onScan,
  isScanning = true,
  className = '',
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const scanCallbackRef = useRef(onScan);
  const [manualInput, setManualInput] = useState('');
  const [cameraFacing, setCameraFacing] = useState<'environment' | 'user'>('environment');
  const [cameraMessage, setCameraMessage] = useState('Allow camera access to scan a ticket QR code.');
  const [cameraReady, setCameraReady] = useState(false);
  const [torchSupported, setTorchSupported] = useState(false);
  const [torchOn, setTorchOn] = useState(false);

  useEffect(() => {
    scanCallbackRef.current = onScan;
  }, [onScan]);

  useEffect(() => {
    if (!isScanning) return;

    let disposed = false;
    let detectionTimer: number | undefined;
    const video = videoRef.current;
    const detectorConstructor = (window as Window & {
      BarcodeDetector?: BarcodeDetectorConstructor;
    }).BarcodeDetector;

    setCameraReady(false);
    setTorchSupported(false);
    setTorchOn(false);

    if (!detectorConstructor) {
      setCameraMessage('Camera QR scanning is not supported in this browser. Use manual entry.');
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !video) {
      setCameraMessage('Camera access is unavailable. Use HTTPS or localhost, or enter a ticket token manually.');
      return;
    }

    const stopStream = () => {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      if (video) video.srcObject = null;
    };

    const startCamera = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: {
            facingMode: { ideal: cameraFacing },
            width: { ideal: 1280 },
            height: { ideal: 960 },
          },
        });
        if (disposed) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }

        streamRef.current = stream;
        video.srcObject = stream;
        await video.play();
        if (disposed) return;

        const track = stream.getVideoTracks()[0];
        setTorchSupported(Boolean((track?.getCapabilities() as TorchCapabilities | undefined)?.torch));
        setCameraReady(true);
        setCameraMessage('Camera ready. Center the ticket QR code in the frame.');

        const detector = new detectorConstructor({ formats: ['qr_code'] });
        const detectFrame = async () => {
          if (disposed) return;
          try {
            const codes = await detector.detect(video);
            const code = codes.find((item) => item.rawValue.trim())?.rawValue;
            if (code) {
              scanCallbackRef.current(code);
              return;
            }
          } catch {
            if (!disposed) {
              setCameraReady(false);
              setCameraMessage('QR detection stopped. Manual entry is still available.');
            }
            return;
          }
          if (!disposed) detectionTimer = window.setTimeout(() => void detectFrame(), 180);
        };
        void detectFrame();
      } catch (error) {
        if (disposed) return;
        const name = error instanceof DOMException ? error.name : '';
        setCameraMessage(
          name === 'NotFoundError'
            ? 'No camera was found on this device. Manual entry is still available.'
            : 'Camera permission was denied or unavailable. Check browser permissions or use manual entry.'
        );
      }
    };

    void startCamera();
    return () => {
      disposed = true;
      if (detectionTimer !== undefined) window.clearTimeout(detectionTimer);
      stopStream();
    };
  }, [cameraFacing, isScanning]);

  const handleManualSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const code = manualInput.trim();
    if (!code) return;
    onScan(code);
    setManualInput('');
  };

  const handleTorchToggle = async () => {
    const track = streamRef.current?.getVideoTracks()[0];
    if (!track || !torchSupported) return;
    const nextTorchState = !torchOn;
    try {
      await track.applyConstraints({
        advanced: [{ torch: nextTorchState } as MediaTrackConstraintSet],
      });
      setTorchOn(nextTorchState);
    } catch {
      setTorchSupported(false);
      setCameraMessage('Flashlight control is unavailable on this camera.');
    }
  };

  return (
    <div className={`mx-auto flex w-full max-w-md flex-col items-center ${className}`}>
      <section className="relative aspect-[4/4.5] w-full overflow-hidden rounded-3xl border border-slate-700 bg-slate-950 shadow-2xl sm:aspect-square">
        <video
          ref={videoRef}
          autoPlay
          muted
          playsInline
          aria-label="Live ticket QR camera preview"
          className={`absolute inset-0 h-full w-full object-cover ${cameraReady ? 'opacity-100' : 'opacity-0'}`}
        />
        <div
          className={`pointer-events-none absolute inset-0 bg-[radial-gradient(#38bdf8_1px,transparent_1px)] [background-size:16px_16px] ${
            cameraReady ? 'opacity-10' : 'opacity-20'
          }`}
        />

        <div className="absolute inset-x-0 top-0 z-10 flex items-center justify-between bg-gradient-to-b from-black/80 to-transparent p-3 sm:p-4">
          <div
            className={`flex min-w-0 items-center gap-2 rounded-full border px-2.5 py-1 text-[10px] font-mono sm:text-xs ${
              cameraReady
                ? 'border-emerald-500/30 bg-slate-900/80 text-emerald-300'
                : 'border-slate-700 bg-slate-900/80 text-slate-300'
            }`}
          >
            <span className={`h-2 w-2 shrink-0 rounded-full ${cameraReady ? 'animate-pulse bg-emerald-400' : 'bg-slate-500'}`} />
            <span className="truncate">{cameraReady ? 'CAMERA READY' : 'CAMERA OFF'}</span>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => void handleTorchToggle()}
              disabled={!cameraReady || !torchSupported}
              className={`rounded-full p-2 transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                torchOn ? 'bg-amber-400 text-slate-950' : 'bg-slate-800/90 text-white hover:bg-slate-700'
              }`}
              title={torchSupported ? 'Toggle flashlight' : 'Flashlight unavailable'}
              aria-label="Toggle flashlight"
            >
              <Flashlight className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setCameraFacing((facing) => (facing === 'environment' ? 'user' : 'environment'))}
              className="rounded-full bg-slate-800/90 p-2 text-white transition-colors hover:bg-slate-700"
              title="Switch camera"
              aria-label="Switch camera"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="absolute inset-0 flex items-center justify-center px-5 pt-8">
          <div className="relative aspect-square w-[min(72vw,18rem)] max-w-full rounded-2xl border border-slate-600/50">
            <span className="absolute left-0 top-0 h-8 w-8 rounded-tl-xl border-l-4 border-t-4 border-indigo-400" />
            <span className="absolute right-0 top-0 h-8 w-8 rounded-tr-xl border-r-4 border-t-4 border-indigo-400" />
            <span className="absolute bottom-0 left-0 h-8 w-8 rounded-bl-xl border-b-4 border-l-4 border-indigo-400" />
            <span className="absolute bottom-0 right-0 h-8 w-8 rounded-br-xl border-b-4 border-r-4 border-indigo-400" />
            {cameraReady && isScanning && (
              <div className="absolute left-2 right-2 top-1/2 h-0.5 animate-scanline bg-gradient-to-r from-transparent via-indigo-400 to-transparent shadow-[0_0_12px_#818cf8]" />
            )}
            {!cameraReady && (
              <div className="absolute inset-3 flex flex-col items-center justify-center gap-3 rounded-xl bg-slate-950/80 p-4 text-center backdrop-blur-sm">
                <Camera className="h-8 w-8 text-indigo-300" />
                <p className="text-xs leading-relaxed text-slate-300">{cameraMessage}</p>
              </div>
            )}
            {cameraReady && (
              <div className="absolute inset-x-0 bottom-3 text-center text-[11px] font-medium text-white drop-shadow">
                Center ticket QR within the frame
              </div>
            )}
          </div>
        </div>
        <div className="absolute inset-x-0 bottom-0 z-10 bg-gradient-to-t from-black/90 via-black/60 to-transparent p-3 text-center text-[11px] text-slate-300 sm:p-4">
          Ticket scans are verified by the ticketing service.
        </div>
      </section>

      <form onSubmit={handleManualSubmit} className="mt-4 flex w-full gap-2">
        <label className="relative min-w-0 flex-1">
          <span className="sr-only">Ticket QR token</span>
          <KeyRound className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={manualInput}
            onChange={(event) => setManualInput(event.target.value)}
            placeholder="Paste opaque ticket token"
            autoComplete="off"
            className="w-full rounded-xl border border-slate-800 bg-slate-900 py-3 pl-10 pr-3 font-mono text-xs text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </label>
        <button
          type="submit"
          disabled={!manualInput.trim() || !isScanning}
          className="rounded-xl bg-indigo-600 px-4 py-3 text-xs font-semibold text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Verify
        </button>
      </form>

    </div>
  );
};
