import { apiRequest, jsonBody } from './http';
import {
  registrationIdempotencyKey,
  registrationRequest,
  RegistrationCreateParams,
} from './registrations';

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

  proofTicketsUrl: (registrationId: string) =>
    `/payments/proof/registrations/${encodeURIComponent(registrationId)}/tickets.pdf`,
};
