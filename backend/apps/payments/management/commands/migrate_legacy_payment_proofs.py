from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.payments.cloudinary_storage import (
    PaymentProofStorageUnavailable,
    delete_unreferenced_payment_proof,
    upload_payment_proof,
)
from apps.payments.models import Payment
from apps.payments.proof import validate_payment_proof_image


class Command(BaseCommand):
    help = "Move pre-Cloudinary payment proof images to private Cloudinary storage."

    def handle(self, *args, **options):
        payment_ids = list(
            Payment.objects.filter(
                provider=Payment.Provider.UPI_MANUAL,
                proof_screenshot__isnull=False,
                proof_cloudinary_public_id__isnull=True,
            ).values_list("pk", flat=True)
        )
        migrated = 0
        for payment_id in payment_ids:
            uploaded_asset = None
            try:
                with transaction.atomic():
                    payment = Payment.objects.select_for_update().get(pk=payment_id)
                    if payment.proof_cloudinary_public_id:
                        continue
                    image = ContentFile(bytes(payment.proof_screenshot), name="payment-proof")
                    content_type = validate_payment_proof_image(image)
                    uploaded_asset = upload_payment_proof(
                        image,
                        image_format=content_type.split("/", 1)[1],
                        image_size=image.size,
                    )
                    payment.proof_cloudinary_public_id = uploaded_asset["public_id"]
                    payment.proof_cloudinary_asset_id = uploaded_asset["asset_id"]
                    payment.proof_cloudinary_version = uploaded_asset["version"]
                    payment.proof_format = uploaded_asset["format"]
                    payment.proof_size_bytes = uploaded_asset["size"]
                    payment.proof_content_type = content_type
                    payment.proof_screenshot = None
                    payment.save(
                        update_fields=(
                            "proof_cloudinary_public_id",
                            "proof_cloudinary_asset_id",
                            "proof_cloudinary_version",
                            "proof_format",
                            "proof_size_bytes",
                            "proof_content_type",
                            "proof_screenshot",
                            "updated_at",
                        )
                    )
            except Exception as error:
                if uploaded_asset:
                    delete_unreferenced_payment_proof(uploaded_asset["public_id"])
                if isinstance(error, PaymentProofStorageUnavailable):
                    raise CommandError(str(error)) from error
                raise
            migrated += 1
        self.stdout.write(self.style.SUCCESS(f"Migrated {migrated} legacy payment proof(s)."))
