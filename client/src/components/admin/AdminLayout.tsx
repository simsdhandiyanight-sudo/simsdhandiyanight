import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Users,
  Ticket,
  ScanLine,
  BarChart3,
  Flower2,
  Menu,
  X,
  ExternalLink,
  ChevronRight,
  LogOut,
  Mail,
  CreditCard,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

interface AdminLayoutProps {
  children: React.ReactNode;
  title: string;
  breadcrumbs?: { label: string; href?: string }[];
  actions?: React.ReactNode;
}

export const AdminLayout: React.FC<AdminLayoutProps> = ({
  children,
  title,
  breadcrumbs = [],
  actions,
}) => {
  const location = useLocation();
  const { user, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [logoutError, setLogoutError] = useState('');

  const handleLogout = async () => {
    setLogoutError('');
    try {
      await logout();
    } catch (error) {
      setLogoutError(error instanceof Error ? error.message : 'Unable to sign out.');
    }
  };

  const navItems = [
    { label: 'Overview', href: '/admin', icon: LayoutDashboard },
    { label: 'Registrations', href: '/admin/registrations', icon: Users },
    { label: 'Tickets', href: '/admin/tickets', icon: Ticket },
    { label: 'Scan History', href: '/admin/scans', icon: ScanLine },
    { label: 'Analytics & Reports', href: '/admin/reports', icon: BarChart3 },
    { label: 'Email Delivery', href: '/admin/email-delivery', icon: Mail },
    { label: 'Payment Review', href: '/admin/payment-review', icon: CreditCard },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex">
      {/* Sidebar Desktop */}
      <aside className="hidden lg:flex w-64 flex-col border-r border-slate-800 bg-slate-950 shrink-0">
        {/* Brand */}
        <div className="h-16 px-6 flex items-center justify-between border-b border-slate-800">
          <Link to="/" className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center text-white">
              <Flower2 className="w-4 h-4" />
            </div>
            <span className="font-display font-bold text-white tracking-tight">Soundarya</span>
            <span className="text-[10px] uppercase font-mono text-indigo-400 bg-indigo-950/60 px-1.5 py-0.5 rounded border border-indigo-800/60">
              Dhandiya Ops
            </span>
          </Link>
        </div>

        {/* Navigation list */}
        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item) => {
            const isActive =
              item.href === '/admin'
                ? location.pathname === '/admin'
                : location.pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                to={item.href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-medium transition-all ${
                  isActive
                    ? 'bg-indigo-600 text-white font-semibold shadow-sm shadow-indigo-600/30'
                    : 'text-slate-400 hover:text-white hover:bg-slate-900'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-white' : 'text-slate-400'}`} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t border-slate-800 bg-slate-900/40">
          <div className="text-xs font-semibold text-white">{user?.name}</div>
          <div className="mt-1 text-[10px] font-mono uppercase text-slate-400">
            {user?.role} {user?.assignedGate ? `· ${user.assignedGate}` : ''}
          </div>
          {logoutError && <p role="alert" className="mt-2 text-[10px] text-rose-300">{logoutError}</p>}
          <div className="pt-3 mt-3 border-t border-slate-800 flex items-center justify-between">
            <Link
              to="/staff/scanner"
              className="text-[11px] text-indigo-400 hover:text-indigo-300 flex items-center gap-1"
            >
              <span>Open Scanner</span>
              <ExternalLink className="w-3 h-3" />
            </Link>
            <Link
              to="/staff/register"
              className="text-[11px] text-slate-400 hover:text-slate-200"
            >
              On-Spot Desk
            </Link>
          </div>
          <button
            onClick={() => void handleLogout()}
            className="mt-3 inline-flex items-center gap-2 text-[11px] text-slate-400 hover:text-white"
          >
            <LogOut className="h-3.5 w-3.5" />
            Sign out
          </button>
        </div>
      </aside>

      {/* Main Content Viewport */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Header Bar Contract */}
        <header className="h-16 border-b border-slate-800 px-4 sm:px-8 flex items-center justify-between bg-slate-950 sticky top-0 z-30">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="lg:hidden p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 cursor-pointer"
              aria-label="Toggle navigation menu"
            >
              <Menu className="w-5 h-5" />
            </button>

            {/* Breadcrumb Trail */}
            <nav className="flex items-center gap-2 text-xs text-slate-400">
              <Link to="/admin" className="hover:text-white transition-colors">
                Console
              </Link>
              {breadcrumbs.map((b, idx) => (
                <React.Fragment key={idx}>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-600" />
                  {b.href ? (
                    <Link to={b.href} className="hover:text-white transition-colors">
                      {b.label}
                    </Link>
                  ) : (
                    <span className="text-slate-200 font-medium">{b.label}</span>
                  )}
                </React.Fragment>
              ))}
            </nav>
          </div>

          {/* Top Actions */}
          <div className="flex items-center gap-3">
            {actions}
            <button
              onClick={() => void handleLogout()}
              aria-label="Sign out"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-400 hover:text-white bg-slate-900 border border-slate-800 rounded-lg transition-colors"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Sign out</span>
            </button>
            <Link
              to="/"
              className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-400 hover:text-white bg-slate-900 border border-slate-800 rounded-lg transition-colors"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>Public Site</span>
            </Link>
          </div>
        </header>

        {/* Mobile Sidebar Modal/Drawer */}
        {sidebarOpen && (
          <div className="lg:hidden fixed inset-0 z-50 flex">
            <div
              className="fixed inset-0 bg-black/80 backdrop-blur-sm"
              onClick={() => setSidebarOpen(false)}
            />
            <div className="relative w-64 bg-slate-950 border-r border-slate-800 flex flex-col p-4 z-10">
              <div className="flex items-center justify-between pb-4 border-b border-slate-800 mb-4">
                <span className="font-display font-bold text-white">Soundarya · Event Ops</span>
                <button
                  onClick={() => setSidebarOpen(false)}
                  className="p-1.5 text-slate-400 hover:text-white"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              <nav className="space-y-1">
                {navItems.map((item) => (
                  <Link
                    key={item.href}
                    to={item.href}
                    onClick={() => setSidebarOpen(false)}
                    className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-medium text-slate-300 hover:bg-slate-900"
                  >
                    <item.icon className="w-4 h-4 text-slate-400" />
                    <span>{item.label}</span>
                  </Link>
                ))}
              </nav>
            </div>
          </div>
        )}

        {/* Page Inner Container */}
        <main className="mx-auto w-full max-w-7xl flex-1 p-4 sm:p-8">
          <h1 className="sr-only">{title}</h1>
          {logoutError && (
            <div role="alert" className="mb-5 rounded-xl border border-rose-900/70 bg-rose-950/40 px-4 py-3 text-xs text-rose-200">
              {logoutError}
            </div>
          )}
          {children}
        </main>
      </div>
    </div>
  );
};
