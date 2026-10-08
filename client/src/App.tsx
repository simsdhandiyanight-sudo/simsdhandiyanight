/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { useAuth } from './context/AuthContext';
import { StaffUser } from './types';

const LandingPage = lazy(() => import('./pages/public/LandingPage').then((module) => ({ default: module.LandingPage })));
const EventDetailPage = lazy(() => import('./pages/public/EventDetailPage').then((module) => ({ default: module.EventDetailPage })));
const RegistrationPage = lazy(() => import('./pages/public/RegistrationPage').then((module) => ({ default: module.RegistrationPage })));
const RegistrationSuccessPage = lazy(() => import('./pages/public/RegistrationSuccessPage').then((module) => ({ default: module.RegistrationSuccessPage })));
const TicketViewPage = lazy(() => import('./pages/public/TicketViewPage').then((module) => ({ default: module.TicketViewPage })));
const TicketComingSoonPage = lazy(() => import('./pages/public/TicketComingSoonPage').then((module) => ({ default: module.TicketComingSoonPage })));
const AboutPage = lazy(() => import('./pages/public/AboutPage').then((module) => ({ default: module.AboutPage })));
const StaffLoginPage = lazy(() => import('./pages/staff/StaffLoginPage').then((module) => ({ default: module.StaffLoginPage })));
const StaffDashboardPage = lazy(() => import('./pages/staff/StaffDashboardPage').then((module) => ({ default: module.StaffDashboardPage })));
const OnSpotRegistrationPage = lazy(() => import('./pages/staff/OnSpotRegistrationPage').then((module) => ({ default: module.OnSpotRegistrationPage })));
const StaffScannerPage = lazy(() => import('./pages/staff/StaffScannerPage').then((module) => ({ default: module.StaffScannerPage })));
const AdminDashboardPage = lazy(() => import('./pages/admin/AdminDashboardPage').then((module) => ({ default: module.AdminDashboardPage })));
const AdminRegistrationsPage = lazy(() => import('./pages/admin/AdminRegistrationsPage').then((module) => ({ default: module.AdminRegistrationsPage })));
const AdminTicketsPage = lazy(() => import('./pages/admin/AdminTicketsPage').then((module) => ({ default: module.AdminTicketsPage })));
const AdminScansPage = lazy(() => import('./pages/admin/AdminScansPage').then((module) => ({ default: module.AdminScansPage })));
const AdminReportsPage = lazy(() => import('./pages/admin/AdminReportsPage').then((module) => ({ default: module.AdminReportsPage })));
const AdminEmailDeliveryPage = lazy(() => import('./pages/admin/AdminEmailDeliveryPage'));
const AdminPaymentReviewPage = lazy(() => import('./pages/admin/AdminPaymentReviewPage'));

const PageLoading: React.FC = () => (
  <div className="flex min-h-screen items-center justify-center" role="status" aria-label="Loading page">
    <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
  </div>
);

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
    const roleHome = user.role === 'ADMIN'
      ? '/admin'
      : user.role === 'REGISTRATION'
        ? '/staff/register'
        : '/staff/scanner';
    return <Navigate to={roleHome} replace />;
  }
  return <>{children}</>;
};

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Suspense fallback={<PageLoading />}>
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
            <Route path="/staff/dashboard" element={<ProtectedRoute allowedRoles={['ADMIN']}><StaffDashboardPage /></ProtectedRoute>} />
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
            <Route path="/admin/email-delivery" element={<ProtectedRoute allowedRoles={['ADMIN']}><AdminEmailDeliveryPage /></ProtectedRoute>} />
            <Route path="/admin/payment-review" element={<ProtectedRoute allowedRoles={['ADMIN']}><AdminPaymentReviewPage /></ProtectedRoute>} />
            <Route path="/admin/users" element={<ProtectedRoute allowedRoles={['ADMIN']}><Navigate to="/admin" replace /></ProtectedRoute>} />

            {/* Fallback */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </AuthProvider>
  );
}
