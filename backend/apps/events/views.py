from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdministrator
from apps.tickets.models import Ticket
from .models import Event
from .serializers import AdminEventSerializer, PublicEventSerializer, ordinal_day


def public_events_queryset():
    return (
        Event.objects.annotate(
            active_ticket_count=Count(
                "registrations__tickets",
                filter=Q(registrations__tickets__status__in=(Ticket.Status.ISSUED, Ticket.Status.USED)),
                distinct=True,
            ),
            used_ticket_count=Count(
                "registrations__tickets",
                filter=Q(registrations__tickets__status=Ticket.Status.USED),
                distinct=True,
            ),
        )
        .prefetch_related("tiers")
    )


class EventListView(APIView):
    def get_permissions(self):
        permission = IsAdministrator if self.request.method == "POST" else AllowAny
        return [permission()]

    def get(self, request):
        events = public_events_queryset()
        return Response(PublicEventSerializer(events, many=True).data)

    @method_decorator(csrf_protect)
    def post(self, request):
        serializer = AdminEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = serializer.save()
        event = public_events_queryset().get(pk=event.pk)
        return Response(PublicEventSerializer(event).data, status=status.HTTP_201_CREATED)


class EventDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, event_identifier):
        try:
            event_id = serializers.UUIDField().run_validation(event_identifier)
        except serializers.ValidationError:
            event = get_object_or_404(public_events_queryset(), slug=event_identifier)
        else:
            event = get_object_or_404(public_events_queryset(), pk=event_id)
        return Response(PublicEventSerializer(event).data)

    @method_decorator(csrf_protect)
    def patch(self, request, event_identifier):
        if not request.user.is_authenticated or request.user.role != "ADMIN":
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Administrator access is required.")
        try:
            event_id = serializers.UUIDField().run_validation(event_identifier)
        except serializers.ValidationError:
            event = get_object_or_404(Event, slug=event_identifier)
        else:
            event = get_object_or_404(Event, pk=event_id)
        serializer = AdminEventSerializer(event, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        event = serializer.save()
        event = public_events_queryset().get(pk=event.pk)
        return Response(PublicEventSerializer(event).data)


class AdminEventContextView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request, event_slug):
        event = get_object_or_404(
            Event.objects.only(
                "id",
                "slug",
                "capacity",
                "status",
                "registration_open",
                "start_at",
            ),
            slug=event_slug,
        )
        event_date = timezone.localtime(event.start_at).date()
        tiers = event.tiers.filter(is_available=True).values("id", "name", "price")
        return Response(
            {
                "id": str(event.id),
                "slug": event.slug,
                "capacity": event.capacity,
                "status": (
                    "upcoming"
                    if event.status == Event.Status.OPEN and not event.registration_open
                    else event.status.lower()
                ),
                "formattedDate": (
                    f"{ordinal_day(event_date.day)} {event_date.strftime('%B %Y')}"
                ),
                "tiers": [
                    {
                        "id": str(tier["id"]),
                        "name": tier["name"],
                        "price": float(tier["price"]),
                    }
                    for tier in tiers
                ],
            }
        )
