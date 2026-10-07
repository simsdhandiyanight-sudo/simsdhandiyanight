import React, { useEffect, useState } from 'react';
import QRCode from 'qrcode';

interface QRCodeDisplayProps {
  value: string;
  size?: number;
  className?: string;
  label?: string;
  alt?: string;
}

export const QRCodeDisplay: React.FC<QRCodeDisplayProps> = ({
  value,
  size = 180,
  className = '',
  label,
  alt = 'Ticket QR code',
}) => {
  const [imageUrl, setImageUrl] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setImageUrl('');
    setError('');

    QRCode.toDataURL(value, {
      width: size,
      margin: 2,
      errorCorrectionLevel: 'M',
      color: { dark: '#0f172a', light: '#ffffff' },
    }).then(
      (url) => {
        if (active) setImageUrl(url);
      },
      () => {
        if (active) setError('Ticket code could not be displayed.');
      }
    );

    return () => {
      active = false;
    };
  }, [size, value]);

  return (
    <div className={`flex flex-col items-center ${className}`}>
      <div
        className="flex items-center justify-center rounded-xl border border-slate-200 bg-white p-3 shadow-inner"
        style={{ width: size + 24, height: size + 24 }}
      >
        {imageUrl ? (
          <img
            src={imageUrl}
            width={size}
            height={size}
            alt={alt}
            className="block max-w-full"
          />
        ) : (
          <span role={error ? 'alert' : 'status'} className="px-3 text-center text-xs text-slate-500">
            {error || 'Preparing ticket code…'}
          </span>
        )}
      </div>
      {label && (
        <span className="mt-2 max-w-[200px] truncate font-mono text-[10px] tracking-wider text-slate-400">
          {label}
        </span>
      )}
    </div>
  );
};
