import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { ArrowRight, Flower2, Mail, Shield } from 'lucide-react';

export const StaffLoginPage: React.FC = () => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  const handleSignIn = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsLoading(true);
    setErrorMessage('');
    try {
      const user = await login(email, password);
      const requestedPath = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname;
      const defaultPath = user.role === 'ADMIN'
        ? '/admin'
        : user.role === 'REGISTRATION'
          ? '/staff/register'
          : '/staff/scanner';
      navigate(requestedPath || defaultPath, { replace: true });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to sign in. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col justify-between p-4 sm:p-6">
      <div className="flex items-center justify-between max-w-5xl mx-auto w-full pt-4">
        <Link to="/" className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center text-white">
            <Flower2 className="w-4 h-4" />
          </div>
          <span className="flex flex-col leading-none">
            <span className="font-display font-bold text-white text-lg">Soundarya Institute</span>
            <span className="festival-script text-sm font-bold text-indigo-400">Dhandiya Night · Event Team</span>
          </span>
        </Link>
        <Link to="/" className="text-xs text-slate-400 hover:text-white transition-colors">
          &larr; Back to Public Site
        </Link>
      </div>

      <div className="max-w-md w-full mx-auto my-12">
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow-2xl space-y-6">
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-xs font-mono font-semibold text-indigo-400 uppercase tracking-wider">
              <Shield className="w-3.5 h-3.5" />
              <span>DHANDIYA NIGHT · EVENT TEAM</span>
            </div>
            <h1 className="text-2xl font-bold font-display text-white">Staff sign in</h1>
            <p className="text-xs text-slate-400">
              Use the account provided by your event administrator.
            </p>
          </div>

          {errorMessage && (
            <p role="alert" className="rounded-xl border border-rose-900/70 bg-rose-950/40 p-3 text-xs text-rose-200">
              {errorMessage}
            </p>
          )}

          <form onSubmit={handleSignIn} className="space-y-4">
            <div>
              <label htmlFor="staff-email" className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                Email
              </label>
              <div className="relative">
                <Mail className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  id="staff-email"
                  type="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-10 pr-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
                />
              </div>
            </div>
            <div>
              <label htmlFor="staff-password" className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                Password
              </label>
              <input
                id="staff-password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
              />
            </div>
            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-2 shadow-lg shadow-indigo-600/30 transition-all cursor-pointer mt-2 disabled:opacity-50"
            >
              {isLoading ? (
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                <>
                  <span>Sign in</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>
          <p className="text-[11px] leading-relaxed text-slate-500">
            Access is determined by your server-managed staff role. Contact an administrator if you need an account.
          </p>
        </div>
      </div>

      <div className="text-center text-xs text-slate-600 pb-4">
        Soundarya Dhandiya Night staff portal
      </div>
    </div>
  );
};
