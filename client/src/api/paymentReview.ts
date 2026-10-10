import { apiRequest } from './http';

export interface PaymentReviewPayment {
  payment_id: string;
  payment_intent_id: string;
  order_id: string | null;
  provider_payment_id: string | null;
  provider: string;
  payment_status: string;
  provider_status: string;
  captured_at: string | null;
  amount: number;
  currency: string;
  event_id: string;
  event_name: string;
  ticket_tier_id: string;
  ticket_tier_name: string;
  buyer_name: string;
  buyer_email: string;
  registration_id: string | null;
  registration_code: string | null;
  ticket_count: number;
  expected_ticket_count: number;
  verification_status: string;
  ticket_issuance_status: string;
  failure: string;
  issue_codes: string[];
  updated_at: string;
}

export interface PaymentReviewRegistration {
  registration_id: string;
  registration_code: string;
  event_id: string;
  event_name: string;
  ticket_tier_id: string;
  ticket_tier_name: string;
  buyer_name: string;
  buyer_email: string;
  ticket_count: number;
  expected_ticket_count: number;
  created_at: string;
  issue_code: 'TICKET_WITHOUT_VALID_PAYMENT';
}

export interface PaymentReviewDashboard {
  issue_counts: Record<string, number>;
  payments: PaymentReviewPayment[];
  registrations_without_valid_payment: PaymentReviewRegistration[];
  has_more_payments: boolean;
  has_more_registrations: boolean;
}

export const paymentReviewApi = {
  getDashboard: () =>
    apiRequest<PaymentReviewDashboard>('/payments/review/dashboard/'),
  reconcile: (paymentId: string) =>
    apiRequest<unknown>(`/payments/review/${encodeURIComponent(paymentId)}/reconcile/`, {
      method: 'POST',
    }),
};
