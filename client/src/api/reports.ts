import { DashboardSummary, EventReport } from '../types';
import { apiBlob, apiRequest } from './http';

export const reportsApi = {
  getDashboardSummary: (eventId: string) =>
    apiRequest<DashboardSummary>(`/reports/dashboard/?event_id=${encodeURIComponent(eventId)}`),

  getEventReport: (eventId: string) =>
    apiRequest<EventReport>(`/reports/?event_id=${encodeURIComponent(eventId)}`),

  downloadManifest: (eventId: string) =>
    apiBlob(`/reports/manifest.csv/?event_id=${encodeURIComponent(eventId)}`),
};
