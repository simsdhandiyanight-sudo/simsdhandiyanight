import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create the initial admin from BOOTSTRAP_ADMIN_* environment variables."

    def handle(self, *args, **options):
        email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
        password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
        name = os.environ.get("BOOTSTRAP_ADMIN_NAME", "SIMS Admin").strip()
        reset_password = (
            os.environ.get("BOOTSTRAP_ADMIN_RESET_PASSWORD", "").strip().lower()
            == "true"
        )

        if not password:
            self.stdout.write("Admin bootstrap skipped; BOOTSTRAP_ADMIN_PASSWORD is not set.")
            return
        if not email:
            raise CommandError("Set BOOTSTRAP_ADMIN_EMAIL before enabling admin bootstrap.")
        if not name:
            raise CommandError("BOOTSTRAP_ADMIN_NAME must not be blank.")

        User = get_user_model()
        existing_user = User.objects.filter(email=email).first()
        if existing_user:
            if not (
                existing_user.is_superuser
                and existing_user.is_staff
                and existing_user.role == User.Role.ADMIN
            ):
                raise CommandError(
                    f"Cannot bootstrap admin: an account already exists for {email} "
                    "but is not an administrator."
                )
            if reset_password:
                existing_user.set_password(password)
                existing_user.save(update_fields=["password"])
                self.stdout.write(
                    self.style.SUCCESS(f"Updated administrator password for {email}.")
                )
                return
            self.stdout.write(f"Administrator account already exists for {email}; unchanged.")
            return

        User.objects.create_superuser(email=email, password=password, name=name)
        self.stdout.write(self.style.SUCCESS(f"Created administrator account for {email}."))
