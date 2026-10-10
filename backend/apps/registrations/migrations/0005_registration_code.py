from django.db import migrations, models


def assign_registration_codes(apps, schema_editor):
    Registration = apps.get_model("registrations", "Registration")
    RegistrationSequence = apps.get_model(
        "registrations",
        "RegistrationSequence",
    )
    database = schema_editor.connection.alias
    registrations = (
        Registration.objects.using(database)
        .select_related("event")
        .order_by("created_at", "id")
    )
    next_numbers = {}

    for registration in registrations.iterator():
        year = registration.event.start_at.year
        number = next_numbers.get(year, 1)
        registration.registration_code = f"SIMS-DN-{year}-{number:05d}"
        registration.save(using=database, update_fields=("registration_code",))
        next_numbers[year] = number + 1

    RegistrationSequence.objects.using(database).bulk_create(
        RegistrationSequence(year=year, next_number=next_number)
        for year, next_number in next_numbers.items()
    )


def remove_registration_codes(apps, schema_editor):
    Registration = apps.get_model("registrations", "Registration")
    RegistrationSequence = apps.get_model(
        "registrations",
        "RegistrationSequence",
    )
    database = schema_editor.connection.alias
    Registration.objects.using(database).update(registration_code=None)
    RegistrationSequence.objects.using(database).all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("registrations", "0004_registration_reg_created_at_desc_idx_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="RegistrationSequence",
            fields=[
                (
                    "year",
                    models.PositiveSmallIntegerField(primary_key=True, serialize=False),
                ),
                ("next_number", models.PositiveIntegerField(default=1)),
            ],
        ),
        migrations.AddField(
            model_name="registration",
            name="registration_code",
            field=models.CharField(max_length=32, null=True),
        ),
        migrations.RunPython(
            assign_registration_codes,
            reverse_code=remove_registration_codes,
        ),
        migrations.AlterField(
            model_name="registration",
            name="registration_code",
            field=models.CharField(max_length=32, unique=True),
        ),
    ]
