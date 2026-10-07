import React from 'react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  isLoading = false,
  leftIcon,
  rightIcon,
  className = '',
  disabled,
  ...props
}) => {
  const baseStyles =
    'inline-flex items-center justify-center font-medium transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 disabled:opacity-50 disabled:pointer-events-none cursor-pointer whitespace-nowrap select-none';

  const sizes = {
    sm: 'text-xs px-3 py-1.5 rounded-md gap-1.5',
    md: 'text-sm px-4 py-2 rounded-lg gap-2',
    lg: 'text-base px-5 py-2.5 rounded-xl gap-2.5',
  };

  const variants = {
    primary:
      'bg-indigo-600 text-white hover:bg-indigo-500 active:scale-[0.98] shadow-sm shadow-indigo-600/30',
    secondary:
      'bg-slate-800 text-slate-100 hover:bg-slate-700 active:scale-[0.98] border border-slate-700',
    outline:
      'border border-slate-700 text-slate-200 hover:bg-slate-800/80 hover:text-white',
    danger:
      'bg-rose-600 text-white hover:bg-rose-500 active:scale-[0.98] shadow-sm shadow-rose-600/30',
    ghost:
      'text-slate-300 hover:text-white hover:bg-slate-800/60',
  };

  return (
    <button
      className={`${baseStyles} ${sizes[size]} ${variants[variant]} ${className}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin shrink-0" />
      ) : (
        leftIcon && <span className="shrink-0">{leftIcon}</span>
      )}
      <span>{children}</span>
      {!isLoading && rightIcon && <span className="shrink-0">{rightIcon}</span>}
    </button>
  );
};
