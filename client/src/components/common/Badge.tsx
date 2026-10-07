import React from 'react';

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'neutral' | 'success' | 'warning' | 'error' | 'indigo';
  size?: 'sm' | 'md';
  dot?: boolean;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'neutral',
  size = 'md',
  dot = false,
}) => {
  const styles = {
    neutral: 'bg-slate-800/80 text-slate-300 border-slate-700/60',
    success: 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60',
    warning: 'bg-amber-950/60 text-amber-300 border-amber-800/60',
    error: 'bg-rose-950/60 text-rose-300 border-rose-800/60',
    indigo: 'bg-indigo-950/60 text-indigo-300 border-indigo-800/60',
  };

  const dotColors = {
    neutral: 'bg-slate-400',
    success: 'bg-emerald-400',
    warning: 'bg-amber-400',
    error: 'bg-rose-400',
    indigo: 'bg-indigo-400',
  };

  const sizeClasses = size === 'sm' ? 'text-[11px] px-2 py-0.5' : 'text-xs px-2.5 py-1';

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-medium rounded-md border ${sizeClasses} ${styles[variant]} tabular-nums whitespace-nowrap`}
    >
      {dot && <span className={`w-1.5 h-1.5 rounded-full ${dotColors[variant]}`} />}
      {children}
    </span>
  );
};
