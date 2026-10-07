import { FEATURED_EVENT_ID, INITIAL_EVENTS } from '../mock/events';
import { INITIAL_REGISTRATIONS } from '../mock/registrations';
import { INITIAL_TICKETS } from '../mock/tickets';
import { INITIAL_SCANS } from '../mock/scans';
import { EventItem, Registration, Ticket, ScanRecord, StaffUser, ScanResultType } from '../types';

const STORAGE_KEY_EVENTS = 'aurapass_events';
const STORAGE_KEY_REGISTRATIONS = 'aurapass_registrations';
const STORAGE_KEY_TICKETS = 'aurapass_tickets';
const STORAGE_KEY_SCANS = 'aurapass_scans';
const STORAGE_KEY_STAFF = 'aurapass_current_staff';
const STORAGE_KEY_FESTIVAL_THEME = 'aurapass_festival_theme';
const FESTIVAL_THEME_VERSION = 'dhandiya-night-v4';

const createOpaqueTicketToken = (): string => {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return `ap1_${Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')}`;
};

const createMockId = (prefix: string): string => {
  const bytes = crypto.getRandomValues(new Uint8Array(8));
  return `${prefix}${Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')}`;
};

class DataStore {
  private events: EventItem[] = [];
  private registrations: Registration[] = [];
  private tickets: Ticket[] = [];
  private scans: ScanRecord[] = [];
  private currentStaff: StaffUser | null = null;
  private listeners: Set<() => void> = new Set();

  constructor() {
    this.loadFromStorage();
  }

  private loadFromStorage() {
    try {
      const applyFestivalTheme = localStorage.getItem(STORAGE_KEY_FESTIVAL_THEME) !== FESTIVAL_THEME_VERSION;
      const storedEvents = localStorage.getItem(STORAGE_KEY_EVENTS);
      this.events = storedEvents ? JSON.parse(storedEvents) : [...INITIAL_EVENTS];
      const featuredEvent = INITIAL_EVENTS[0];
      if (applyFestivalTheme && featuredEvent) {
        this.events = this.events.map((event) => {
          if (event.id !== FEATURED_EVENT_ID) return event;
          return {
            ...featuredEvent,
            capacity: event.capacity,
            registeredCount: event.registeredCount,
            checkedInCount: event.checkedInCount,
            tiers: featuredEvent.tiers.map((tier) => {
              const storedTier = event.tiers?.find((item) => item.id === tier.id);
              return {
                ...tier,
                available: storedTier?.available ?? tier.available,
              };
            }),
          };
        });
      }

      const storedRegs = localStorage.getItem(STORAGE_KEY_REGISTRATIONS);
      this.registrations = storedRegs
        ? (JSON.parse(storedRegs) as Registration[]).map((registration) => ({
            ...registration,
            ...(applyFestivalTheme && registration.eventId === featuredEvent?.id && registration.tierId === 'tier-vip'
              ? { tierId: 'tier-single', tierName: 'Single Ticket' }
              : {}),
            source: (registration.source as string) === 'ON-SPOT' ? 'ON_SPOT' : registration.source,
            ...(applyFestivalTheme && registration.eventId === featuredEvent?.id
              ? {
                  eventName: featuredEvent.name,
                  tierName: featuredEvent.tiers.find((tier) => tier.id === registration.tierId)?.name ?? registration.tierName,
                }
              : {}),
          }))
        : [...INITIAL_REGISTRATIONS];

      const storedTickets = localStorage.getItem(STORAGE_KEY_TICKETS);
      this.tickets = storedTickets
        ? (JSON.parse(storedTickets) as Array<Ticket & { qrPayload?: string }>).map((ticket) => ({
            ...ticket,
            source: (ticket.source as string) === 'ON-SPOT' ? 'ON_SPOT' : ticket.source,
            qrToken: ticket.qrToken || createOpaqueTicketToken(),
            ...(applyFestivalTheme && ticket.eventId === featuredEvent?.id
              ? {
                  eventName: featuredEvent.name,
                  venue: featuredEvent.venue,
                  eventDate: featuredEvent.formattedDate,
                  eventTime: featuredEvent.time,
                  tierName:
                    featuredEvent.tiers.find(
                      (tier) =>
                        tier.name === ticket.tierName ||
                        this.registrations.some(
                          (registration) =>
                            (registration.ticketIds?.includes(ticket.id) || registration.ticketId === ticket.id) &&
                            registration.tierId === tier.id
                        )
                    )?.name ?? ticket.tierName,
                }
              : {}),
          }))
        : [...INITIAL_TICKETS];

      const storedScans = localStorage.getItem(STORAGE_KEY_SCANS);
      this.scans = storedScans
        ? (JSON.parse(storedScans) as ScanRecord[]).map((scan) => ({
            ...scan,
            result:
              (scan.result as string) === 'SUCCESS'
                ? 'ENTRY_GRANTED'
                : (scan.result as string) === 'INVALID'
                  ? 'INVALID_TICKET'
                  : scan.result,
            ...(applyFestivalTheme && scan.eventId === featuredEvent?.id
              ? {
                  eventName: featuredEvent.name,
                  notes: scan.notes?.replaceAll('TECHNOVA 2026', featuredEvent.name),
                }
              : {}),
          }))
        : [...INITIAL_SCANS];

      const storedStaff = localStorage.getItem(STORAGE_KEY_STAFF);
      this.currentStaff = storedStaff ? JSON.parse(storedStaff) : null;
      this.saveToStorage();
      localStorage.setItem(STORAGE_KEY_FESTIVAL_THEME, FESTIVAL_THEME_VERSION);
    } catch (error) {
      console.warn('Failed to load local demo data; initial sample records are being used.', error);
      this.events = [...INITIAL_EVENTS];
      this.registrations = [...INITIAL_REGISTRATIONS];
      this.tickets = [...INITIAL_TICKETS];
      this.scans = [...INITIAL_SCANS];
      this.currentStaff = null;
    }
  }

