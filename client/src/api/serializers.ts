import {
  EventItem,
  Registration,
  RegistrationSource,
  ScanRecord,
  ScanResultType,
  StaffUser,
  Ticket,
  TicketStatus,
} from '../types';

export interface ApiTicket {
  id: string;
  registration_id: string;
  event_id: string;
  event_name: string;
  buyer_name: string;
  attendee_email?: string | null;
  attendee_phone?: string | null;
  tier_name: string;
  source: RegistrationSource;
  status: TicketStatus;
  venue: string;
  event_date: string;
  event_time: string;
  issued_at: string;
  used_at: string | null;
  cancelled_at?: string | null;
  gate: string | null;
  qr_token: string;
}

export interface ApiRegistration {
  id: string;
  event_id: string;
  event_name: string;
  buyer: {
    name: string;
    email: string;
    phone: string;
    organization?: string;
    job_title?: string;
  };
  ticket_tier_id: string;
  ticket_tier_name: string;
  source: RegistrationSource;
  created_at: string;
  tickets?: ApiTicket[];
  ticket_ids?: string[];
}

export interface ApiScanRecord {
  id: string;
  ticket_id: string | null;
  event_id: string;
  event_name: string;
  attendee_name: string;
  result: ScanResultType;
  gate: string;
  staff_name: string;
  scanned_at: string;
}

export interface ApiEvent extends Omit<EventItem, 'category' | 'accentColor'> {
  category: EventItem['category'];
  accentColor: string;
}

export interface ApiUser {
  id: string;
  email: string;
  name: string;
  role: 'ADMIN' | 'REGISTRATION_STAFF' | 'SCANNER_STAFF';
  assigned_gate: string | null;
}

export const mapEvent = (event: ApiEvent): EventItem => event;

export const mapTicket = (ticket: ApiTicket): Ticket => ({
  id: ticket.id,
  registrationId: ticket.registration_id,
  eventId: ticket.event_id,
  eventName: ticket.event_name,
  attendeeName: ticket.buyer_name,
  attendeeEmail: ticket.attendee_email ?? undefined,
  attendeePhone: ticket.attendee_phone ?? undefined,
  tierName: ticket.tier_name,
  source: ticket.source,
  status: ticket.status,
  venue: ticket.venue,
  eventDate: ticket.event_date,
  eventTime: ticket.event_time,
  issuedAt: ticket.issued_at,
  usedAt: ticket.used_at ?? undefined,
  gate: ticket.gate ?? undefined,
  qrToken: ticket.qr_token,
});

export const mapRegistration = (registration: ApiRegistration): Registration => {
  const ticketIds = registration.tickets?.map((ticket) => ticket.id) ?? registration.ticket_ids ?? [];
  return {
    id: registration.id,
    eventId: registration.event_id,
    eventName: registration.event_name,
    attendee: {
      fullName: registration.buyer.name,
      email: registration.buyer.email,
      phone: registration.buyer.phone,
      organization: registration.buyer.organization || undefined,
      jobTitle: registration.buyer.job_title || undefined,
    },
    tierId: registration.ticket_tier_id,
    tierName: registration.ticket_tier_name,
    source: registration.source,
    ticketId: ticketIds[0] ?? '',
    ticketIds,
    status: 'REGISTERED',
    createdAt: registration.created_at,
  };
};

export const mapScan = (scan: ApiScanRecord): ScanRecord => ({
  id: scan.id,
  ticketId: scan.ticket_id,
  eventId: scan.event_id,
  eventName: scan.event_name,
  attendeeName: scan.attendee_name,
  result: scan.result,
  gate: scan.gate,
  staffName: scan.staff_name,
  scannedAt: scan.scanned_at,
});

export const mapUser = (user: ApiUser): StaffUser => ({
  id: user.id,
  name: user.name,
  email: user.email,
  role: user.role === 'REGISTRATION_STAFF' ? 'REGISTRATION' : user.role === 'SCANNER_STAFF' ? 'SCANNER' : 'ADMIN',
  assignedGate: user.assigned_gate ?? undefined,
});
