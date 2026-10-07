from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand

from apps.events.models import Event, TicketTier


EVENT_ID = "8b3f7a20-6e8d-4b91-a462-9c5d2f1e7043"
EVENT_SLUG = "dhandiya-night-2026"
IST = ZoneInfo("Asia/Kolkata")


class Command(BaseCommand):
    help = "Create the canonical Dhandiya Night 2026 event and configured offers."

    def handle(self, *args, **options):
        event, created = Event.objects.get_or_create(
            id=EVENT_ID,
            defaults={
                "slug": EVENT_SLUG,
                "name": "Dhandiya Night 2026",
                "tagline": "Dance · Dandiya · Dhamaka",
                "description": (
                    "Celebrate Navratri with an evening of Dandiya, music, and "
                    "festive activities at Soundarya College Campus."
                ),
                "category": "music",
                "start_at": datetime(2026, 10, 16, 18, 0, tzinfo=IST),
                "end_at": datetime(2026, 10, 16, 21, 0, tzinfo=IST),
                "venue": "Soundarya College Campus",
                "city": "Bengaluru",
                "address": "Sidedahalli, Soundarya Layout, Bengaluru - 560073",
                "status": Event.Status.OPEN,
                "registration_open": True,
                "capacity": 2500,
                "highlights": [
                    "An evening of Garba, Dandiya, and festive music",
                    "Traditional dance with friends and the Soundarya community",
                    "Festive decorations and folk-inspired details",
                ],
                "schedule": [
                    {"time": "6:00 PM", "title": "Doors Open & Welcome", "speaker": "Soundarya Institute"},
                    {"time": "6:30 PM", "title": "Garba & Dandiya Celebration", "speaker": "Daksha Student Council"},
                    {"time": "8:45 PM", "title": "Final Dance & Festive Farewell", "speaker": "Daksha Student Council"},
                ],
                "faqs": [],
                "accent_color": "#b71959",
            },
        )
        if not created and event.slug != EVENT_SLUG:
            raise RuntimeError(f"Canonical event UUID is already assigned to unexpected slug '{event.slug}'.")

        tiers = (
            {
                "slug": "single-ticket",
                "name": "Single Ticket",
                "price": "149.00",
                "admission_count": 1,
                "description": "One admission. Taxes, if applicable, are not configured.",
                "perks": ["One Dandiya Night admission"],
            },
            {
                "slug": "combo-buy-3-get-1",
                "name": "Combo Offer — Buy 3, Get 1 Free",
                "price": "447.00",
                "admission_count": 4,
                "description": "Four admissions for the configured combo price.",
                "perks": ["Four independently scannable admissions"],
            },
        )
        for tier in tiers:
            TicketTier.objects.get_or_create(event=event, slug=tier["slug"], defaults=tier)

        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if created else 'Found'} {event.name} ({event.id}); "
                "no registrations, tickets, scans, or staff accounts were seeded."
            )
        )
