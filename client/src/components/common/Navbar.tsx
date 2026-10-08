import React, { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Menu, X } from 'lucide-react';

const navLinks = [
  { label: 'Home', href: '/', isActive: (pathname: string, hash: string) => pathname === '/' && !hash },
  { label: 'Event', href: '/events/dhandiya-night-2026', isActive: (pathname: string) => pathname === '/events/dhandiya-night-2026' },
  { label: 'Register', href: '/register/dhandiya-night-2026', isActive: (pathname: string) => pathname.startsWith('/register') },
  { label: 'About', href: '/about', isActive: (pathname: string) => pathname === '/about' },
];

export const Navbar: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const location = useLocation();

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20);
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    setIsOpen(false);
  }, [location.pathname, location.hash]);

  const renderLinks = (mobile = false) => navLinks.map(({ label, href, isActive }, index) => {
    const active = isActive(location.pathname, location.hash);
    return (
      <React.Fragment key={label}>
        {index === 2 && !mobile && <span className="festival-nav__ornament" aria-hidden="true">✦</span>}
        <Link
          to={href}
          className={`${mobile ? 'festival-nav__drawer-link' : 'festival-nav__link'}${active ? ' is-active' : ''}`}
          aria-current={active ? 'page' : undefined}
          onClick={mobile ? () => setIsOpen(false) : undefined}
        >
          {label}
        </Link>
      </React.Fragment>
    );
  });

  return (
    <header className={`festival-nav fixed z-40${scrolled ? ' festival-nav--scrolled' : ''}`}>
      <div className="festival-nav__inner">
        <Link to="/" className="festival-nav__sims" aria-label="Soundarya Institute of Management and Science home">
          <img src="/sims-logo.png" alt="SIMS" />
        </Link>

        <nav className="festival-nav__links" aria-label="Main navigation">
          {renderLinks()}
        </nav>

        <div className="festival-nav__right">
          <img
            className="festival-nav__daksha"
            src="/daksha-student-council-emblem.png"
            alt="Daksha Student Council"
          />
          <button
            type="button"
            onClick={() => setIsOpen(!isOpen)}
            className="festival-nav__menu"
            aria-label={isOpen ? 'Close navigation menu' : 'Open navigation menu'}
            aria-expanded={isOpen}
            aria-controls="festival-mobile-navigation"
          >
            {isOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
          </button>
        </div>
      </div>

      {isOpen && (
        <nav id="festival-mobile-navigation" className="festival-nav__drawer" aria-label="Mobile navigation">
          {renderLinks(true)}
        </nav>
      )}
    </header>
  );
};
