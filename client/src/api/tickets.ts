import { ApiPage, Ticket, TicketStatus } from '../types';
import { ApiError, apiRequest, jsonBody } from './http';
import { ApiTicket, mapTicket } from './serializers';

export interface TicketFilters {
  page?: number;
  eventId?: string;
  status?: TicketStatus;
  search?: string;
}

const queryString = (filters: TicketFilters): string => {
  const query = new URLSearchParams();
  query.set('page_size', '50');
  if (filters.page) query.set('page', String(filters.page));
  if (filters.eventId) query.set('event_id', filters.eventId);
  if (filters.status) query.set('status', filters.status);
  if (filters.search?.trim()) query.set('search', filters.search.trim());
  return `?${query.toString()}`;
};

export const ticketsApi = {
  getPage: async (filters: TicketFilters = {}): Promise<ApiPage<Ticket>> => {
    const page = await apiRequest<ApiPage<ApiTicket>>(`/tickets/${queryString(filters)}`);
    return { ...page, results: page.results.map(mapTicket) };
  },

  getAll: async (): Promise<Ticket[]> => (await ticketsApi.getPage()).results,

  getById: async (id: string): Promise<Ticket | null> => {
    try {
      const ticket = await apiRequest<ApiTicket>(`/tickets/${encodeURIComponent(id)}/`);
      return mapTicket(ticket);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  },

  cancel: async (id: string): Promise<boolean> => {
    await apiRequest<ApiTicket>(`/tickets/${encodeURIComponent(id)}/cancel/`, {
      method: 'POST',
      body: jsonBody({}),
    });
    return true;
  },
};
