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

export interface PaymentProofRegistrationResponse {
  registration_id: string;
  proof_access_token: string;
  registration_code: string;
  ticket_id: string | null;
  registration_status: string;
  can_submit_proof?: boolean;
  payment_status: string;
  reservation_expires_at: string | null;
  rejection_deadline: string | null;
  upi_id: string;
  upi_qr_image_url: string;
  amount: number;
  currency: string;
  reservation_hours: number;
  replayed: boolean;
}

export interface PaymentProofStatusResponse extends Omit<
  PaymentProofRegistrationResponse,
  'proof_access_token' | 'replayed'
> {
  event_name: string;
  applicant_name: string;
  applicant_email: string;
  ticket_tier_name: string;
  payment_id: string | null;
  utr_reference: string;
  transaction_id: string;
  submitted_at: string | null;
  rejection_reason: string;
  rejection_email_status: string;
  email_status: string;
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

  startProofRegistration: async (params: RegistrationCreateParams) => {
    const idempotencyKey = await registrationIdempotencyKey(params);
    const response = await apiRequest<PaymentProofRegistrationResponse>(
      '/payments/proof/registrations/',
      {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey },
        body: jsonBody(registrationRequest(params)),
      },
    );
    return { ...response, idempotency_key: idempotencyKey };
  },

  proofStatus: (registrationId: string, accessToken: string) =>
    apiRequest<PaymentProofStatusResponse>(
      `/payments/proof/registrations/${encodeURIComponent(registrationId)}/`,
      { headers: { 'X-Proof-Access-Token': accessToken } },
    ),

  submitProof: (
    registrationId: string,
    accessToken: string,
    utrReference: string,
    transactionId: string,
    screenshot: File,
    submissionKey: string,
  ) => {
    const body = new FormData();
    body.set('utr_reference', utrReference);
    body.set('transaction_id', transactionId);
    body.set('screenshot', screenshot);
    return apiRequest<PaymentProofStatusResponse>(
      `/payments/proof/registrations/${encodeURIComponent(registrationId)}/submit/`,
      {
        method: 'POST',
        headers: {
          'Idempotency-Key': submissionKey,
          'X-Proof-Access-Token': accessToken,
        },
        body,
      },
    );
  },

  proofConfirmationUrl: (registrationId: string) =>
    `/payments/proof/registrations/${encodeURIComponent(registrationId)}/ticket-id.pdf`,
};
