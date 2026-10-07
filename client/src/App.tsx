/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { useAuth } from './context/AuthContext';
import { StaffUser } from './types';

// Public Pages
import { LandingPage } from './pages/public/LandingPage';
import { EventDetailPage } from './pages/public/EventDetailPage';
import { RegistrationPage } from './pages/public/RegistrationPage';
import { RegistrationSuccessPage } from './pages/public/RegistrationSuccessPage';
import { TicketViewPage } from './pages/public/TicketViewPage';
import { TicketComingSoonPage } from './pages/public/TicketComingSoonPage';
import { AboutPage } from './pages/public/AboutPage';

// Staff Pages
import { StaffLoginPage } from './pages/staff/StaffLoginPage';
import { StaffDashboardPage } from './pages/staff/StaffDashboardPage';
import { OnSpotRegistrationPage } from './pages/staff/OnSpotRegistrationPage';
import { StaffScannerPage } from './pages/staff/StaffScannerPage';

// Admin Pages
import { AdminDashboardPage } from './pages/admin/AdminDashboardPage';
import { AdminRegistrationsPage } from './pages/admin/AdminRegistrationsPage';
import { AdminTicketsPage } from './pages/admin/AdminTicketsPage';
import { AdminScansPage } from './pages/admin/AdminScansPage';
import { AdminReportsPage } from './pages/admin/AdminReportsPage';

const ProtectedRoute: React.FC<{
  allowedRoles: StaffUser['role'][];
  children: React.ReactNode;
}> = ({ allowedRoles, children }) => {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <div className="min-h-screen bg-slate-950" aria-label="Loading authenticated session" />;
  }
  if (!user) {
    return <Navigate to="/staff/login" replace state={{ from: location }} />;
  }
  if (!allowedRoles.includes(user.role)) {
    return <Navigate to={user.role === 'ADMIN' ? '/admin' : '/staff/dashboard'} replace />;
  }
  return <>{children}</>;
};

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public Routes */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/events" element={<Navigate to="/events/dhandiya-night-2026" replace />} />
          <Route path="/events/dhandiya-night-2026" element={<EventDetailPage />} />
          <Route path="/events/:eventId" element={<Navigate to="/events/dhandiya-night-2026" replace />} />
          <Route path="/register/dhandiya-night-2026" element={<RegistrationPage />} />
          <Route path="/register/:eventId" element={<Navigate to="/register/dhandiya-night-2026" replace />} />
          <Route path="/registration/success" element={<RegistrationSuccessPage />} />
          <Route path="/ticket/:ticketId" element={<TicketViewPage />} />
          <Route path="/ticket-coming-soon" element={<TicketComingSoonPage />} />

          {/* Staff Routes */}
          <Route path="/staff/login" element={<StaffLoginPage />} />
          <Route path="/staff/dashboard" element={<ProtectedRoute allowedRoles={['ADMIN', 'REGISTRATION', 'SCANNER']}><StaffDashboardPage /></ProtectedRoute>} />
          <Route path="/staff/register" element={<ProtectedRoute allowedRoles={['ADMIN', 'REGISTRATION']}><OnSpotRegistrationPage /></ProtectedRoute>} />
          <Route path="/staff/scanner" element={<ProtectedRoute allowedRoles={['ADMIN', 'SCANNER']}><StaffScannerPage /></ProtectedRoute>} />
          <Route path="/staff/scanner/result" element={<ProtectedRoute allowedRoles={['ADMIN', 'SCANNER']}><StaffScannerPage /></ProtectedRoute>} />

          {/* Admin Routes */}
          <Route path="/admin" element={<ProtectedRoute allowedRoles={['ADMIN']}><AdminDashboardPage /></ProtectedRoute>} />
          <Route path="/admin/events" element={<ProtectedRoute allowedRoles={['ADMIN']}><Navigate to="/admin" replace /></ProtectedRoute>} />
          <Route path="/admin/registrations" element={<ProtectedRoute allowedRoles={['ADMIN']}><AdminRegistrationsPage /></ProtectedRoute>} />
          <Route path="/admin/tickets" element={<ProtectedRoute allowedRoles={['ADMIN']}><AdminTicketsPage /></ProtectedRoute>} />
          <Route path="/admin/scans" element={<ProtectedRoute allowedRoles={['ADMIN']}><AdminScansPage /></ProtectedRoute>} />
          <Route path="/admin/reports" element={<ProtectedRoute allowedRoles={['ADMIN']}><AdminReportsPage /></ProtectedRoute>} />
          <Route path="/admin/users" element={<ProtectedRoute allowedRoles={['ADMIN']}><Navigate to="/admin" replace /></ProtectedRoute>} />

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
