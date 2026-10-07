import { ApiPage, ScanRecord, ScanResultType, Ticket } from '../types';
import { ApiError, apiRequest, jsonBody } from './http';
import { ApiScanRecord, ApiTicket, mapScan, mapTicket } from './serializers';

interface ScanResponse {
  success: boolean;
  result: ScanResultType;
  ticket: ApiTicket | null;
  scan_record: ApiScanRecord;
  scanned_at: string;
}

export interface ScanFilters {
  page?: number;
  eventId?: string;
  result?: ScanResultType;
  search?: string;
}

const queryString = (filters: ScanFilters): string => {
  const query = new URLSearchParams();
  query.set('page_size', '50');
  if (filters.page) query.set('page', String(filters.page));
  if (filters.eventId) query.set('event_id', filters.eventId);
  if (filters.result) query.set('result', filters.result);
  if (filters.search?.trim()) query.set('search', filters.search.trim());
  return `?${query.toString()}`;
};

const messageByResult: Record<Exclude<ScanResultType, 'NETWORK_ERROR'>, string> = {
  ENTRY_GRANTED: 'Ticket valid. Entry granted.',
  ALREADY_USED: 'This ticket has already been used.',
  INVALID_TICKET: 'No valid ticket was found for this code.',
  CANCELLED: 'This ticket has been cancelled.',
  WRONG_EVENT: 'This ticket is not valid for the assigned gate event.',
  EVENT_CLOSED: 'Entry is currently closed.',
};

export const scansApi = {
  getPage: async (filters: ScanFilters = {}): Promise<ApiPage<ScanRecord>> => {
    const page = await apiRequest<ApiPage<ApiScanRecord>>(`/scans/${queryString(filters)}`);
    return { ...page, results: page.results.map(mapScan) };
  },

  getAll: async (): Promise<ScanRecord[]> => (await scansApi.getPage()).results,

  verifyTicket: async (
    scannedCode: string,
    _currentEventId: string,
    _gate?: string,
  ): Promise<{
    result: ScanResultType;
    ticket?: Ticket;
    scanRecord: ScanRecord;
    message: string;
  }> => {
    try {
      const response = await apiRequest<ScanResponse>(
        '/scans/',
        { method: 'POST', body: jsonBody({ token: scannedCode }) },
        [404, 409],
      );
      const result = response.result;
      return {
        result,
        ticket: response.ticket ? mapTicket(response.ticket) : undefined,
        scanRecord: mapScan(response.scan_record),
        message: result === 'NETWORK_ERROR'
          ? 'The scanner cannot reach the ticketing service. Do not allow entry.'
          : messageByResult[result],
      };
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw error;
    }
  },
};