  private saveToStorage() {
    try {
      localStorage.setItem(STORAGE_KEY_EVENTS, JSON.stringify(this.events));
      localStorage.setItem(STORAGE_KEY_REGISTRATIONS, JSON.stringify(this.registrations));
      localStorage.setItem(STORAGE_KEY_TICKETS, JSON.stringify(this.tickets));
      localStorage.setItem(STORAGE_KEY_SCANS, JSON.stringify(this.scans));
      if (this.currentStaff) {
        localStorage.setItem(STORAGE_KEY_STAFF, JSON.stringify(this.currentStaff));
      } else {
        localStorage.removeItem(STORAGE_KEY_STAFF);
      }
    } catch (e) {
      console.warn('LocalStorage save failed:', e);
    }
    this.notify();
  }

  public subscribe(listener: () => void) {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private notify() {
    this.listeners.forEach((cb) => cb());
  }

  // --- EVENTS ---
  public getEvents(): EventItem[] {
    return this.events.filter((event) => event.id === FEATURED_EVENT_ID);
  }

  public getEventById(id: string): EventItem | undefined {
    return this.events.find(
      (event) => event.id === FEATURED_EVENT_ID && (event.id === id || event.slug === id)
    );
  }

  public updateEvent(updated: EventItem): void {
    if (updated.id !== FEATURED_EVENT_ID) {
      throw new Error('Only Dhandiya Night is configured in this application.');
    }
    const idx = this.events.findIndex((e) => e.id === updated.id);
    if (idx !== -1) {
      this.events[idx] = updated;
      this.saveToStorage();
    }
  }

  // --- REGISTRATIONS & TICKETS ---
  public getRegistrations(): Registration[] {
    return [...this.registrations];
  }

  public getRegistrationById(id: string): Registration | undefined {
    return this.registrations.find((r) => r.id === id);
  }

  public getTickets(): Ticket[] {
    return [...this.tickets];
  }

  public getTicketById(id: string): Ticket | undefined {
    return this.tickets.find((t) => t.id === id || t.qrToken === id);
  }

  public createRegistration(params: {
    eventId: string;
    attendee: {
      fullName: string;
      email: string;
      phone: string;
      organization?: string;
      jobTitle?: string;
    };
    tierId: string;
    source: 'ONLINE' | 'ON_SPOT';
  }): { registration: Registration; ticket: Ticket; tickets: Ticket[] } {
    const event = this.getEventById(params.eventId);
    if (!event) throw new Error('Event not found');

    if (event.status !== 'open') {
      throw new Error('Registration is not open for this event.');
    }
    if (event.registeredCount >= event.capacity) {
      throw new Error('This event has reached its registration capacity.');
    }

    const tier = event.tiers.find((t) => t.id === params.tierId);
    if (!tier) throw new Error('The selected ticket tier is not available for this event.');
    if (tier.available < 1) {
      throw new Error('This ticket tier is sold out. Choose another available tier.');
    }
    const admissionCount = tier.admissionCount ?? 1;
    if (event.registeredCount + admissionCount > event.capacity) {
      throw new Error('There are not enough admissions remaining for this ticket option.');
    }

    const regId = createMockId('REG-');
    const tickets: Ticket[] = Array.from({ length: admissionCount }, () => ({
        id: createMockId('TKT-'),
        registrationId: regId,
        eventId: event.id,
        eventName: event.name,
        attendeeName: params.attendee.fullName,
        attendeeEmail: params.attendee.email,
        attendeePhone: params.attendee.phone,
        tierName: tier.name,
        source: params.source,
        status: 'ISSUED',
        venue: event.venue,
        eventDate: event.formattedDate,
        eventTime: event.time,
        issuedAt: new Date().toISOString(),
        qrToken: createOpaqueTicketToken(),
      }));
    const ticket = tickets[0];

    const newRegistration: Registration = {
      id: regId,
      eventId: event.id,
      eventName: event.name,
      attendee: params.attendee,
      tierId: tier.id,
      tierName: tier.name,
      source: params.source,
      ticketId: ticket.id,
      ticketIds: tickets.map((issuedTicket) => issuedTicket.id),
      status: 'REGISTERED',
      createdAt: new Date().toISOString(),
    };

    this.registrations.unshift(newRegistration);
    this.tickets.unshift(...tickets);

    // Update event registered counter
    tier.available -= 1;
    event.registeredCount += admissionCount;
    if (event.registeredCount >= event.capacity || event.tiers.every((eventTier) => eventTier.available < 1)) {
      event.status = 'sold_out';
    }
    this.updateEvent(event);

    this.saveToStorage();
    return { registration: newRegistration, ticket, tickets };
  }

  public cancelTicket(ticketId: string): boolean {
    const tkt = this.tickets.find((t) => t.id === ticketId);
    if (!tkt || tkt.status !== 'ISSUED') return false;

    const reg = this.registrations.find((r) => r.id === tkt.registrationId);
    if (reg) {
      const registrationTickets = this.tickets.filter(
        (ticket) => ticket.registrationId === reg.id && ticket.status === 'ISSUED'
      );
      registrationTickets.forEach((ticket) => {
        ticket.status = 'CANCELLED';
      });
      reg.status = 'REGISTERED';
      const event = this.getEventById(reg.eventId);
      const tier = event?.tiers.find((item) => item.id === reg.tierId);
      if (event) {
        event.registeredCount = Math.max(0, event.registeredCount - registrationTickets.length);
        if (tier && registrationTickets.length === (reg.ticketIds?.length ?? 1)) tier.available += 1;
        if (event.status === 'sold_out') event.status = 'open';
      }
    } else {
      tkt.status = 'CANCELLED';
    }

    this.saveToStorage();
    return true;
  }

  // --- SCANS ---
  public getScans(): ScanRecord[] {
    return [...this.scans];
  }

  public verifyTicket(scannedCode: string, currentEventId: string, gate = 'Gate 2'): {
    result: ScanResultType;
    ticket?: Ticket;
    scanRecord: ScanRecord;
    message: string;
  } {
    const cleanCode = scannedCode.trim();
    // Match by direct ID or payload containing ID
    const foundTicket = this.tickets.find((ticket) => ticket.qrToken === cleanCode);

    // If simulated code begins with mock error flags:
    if (cleanCode.toLowerCase().includes('network-err')) {
      const record: ScanRecord = {
        id: createMockId('SCN-'),
        ticketId: 'NETWORK_ERROR',
        eventId: currentEventId,
        eventName: this.getEventById(currentEventId)?.name || 'Event',
        attendeeName: 'Unknown',
        result: 'NETWORK_ERROR',
        gate,
        staffName: this.currentStaff?.name || 'Gate Staff',
        scannedAt: new Date().toISOString(),
        notes: 'Demo network-error scenario.',
      };
      this.scans.unshift(record);
      this.saveToStorage();
      return {
        result: 'NETWORK_ERROR',
        scanRecord: record,
        message: 'The local demo simulated a network error. Do not allow entry.',
      };
    }

    if (cleanCode === 'event-closed-demo') {
      const event = this.getEventById(currentEventId);
      const record: ScanRecord = {
        id: createMockId('SCN-'),
        ticketId: 'EVENT_CLOSED',
        eventId: currentEventId,
        eventName: event?.name || 'Event',
        attendeeName: 'Demo scenario',
        result: 'EVENT_CLOSED',
        gate,
        staffName: this.currentStaff?.name || 'Gate Staff',
        scannedAt: new Date().toISOString(),
        notes: 'Demo event-closed scenario.',
      };
      this.scans.unshift(record);
      this.saveToStorage();
      return {
        result: 'EVENT_CLOSED',
        scanRecord: record,
        message: 'The local demo simulated a closed event. Do not allow entry.',
      };
    }

    if (!foundTicket) {
      const record: ScanRecord = {
        id: createMockId('SCN-'),
        ticketId: 'UNKNOWN',
        eventId: currentEventId,
        eventName: this.getEventById(currentEventId)?.name || 'Event',
        attendeeName: 'Unknown',
        result: 'INVALID_TICKET',
        gate,
        staffName: this.currentStaff?.name || 'Gate Staff',
        scannedAt: new Date().toISOString(),
        notes: 'Token does not match an issued local demo ticket.',
      };
      this.scans.unshift(record);
      this.saveToStorage();
      return {
        result: 'INVALID_TICKET',
        scanRecord: record,
        message: 'No matching local demo ticket was found. Do not allow entry.',
      };
    }

    // Wrong event check
    if (foundTicket.eventId !== currentEventId) {
      const record: ScanRecord = {
        id: createMockId('SCN-'),
        ticketId: foundTicket.id,
        eventId: currentEventId,
        eventName: this.getEventById(currentEventId)?.name || 'Current Event',
        attendeeName: foundTicket.attendeeName,
        result: 'WRONG_EVENT',
        gate,
        staffName: this.currentStaff?.name || 'Gate Staff',
        scannedAt: new Date().toISOString(),
        notes: `Ticket issued for ${foundTicket.eventName}, attempted scan at ${this.getEventById(currentEventId)?.name}.`,
      };
      this.scans.unshift(record);
      this.saveToStorage();
      return {
        result: 'WRONG_EVENT',
        ticket: foundTicket,
        scanRecord: record,
        message: `This pass is issued for ${foundTicket.eventName}, not the active entry gate.`,
      };
    }

    // Cancelled check
    if (foundTicket.status === 'CANCELLED') {
      const record: ScanRecord = {
        id: createMockId('SCN-'),
        ticketId: foundTicket.id,
        eventId: currentEventId,
        eventName: foundTicket.eventName,
        attendeeName: foundTicket.attendeeName,
        result: 'CANCELLED',
        gate,
        staffName: this.currentStaff?.name || 'Gate Staff',
        scannedAt: new Date().toISOString(),
        notes: 'Ticket was formally cancelled prior to entry.',
      };
      this.scans.unshift(record);
      this.saveToStorage();
      return {
        result: 'CANCELLED',
        ticket: foundTicket,
        scanRecord: record,
        message: 'This registration has been marked CANCELLED.',
      };
    }

    // Already used check
    if (foundTicket.status === 'USED') {
      const record: ScanRecord = {
        id: createMockId('SCN-'),
        ticketId: foundTicket.id,
        eventId: currentEventId,
        eventName: foundTicket.eventName,
        attendeeName: foundTicket.attendeeName,
        result: 'ALREADY_USED',
        gate,
        staffName: this.currentStaff?.name || 'Gate Staff',
        scannedAt: new Date().toISOString(),
        notes: `Duplicate entry attempt. Previously checked in at ${foundTicket.gate || 'Gate'} at ${foundTicket.usedAt ? new Date(foundTicket.usedAt).toLocaleTimeString() : 'Earlier'}.`,
      };
      this.scans.unshift(record);
      this.saveToStorage();
      return {
        result: 'ALREADY_USED',
        ticket: foundTicket,
        scanRecord: record,
        message: `Already checked in at ${foundTicket.gate || 'Gate'} (${foundTicket.usedAt ? new Date(foundTicket.usedAt).toLocaleTimeString() : 'Earlier'}).`,
      };
    }

    // Valid check-in: Grant entry
    const event = this.getEventById(currentEventId);
    if (event?.status === 'completed') {
      const record: ScanRecord = {
        id: createMockId('SCN-'),
        ticketId: foundTicket.id,
        eventId: currentEventId,
        eventName: event.name,
        attendeeName: foundTicket.attendeeName,
        result: 'EVENT_CLOSED',
        gate,
        staffName: this.currentStaff?.name || 'Gate Staff',
        scannedAt: new Date().toISOString(),
      };
      this.scans.unshift(record);
      this.saveToStorage();
      return {
        result: 'EVENT_CLOSED',
        ticket: foundTicket,
        scanRecord: record,
        message: 'Entry is closed for this event.',
      };
    }

    const nowIso = new Date().toISOString();
    foundTicket.status = 'USED';
    foundTicket.usedAt = nowIso;
    foundTicket.gate = gate;

    if (event) {
      event.checkedInCount += 1;
      this.updateEvent(event);
    }

    const record: ScanRecord = {
      id: createMockId('SCN-'),
      ticketId: foundTicket.id,
      eventId: currentEventId,
      eventName: foundTicket.eventName,
      attendeeName: foundTicket.attendeeName,
      result: 'ENTRY_GRANTED',
      gate,
      staffName: this.currentStaff?.name || 'Gate Staff',
      scannedAt: nowIso,
      notes: 'Entry granted. Primary pass consumed.',
    };

    this.scans.unshift(record);
    this.saveToStorage();

    return {
      result: 'ENTRY_GRANTED',
      ticket: foundTicket,
      scanRecord: record,
      message: 'Entry granted in local demo mode; no server-side validation was performed.',
    };
  }

  // --- STAFF AUTH (MOCK) ---
  public getCurrentStaff(): StaffUser | null {
    return this.currentStaff;
  }

  public setStaff(staff: StaffUser | null) {
    this.currentStaff = staff;
    this.saveToStorage();
  }

  public resetAllData() {
    this.events = [...INITIAL_EVENTS];
    this.registrations = [...INITIAL_REGISTRATIONS];
    this.tickets = [...INITIAL_TICKETS];
    this.scans = [...INITIAL_SCANS];
    this.currentStaff = null;
    this.saveToStorage();
  }
}

export const store = new DataStore();
