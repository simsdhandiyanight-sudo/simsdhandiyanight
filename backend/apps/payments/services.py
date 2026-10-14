from django.db.models import Count, Exists, F, OuterRef, Q

from apps.payments.models import Payment, PaymentIntent
from apps.registrations.models import Registration


def get_payment_review_dashboard():
    captured_payment_queryset = (
        Payment.objects.filter(
            Q(status=Payment.Status.CAPTURED)
            | Q(
                provider=Payment.Provider.PAYU,
                status__in=(Payment.Status.CREATED, Payment.Status.PENDING),
                verification_status__in=(
                    Payment.VerificationStatus.PENDING,
                    Payment.VerificationStatus.FAILED,
                ),
            )
        )
        .select_related("intent__event", "intent__ticket_tier", "intent__registration")
        .annotate(
            ticket_count=Count("intent__registration__tickets", distinct=True),
            captured_for_intent=Count(
                "intent__payments",
                filter=Q(intent__payments__status=Payment.Status.CAPTURED),
                distinct=True,
            ),
        )
    )
    needs_review = (
        Q(ticket_issuance_status__in=(
            Payment.TicketIssuanceStatus.PENDING,
            Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED,
        ))
        | ~Q(verification_status=Payment.VerificationStatus.VERIFIED)
        | Q(intent__registration__isnull=True)
        | ~Q(
            ticket_count=F("intent__ticket_tier__admission_count")
            * F("intent__quantity")
        )
        | Q(captured_for_intent__gt=1)
    )
    payment_review_queryset = captured_payment_queryset.filter(needs_review)
    captured_payments_raw = list(payment_review_queryset.order_by("-updated_at")[:201])
    has_more_payments = len(captured_payments_raw) > 200
    captured_payments = captured_payments_raw[:200]
    payment_cases = []
    issue_counts_agg = captured_payment_queryset.aggregate(
        PAYMENT_REVIEW_REQUIRED=Count(
            "id",
            filter=(
                Q(ticket_issuance_status__in=(
                    Payment.TicketIssuanceStatus.PENDING,
                    Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED,
                ))
                | ~Q(verification_status=Payment.VerificationStatus.VERIFIED)
                | Q(intent__registration__isnull=True)
                | ~Q(
                    ticket_count=F("intent__ticket_tier__admission_count")
                    * F("intent__quantity")
                )
            ),
        ),
        TICKET_ISSUANCE_FAILED=Count(
            "id",
            filter=Q(
                status=Payment.Status.CAPTURED,
                ticket_issuance_status=Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED,
            ),
        ),
        PAYMENT_CAPTURED_WITHOUT_TICKET=Count(
            "id",
            filter=Q(status=Payment.Status.CAPTURED)
            & (Q(intent__registration__isnull=True) | Q(ticket_count=0)),
        ),
        PAYMENT_CAPTURED_WITH_INCOMPLETE_REGISTRATION=Count(
            "id",
            filter=Q(status=Payment.Status.CAPTURED)
            & (
                Q(intent__registration__isnull=True)
                | ~Q(
                    ticket_count=F("intent__ticket_tier__admission_count")
                    * F("intent__quantity")
                )
            ),
        ),
        DUPLICATE_PAYMENT=Count(
            "id",
            filter=Q(status=Payment.Status.CAPTURED)
            & Q(captured_for_intent__gt=1),
        ),
    )
    issue_counts = {
        key: issue_counts_agg[key] or 0
        for key in (
            "PAYMENT_REVIEW_REQUIRED",
            "TICKET_ISSUANCE_FAILED",
            "PAYMENT_CAPTURED_WITHOUT_TICKET",
            "PAYMENT_CAPTURED_WITH_INCOMPLETE_REGISTRATION",
            "DUPLICATE_PAYMENT",
        )
    }
    for payment in captured_payments:
        intent = payment.intent
        registration = intent.registration
        issue_codes = []
        if payment.ticket_issuance_status != Payment.TicketIssuanceStatus.ISSUED:
            issue_codes.append("PAYMENT_REVIEW_REQUIRED")
        if (
            payment.status == Payment.Status.CAPTURED
            and payment.ticket_issuance_status
            == Payment.TicketIssuanceStatus.ADMIN_REVIEW_REQUIRED
        ):
            issue_codes.append("TICKET_ISSUANCE_FAILED")
        if payment.status == Payment.Status.CAPTURED and (
            registration is None or payment.ticket_count == 0
        ):
            issue_codes.append("PAYMENT_CAPTURED_WITHOUT_TICKET")
        if payment.status == Payment.Status.CAPTURED and (
            registration is None
            or payment.ticket_count
            != intent.quantity * intent.ticket_tier.admission_count
        ):
            issue_codes.append("PAYMENT_CAPTURED_WITH_INCOMPLETE_REGISTRATION")
        if (
            payment.status == Payment.Status.CAPTURED
            and payment.captured_for_intent > 1
        ):
            issue_codes.append("DUPLICATE_PAYMENT")
        if payment.verification_status != Payment.VerificationStatus.VERIFIED:
            issue_codes.append("PAYMENT_REVIEW_REQUIRED")
        if issue_codes:
            payment_cases.append(
                {
                    "payment_id": str(payment.id),
                    "payment_intent_id": str(intent.idempotency_key),
                    "provider": payment.provider,
                    "order_id": payment.provider_order_id,
                    "provider_payment_id": payment.provider_payment_id,
                    "payment_status": payment.status,
                    "provider_status": payment.provider_status,
                    "captured_at": payment.captured_at.isoformat() if payment.captured_at else None,
                    "amount": payment.amount,
                    "currency": payment.currency,
                    "event_id": str(intent.event_id),
                    "event_name": intent.event.name,
                    "ticket_tier_id": str(intent.ticket_tier_id),
                    "ticket_tier_name": intent.ticket_tier.name,
                    "buyer_name": intent.buyer_name,
                    "buyer_email": intent.buyer_email,
                    "registration_id": str(registration.id) if registration else None,
                    "registration_code": (
                        registration.registration_code if registration else None
                    ),
                    "ticket_count": payment.ticket_count,
                    "expected_ticket_count": (
                        intent.quantity * intent.ticket_tier.admission_count
                    ),
                    "verification_status": payment.verification_status,
                    "ticket_issuance_status": payment.ticket_issuance_status,
                    "failure": payment.ticket_issuance_failure or payment.failure_message,
                    "issue_codes": sorted(set(issue_codes)),
                    "updated_at": payment.updated_at.isoformat(),
                }
            )

    valid_payment_intents = PaymentIntent.objects.filter(
        registration_id=OuterRef("pk"),
        status=PaymentIntent.Status.VERIFIED,
        payments__verification_status=Payment.VerificationStatus.VERIFIED,
        payments__ticket_issuance_status=Payment.TicketIssuanceStatus.ISSUED,
    ).filter(
        Q(payments__status=Payment.Status.CAPTURED)
        | Q(
            payments__provider=Payment.Provider.UPI_MANUAL,
            payments__status=Payment.Status.VERIFIED,
        )
    )
    registrations_without_valid_payment_queryset = (
        Registration.objects.filter(source=Registration.Source.ONLINE)
        .annotate(
            ticket_count=Count("tickets", distinct=True),
            has_valid_payment=Exists(valid_payment_intents),
        )
        .filter(has_valid_payment=False, ticket_count__gt=0)
        .select_related("event", "ticket_tier")
        .order_by("-created_at")
    )
    registration_rows = list(registrations_without_valid_payment_queryset[:201])
    has_more_registrations = len(registration_rows) > 200
    registration_cases = [
        {
            "registration_id": str(registration.id),
            "registration_code": registration.registration_code,
            "event_id": str(registration.event_id),
            "event_name": registration.event.name,
            "ticket_tier_id": str(registration.ticket_tier_id),
            "ticket_tier_name": registration.ticket_tier.name,
            "buyer_name": registration.buyer_name,
            "buyer_email": registration.buyer_email,
            "ticket_count": registration.ticket_count,
            "expected_ticket_count": (
                registration.ticket_tier.admission_count * registration.quantity
            ),
            "created_at": registration.created_at.isoformat(),
            "issue_code": "TICKET_WITHOUT_VALID_PAYMENT",
        }
        for registration in registration_rows[:200]
    ]
    issue_counts["TICKET_WITHOUT_VALID_PAYMENT"] = (
        registrations_without_valid_payment_queryset.count()
        if has_more_registrations
        else len(registration_rows)
    )
    return {
        "issue_counts": issue_counts,
        "payments": payment_cases,
        "registrations_without_valid_payment": registration_cases,
        "has_more_payments": has_more_payments,
        "has_more_registrations": has_more_registrations,
    }
