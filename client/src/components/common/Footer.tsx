import React from 'react';
import { Link } from 'react-router-dom';

export const Footer: React.FC = () => {
  return (
    <footer className="festival-footer border-t border-slate-900 bg-slate-950 text-slate-400 text-sm mt-auto">
      <div className="festival-footer__inner max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-10">
          {/* Brand info */}
          <div className="festival-footer__brand md:col-span-2">
            <img
              className="festival-footer__brand-logo"
              src="/sims-logo.png"
              srcSet="/sims-logo.webp"
              alt="Soundarya Institute of Management and Science logo"
            />
            <div className="festival-footer__brand-copy">
              <p className="festival-footer__college-name">Soundarya Institute of Management and Science</p>
              <p className="festival-footer__event-name">Dhandiya Night 2026</p>
              <p className="festival-footer__tagline">Dance · Dandiya · Dhamaka</p>
              <p className="text-slate-400 max-w-sm text-xs leading-relaxed">
                A celebration of tradition, dance, and community at Soundarya College Campus.
              </p>
            </div>
          </div>

          {/* Public links */}
          <div className="space-y-3">
            <h4 className="text-xs font-semibold text-slate-200 tracking-wider uppercase">The Celebration</h4>
            <ul className="space-y-2 text-xs">
              <li>
                <Link to="/" className="hover:text-white transition-colors">
                  Home
                </Link>
              </li>
              <li>
                <Link to="/events/dhandiya-night-2026" className="hover:text-white transition-colors">
                  Event Details
                </Link>
              </li>
              <li>
                <Link to="/about" className="hover:text-white transition-colors">
                  About SIMS &amp; Daksha
                </Link>
              </li>
              <li>
                <Link to="/register" className="hover:text-white transition-colors">
                  Register Now
                </Link>
              </li>
            </ul>
          </div>

        </div>

        {/* Bottom row */}
        <div className="festival-footer__bottom pt-6 border-t border-slate-900 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-400">
          <div>
            © 2026 Soundarya Institute · Dhandiya Night
          </div>
        </div>
      </div>
    </footer>
  );
};
