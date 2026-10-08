import { EventItem } from '../types';
import { ApiError, apiRequest, jsonBody } from './http';
import { ApiEvent, mapEvent } from './serializers';

export const FEATURED_EVENT_SLUG = 'dhandiya-night-2026';

export interface AdminEventContext {
  id: string;
  slug: string;
  capacity: number;
  status: EventItem['status'];
  formattedDate: string;
  tiers: Pick<EventItem['tiers'][number], 'id' | 'name' | 'price'>[];
}

export const eventsApi = {
  getAll: async (): Promise<EventItem[]> => {
    const events = await apiRequest<ApiEvent[]>('/events/');
    return events.map(mapEvent);
  },

  getById: async (identifier: string): Promise<EventItem | null> => {
    try {
      const event = await apiRequest<ApiEvent>(`/events/${encodeURIComponent(identifier)}/`);
      return mapEvent(event);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  },

  getAdminContext: (slug: string) =>
    apiRequest<AdminEventContext>(`/events/admin-context/${encodeURIComponent(slug)}/`),

  update: async (event: EventItem): Promise<EventItem> => {
    const updated = await apiRequest<ApiEvent>(
      `/events/${encodeURIComponent(event.id)}/`,
      {
        method: 'PATCH',
        body: jsonBody({
          slug: event.slug,
          name: event.name,
          tagline: event.tagline,
          description: event.description,
          category: event.category,
          venue: event.venue,
          city: event.city,
          address: event.address,
          capacity: event.capacity,
          accent_color: event.accentColor,
        }),
      },
    );
    return mapEvent(updated);
  },
};
