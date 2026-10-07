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
    attendee: {
      fullName: string;
      email: string;
      phone: string;
      organization?: string;
      jobTitle?: string;
    };
    tierId: string;
    source: 'ONLINE' | 'ON_SPOT';
  }): Promise<{ registration: Registration; ticket: Ticket; tickets: Ticket[] }> => {
    const endpoint = params.source === 'ON_SPOT' ? '/registrations/on-spot/' : '/registrations/';
    const response = await apiRequest<RegistrationCreateResponse>(endpoint, {
      method: 'POST',
      body: jsonBody({
        event_id: params.eventId,
        ticket_tier_id: params.tierId,
        buyer: {
          name: params.attendee.fullName,
          email: params.attendee.email,
          phone: params.attendee.phone,
          organization: params.attendee.organization || '',
          job_title: params.attendee.jobTitle || '',
        },
      }),
    });
    const tickets = response.tickets.map(mapTicket);
    return {
      registration: mapRegistration(response.registration),
      ticket: tickets[0],
      tickets,
    };
  },
};
