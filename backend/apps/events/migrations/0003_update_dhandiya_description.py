from django.db import migrations


DESCRIPTION = (
    "Celebrate the vibrant spirit of Navratri through Dandiya, a joyful "
    "celebration of music, dance, and togetherness.\n"
    "Get ready for an evening filled with rhythm, colours, energy, and festive vibes.\n"
    "Dance to lively beats and celebrate the season with friends, family, and loved ones.\n"
    "Put on your festive best and make memories that last beyond the night.\n"
    "Join us on 16th October and let the celebration begin"
)
PREVIOUS_DESCRIPTION = (
    "Celebrate Navratri with an evening of Dandiya, music, and festive activities "
    "at Soundarya College Campus."
)


def update_description(apps, schema_editor):
    Event = apps.get_model("events", "Event")
    Event.objects.filter(
        slug="dhandiya-night-2026",
        description=PREVIOUS_DESCRIPTION,
    ).update(description=DESCRIPTION)


def restore_previous_description(apps, schema_editor):
    Event = apps.get_model("events", "Event")
    Event.objects.filter(
        slug="dhandiya-night-2026",
        description=DESCRIPTION,
    ).update(description=PREVIOUS_DESCRIPTION)


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0002_event_instructions_event_location_url_and_more"),
    ]

    operations = [
        migrations.RunPython(update_description, restore_previous_description),
    ]
