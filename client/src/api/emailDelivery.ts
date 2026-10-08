import { apiRequest, jsonBody } from './http';

export type EmailPriority = 'STAFF' | 'COMPLIMENTARY' | 'REGULAR';
export type EmailDeliveryStatus =
  | 'PENDING'
  | 'SENDING'
  | 'SENT'
  | 'DELIVERED'
  | 'FAILED'
  | 'RECONCILIATION_REQUIRED';

export interface EmailDeliveryRecord {
  id: string;
  ticket_id: string;
  attendee_name: string;
  event_name: string;
  recipient: string;
  priority: EmailPriority;
  status: EmailDeliveryStatus;
  attempt_count: number;
  failure_reason: string;
  provider_message_id: string | null;
  created_at: string;
  last_attempt_at: string | null;
}

export interface EmailDeliveryDashboard {
  total_ticket_emails: number;
  provider_configured: boolean;
  statuses: Partial<Record<EmailDeliveryStatus, number>>;
  priorities: Partial<Record<EmailPriority, number>>;
  quota: {
    brevo_limit: number;
    regular_allocation: number;
    priority_allocation: number;
    regular_sent: number;
    priority_sent: number;
    regular_reserved: number;
    priority_reserved: number;
    total_sent: number;
    remaining_regular: number;
    remaining_priority: number;
    date: string;
  };
  queue: EmailDeliveryRecord[];
}

export const emailDeliveryApi = {
  getDashboard: () =>
    apiRequest<EmailDeliveryDashboard>('/payments/delivery/dashboard/'),

  retry: (deliveryId: string) =>
    apiRequest<{ status: EmailDeliveryStatus; attempt_count: number; queued: boolean }>(
      `/payments/delivery/${encodeURIComponent(deliveryId)}/retry/`,
      { method: 'POST', body: jsonBody({}) },
    ),

  updatePriority: (deliveryId: string, priority: EmailPriority) =>
    apiRequest<{ id: string; priority: EmailPriority }>(
      `/payments/delivery/${encodeURIComponent(deliveryId)}/priority/`,
      { method: 'PATCH', body: jsonBody({ priority }) },
    ),
};
