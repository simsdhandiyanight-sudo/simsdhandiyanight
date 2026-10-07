import React from 'react';

interface StatCardProps {
  label: string;
  value: string | number;
  subValue?: string;
  trend?: {
    value: string;
    isPositive?: boolean;
  };
  icon?: React.ReactNode;
  accentColor?: string;
}

export const StatCard: React.FC<StatCardProps> = ({
  label,
  value,
  subValue,
  trend,
  icon,
}) => {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 hover:border-slate-700 transition-all">
      <div className="flex items-center justify-between text-slate-400 mb-2">
        <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">
          {label}
        </span>
        {icon && <span className="text-slate-400">{icon}</span>}
      </div>

      <div className="flex items-baseline gap-2">
        <span className="text-2xl sm:text-3xl font-extrabold text-white font-mono tabular-nums tracking-tight">
          {value}
        </span>
        {trend && (
          <span
            className={`text-xs font-medium font-mono ${
              trend.isPositive ? 'text-emerald-400' : 'text-rose-400'
            }`}
          >
            {trend.value}
          </span>
        )}
      </div>

      {subValue && (
        <p className="text-xs text-slate-400 mt-1 font-normal">{subValue}</p>
      )}
    </div>
  );
};
