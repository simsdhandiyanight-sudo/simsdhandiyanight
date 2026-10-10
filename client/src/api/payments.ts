import { apiRequest, jsonBody } from './http';
import {
  ApiRegistration,
  ApiTicket,
} from './serializers';
import {
  registrationIdempotencyKey,
  registrationRequest,
  RegistrationCreateParams,
} from './registrations';

export interface PaymentOrderResponse {
  amount?: number;
  currency?: string;
  order_id?: string | null;
  display_amount?: number;
  checkout_url?: string;
  payment_params?: Record<string, string>;
  payment_verified?: boolean;
  payment_status?: string;
  registration?: ApiRegistration;
  ticket?: ApiTicket;
  tickets?: ApiTicket[];
  delivery_status?: string | null;
}

export interface PaymentVerificationResponse {
  payment_verified: boolean;
  payment_status: string;
  order_id?: string | null;
  payment_id?: string | null;
  registration?: ApiRegistration;
  ticket?: ApiTicket;
  tickets?: ApiTicket[];
  delivery_status?: string | null;
  verification_status?: string;
  ticket_issuance_status?: string;
  verification_message?: string;
}

export const paymentsApi = {
  createOrder: async (params: RegistrationCreateParams) => {
    const idempotencyKey = await registrationIdempotencyKey(params);
    const request = registrationRequest(params);
    const response = await apiRequest<PaymentOrderResponse>('/payments/create-order/', {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
      body: jsonBody(request),
    });
    return { ...response, idempotency_key: idempotencyKey };
  },

  status: (txnid: string, idempotencyKey: string) =>
    apiRequest<PaymentVerificationResponse>(
      `/payments/status/?txnid=${encodeURIComponent(txnid)}&idempotency_key=${encodeURIComponent(idempotencyKey)}`,
    ),
};
