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
  order_id?: string;
  display_amount?: number;
  key_id: string;
  payment_verified?: boolean;
  registration?: ApiRegistration;
  ticket?: ApiTicket;
  tickets?: ApiTicket[];
  delivery_status?: string | null;
}

export interface PaymentVerificationResponse {
  payment_verified: boolean;
  order_id: string;
  payment_id: string;
  registration: ApiRegistration;
  ticket: ApiTicket;
  tickets: ApiTicket[];
  delivery_status: string | null;
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

  verify: (payload: {
    razorpay_order_id: string;
    razorpay_payment_id: string;
    razorpay_signature: string;
  }) =>
    apiRequest<PaymentVerificationResponse>('/payments/verify/', {
      method: 'POST',
      body: jsonBody(payload),
    }),

  recordFailure: (payload: { razorpay_order_id: string }) =>
    apiRequest<{ status: string }>('/payments/failure/', {
      method: 'POST',
      body: jsonBody(payload),
    }),
};
