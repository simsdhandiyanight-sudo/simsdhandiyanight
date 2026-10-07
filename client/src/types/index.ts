export type EventCategory = 'technology' | 'design' | 'business' | 'music' | 'startup';

export type EventStatus = 'open' | 'upcoming' | 'sold_out' | 'completed' | 'cancelled';

export type RegistrationSource = 'ONLINE' | 'ON_SPOT';

export type TicketStatus = 'ISSUED' | 'USED' | 'CANCELLED';

export type ScanResultType =
  | 'ENTRY_GRANTED'
  | 'ALREADY_USED'
  | 'INVALID_TICKET'
  | 'CANCELLED'
  | 'WRONG_EVENT'
  | 'EVENT_CLOSED'
  | 'NETWORK_ERROR';

export interface EventTier {
  id: string;
  name: string;
  price: number;
  admissionCount?: number;
  description: string;
  perks: string[];
  available: number;
}

export interface EventItem {
  id: string;
  slug: string;
  name: string;
  tagline: string;
  description: string;
  category: EventCategory;
  date: string; // e.g. "2026-10-18"
  formattedDate: string; // e.g. "18 Oct 2026"
  time: string; // e.g. "10:00 AM – 5:00 PM"
  venue: string;
  city: string;
  address: string;
  status: EventStatus;
  capacity: number;
  registeredCount: number;
  checkedInCount: number;
  tiers: EventTier[];
  highlights: string[];
  schedule: { time: string; title: string; speaker?: string }[];
  faqs: { question: string; answer: string }[];
  accentColor: string;
}

export interface Attendee {
  fullName: string;
  email: string;
  phone: string;
  organization?: string;
  jobTitle?: string;
}

export interface Registration {
  id: string; // e.g. "REG-2026-001284"
  eventId: string;
  eventName: string;
  attendee: Attendee;
  tierId: string;
  tierName: string;
  source: RegistrationSource;
  ticketId: string;
  ticketIds?: string[];
  status: 'REGISTERED';
  createdAt: string; // ISO string
}

export interface Ticket {
  id: string; // e.g. "TKT-849201"
  registrationId: string;
  eventId: string;
  eventName: string;
  attendeeName: string;
  attendeeEmail?: string;
  attendeePhone?: string;
  tierName: string;
  source: RegistrationSource;
  status: TicketStatus;
  venue: string;
  eventDate: string;
  eventTime: string;
  issuedAt: string;
  usedAt?: string;
  gate?: string;
  qrToken: string;
}

export interface ScanRecord {
  id: string;
  ticketId: string | null;
  eventId: string;
  eventName: string;
  attendeeName: string;
  result: ScanResultType;
  gate: string;
  staffName: string;
  scannedAt: string; // ISO string
  notes?: string;
}

export interface StaffUser {
  id: string;
  name: string;
  email: string;
  role: 'SCANNER' | 'REGISTRATION' | 'ADMIN';
  assignedGate?: string;
}

export interface ApiPage<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface DashboardSummary {
  event_id: string;
  registrations: number;
  online_registrations: number;
  on_spot_registrations: number;
  active_tickets: number;
  used_tickets: number;
  cancelled_tickets: number;
  scan_attempts: number;
  entry_granted: number;
  scan_results: { result: ScanResultType; count: number }[];
}

export interface EventReport {
  event_id: string;
  registration_sources: { source: RegistrationSource; count: number }[];
  ticket_statuses: { status: TicketStatus; count: number }[];
  scan_results: { result: ScanResultType; count: number }[];
  tiers: { tier_id: string; tier_name: string; count: number }[];
  gates: { gate: string; attempts: number; granted: number }[];
}
