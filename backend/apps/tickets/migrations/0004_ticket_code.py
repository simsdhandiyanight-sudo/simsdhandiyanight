from django.db import migrations, models


def assign_ticket_codes(apps, schema_editor):
    Ticket = apps.get_model("tickets", "Ticket")
    database = schema_editor.connection.alias
    tickets = (
        Ticket.objects.using(database)
        .select_related("registration")
        .order_by("registration_id", "created_at", "id")
    )
    sequence_by_registration = {}

    for ticket in tickets.iterator():
        registration = ticket.registration
        number = sequence_by_registration.get(registration.pk, 1)
        ticket.ticket_code = f"{registration.registration_code}-T{number:02d}"
        ticket.save(using=database, update_fields=("ticket_code",))
        sequence_by_registration[registration.pk] = number + 1


class Migration(migrations.Migration):
    dependencies = [
        ("registrations", "0005_registration_code"),
        ("tickets", "0003_ticket_ticket_created_at_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="ticket_code",
            field=models.CharField(max_length=40, null=True),
        ),
        migrations.RunPython(
            assign_ticket_codes,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="ticket",
            name="ticket_code",
            field=models.CharField(max_length=40, unique=True),
        ),
    ]
