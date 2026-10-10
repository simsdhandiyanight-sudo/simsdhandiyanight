import logging
import uuid
from datetime import datetime, timedelta, timezone

import cloudinary
import cloudinary.api
import cloudinary.exceptions
import cloudinary.uploader
import requests
from cloudinary.utils import cloudinary_url
from django.conf import settings
from django.db import DatabaseError
from rest_framework.exceptions import APIException, NotFound

from .models import Payment

logger = logging.getLogger(__name__)


class PaymentProofStorageUnavailable(APIException):
    status_code = 503
    default_detail = "Payment proof storage is temporarily unavailable. Please retry."
    default_code = "PAYMENT_PROOF_STORAGE_UNAVAILABLE"


def _configure_cloudinary():
    if not all(
        (
            settings.CLOUDINARY_CLOUD_NAME,
            settings.CLOUDINARY_API_KEY,
            settings.CLOUDINARY_API_SECRET,
        )
    ):
        raise PaymentProofStorageUnavailable()
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )


def upload_payment_proof(image, *, image_format, image_size):
    _configure_cloudinary()
    upload_id = uuid.uuid4().hex
    try:
        result = cloudinary.uploader.upload(
            image,
            asset_folder=settings.CLOUDINARY_PAYMENT_PROOF_FOLDER,
            public_id=(
                f"{settings.CLOUDINARY_PAYMENT_PROOF_FOLDER}/{upload_id}"
            ),
            resource_type="image",
            type="authenticated",
            overwrite=False,
            unique_filename=False,
            use_filename=False,
        )
    except (cloudinary.exceptions.Error, requests.RequestException) as error:
        logger.warning("Cloudinary payment proof upload failed (%s).", type(error).__name__)
        raise PaymentProofStorageUnavailable() from None

    public_id = result.get("public_id")
    asset_id = result.get("asset_id")
    uploaded_type = result.get("type")
    uploaded_format = result.get("format")
    uploaded_size = result.get("bytes")
    version = result.get("version")
    acceptable_formats = {
        "jpeg": {"jpg", "jpeg"},
        "png": {"png"},
        "webp": {"webp"},
    }
    if (
        not isinstance(public_id, str)
        or not public_id.startswith(f"{settings.CLOUDINARY_PAYMENT_PROOF_FOLDER}/")
        or not isinstance(asset_id, str)
        or uploaded_type != "authenticated"
        or uploaded_format not in acceptable_formats.get(image_format, set())
        or uploaded_size != image_size
        or not isinstance(version, int)
    ):
        if isinstance(public_id, str):
            delete_unreferenced_payment_proof(public_id)
        logger.error("Cloudinary returned incomplete or non-private payment proof metadata.")
        raise PaymentProofStorageUnavailable()
    return {
        "public_id": public_id,
        "asset_id": asset_id,
        "version": version,
        "format": uploaded_format,
        "size": uploaded_size,
    }


def delete_unreferenced_payment_proof(public_id):
    try:
        _configure_cloudinary()
        if Payment.objects.filter(proof_cloudinary_public_id=public_id).exists():
            return
        cloudinary.uploader.destroy(
            public_id,
            resource_type="image",
            type="authenticated",
            invalidate=True,
        )
    except (
        DatabaseError,
        PaymentProofStorageUnavailable,
        cloudinary.exceptions.Error,
        requests.RequestException,
    ) as error:
        logger.error(
            "Unable to clean up an unreferenced payment proof (%s).",
            type(error).__name__,
        )


def get_payment_proof_content(payment):
    if not payment.proof_cloudinary_public_id:
        if payment.proof_screenshot is None:
            raise NotFound("The payment screenshot is unavailable.")
        return bytes(payment.proof_screenshot)

    _configure_cloudinary()
    signed_url, _ = cloudinary_url(
        payment.proof_cloudinary_public_id,
        format=payment.proof_format,
        version=payment.proof_cloudinary_version,
        resource_type="image",
        type="authenticated",
        secure=True,
        sign_url=True,
    )
    try:
        with requests.get(
            signed_url,
            timeout=(3, 20),
            allow_redirects=False,
            stream=True,
        ) as response:
            if response.status_code != 200:
                logger.error(
                    "Cloudinary payment proof retrieval returned HTTP %s.",
                    response.status_code,
                )
                raise PaymentProofStorageUnavailable()
            content = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                content.extend(chunk)
                if len(content) > 5 * 1024 * 1024:
                    logger.error("Cloudinary payment proof exceeded the configured size limit.")
                    raise PaymentProofStorageUnavailable()
    except requests.RequestException as error:
        logger.warning("Cloudinary payment proof retrieval failed (%s).", type(error).__name__)
        raise PaymentProofStorageUnavailable() from None
    return bytes(content)


def cleanup_orphaned_payment_proofs(*, grace_hours=168):
    _configure_cloudinary()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=grace_hours)
    cursor = None
    deleted = 0
    failures = 0
    while True:
        options = {
            "type": "authenticated",
            "prefix": f"{settings.CLOUDINARY_PAYMENT_PROOF_FOLDER}/",
            "max_results": 500,
        }
        if cursor:
            options["next_cursor"] = cursor
        try:
            result = cloudinary.api.resources(**options)
        except (cloudinary.exceptions.Error, requests.RequestException) as error:
            logger.error("Cloudinary orphan cleanup listing failed (%s).", type(error).__name__)
            raise PaymentProofStorageUnavailable() from None

        for resource in result.get("resources", []):
            created_at = datetime.fromisoformat(
                resource["created_at"].replace("Z", "+00:00")
            )
            public_id = resource.get("public_id")
            if (
                created_at >= cutoff
                or not isinstance(public_id, str)
                or Payment.objects.filter(proof_cloudinary_public_id=public_id).exists()
            ):
                continue
            try:
                cloudinary.uploader.destroy(
                    public_id,
                    resource_type="image",
                    type="authenticated",
                    invalidate=True,
                )
            except (cloudinary.exceptions.Error, requests.RequestException) as error:
                logger.error(
                    "Cloudinary orphan cleanup failed for an unreferenced asset (%s).",
                    type(error).__name__,
                )
                failures += 1
                continue
            deleted += 1

        cursor = result.get("next_cursor")
        if not cursor:
            if failures:
                raise PaymentProofStorageUnavailable(
                    f"Cloudinary orphan cleanup could not delete {failures} asset(s)."
                )
            return deleted
