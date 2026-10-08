import { ApiPage, Registration, Ticket } from '../types';
import { ApiError, apiRequest, jsonBody } from './http';
import { ApiRegistration, ApiTicket, mapRegistration, mapTicket } from './serializers';

interface RegistrationCreateResponse {
  registration: ApiRegistration;
  ticket: ApiTicket;
  tickets: ApiTicket[];
}

export interface RegistrationFilters {
  page?: number;
  eventId?: string;
  source?: 'ONLINE' | 'ON_SPOT';
  search?: string;
}

export interface RegistrationCreateParams {
  eventId: string;
  attendee: {
    fullName: string;
    email: string;
    phone: string;
    organization?: string;
    jobTitle?: string;
  };
  attendeeNames?: string[];
  tierId: string;
  source: 'ONLINE' | 'ON_SPOT';
}

export const registrationRequest = (params: RegistrationCreateParams) => {
  const buyer = {
    name: params.attendee.fullName.trim(),
    email: params.attendee.email.trim().toLowerCase(),
    phone: params.attendee.phone,
    organization: params.attendee.organization?.trim() || '',
    job_title: params.attendee.jobTitle?.trim() || '',
  };
  return {
    event_id: params.eventId,
    ticket_tier_id: params.tierId,
    buyer,
    attendee_names: (params.attendeeNames || [buyer.name]).map((name) => name.trim()),
  };
};

export const registrationIdempotencyKey = async (params: RegistrationCreateParams): Promise<string> => {
  const request = registrationRequest(params);
  const fingerprint = await requestFingerprint({
    ...request,
    source: params.source,
  });
  const storageKey = `ticketing.registration-idempotency.${fingerprint}`;
  const idempotencyKey = sessionStorage.getItem(storageKey) || crypto.randomUUID();
  sessionStorage.setItem(storageKey, idempotencyKey);
  return idempotencyKey;
};

export const clearRegistrationIdempotencyKey = async (params: RegistrationCreateParams): Promise<void> => {
  const request = registrationRequest(params);
  const fingerprint = await requestFingerprint({
    ...request,
    source: params.source,
  });
  sessionStorage.removeItem(`ticketing.registration-idempotency.${fingerprint}`);
};

const requestFingerprint = async (value: unknown): Promise<string> => {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
};

const queryString = (filters: RegistrationFilters): string => {
  const query = new URLSearchParams();
  query.set('page_size', '50');
  if (filters.page) query.set('page', String(filters.page));
  if (filters.eventId) query.set('event_id', filters.eventId);
  if (filters.source) query.set('source', filters.source);
  if (filters.search?.trim()) query.set('search', filters.search.trim());
  return `?${query.toString()}`;
};

export const registrationsApi = {
  getPage: async (filters: RegistrationFilters = {}): Promise<ApiPage<Registration>> => {
    const page = await apiRequest<ApiPage<ApiRegistration>>(`/registrations/${queryString(filters)}`);
    return { ...page, results: page.results.map(mapRegistration) };
  },

  getAll: async (): Promise<Registration[]> => (await registrationsApi.getPage()).results,

  getById: async (id: string): Promise<Registration | null> => {
    try {
      const registration = await apiRequest<ApiRegistration>(`/registrations/${encodeURIComponent(id)}/`);
      return mapRegistration(registration);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  },

  create: async (params: {
    eventId: string;
    attendee: RegistrationCreateParams['attendee'];
    attendeeNames?: string[];
    tierId: string;
    source: 'ONLINE' | 'ON_SPOT';
  }): Promise<{ registration: Registration; ticket: Ticket; tickets: Ticket[] }> => {
    const endpoint = params.source === 'ON_SPOT' ? '/registrations/on-spot/' : '/registrations/';
    const request = registrationRequest(params);
    const idempotencyKey = await registrationIdempotencyKey(params);

    const response = await apiRequest<RegistrationCreateResponse>(endpoint, {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
      body: jsonBody(request),
    });
    await clearRegistrationIdempotencyKey(params);
    const tickets = response.tickets.map(mapTicket);
    return {
      registration: mapRegistration(response.registration),
      ticket: tickets[0],
      tickets,
    };
  },
};
