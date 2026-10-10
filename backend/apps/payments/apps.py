from django.apps import AppConfig
from django.conf import settings
from django.core.checks import Warning, register
from django.core.checks.registry import Tags
import logging


logger = logging.getLogger(__name__)


@register(Tags.security)
def check_payu_configuration(app_configs, **kwargs):
    missing = [
        name
        for name in ("PAYU_MERCHANT_KEY", "PAYU_MERCHANT_SALT")
        if not getattr(settings, name, "")
    ]
    invalid_environment = getattr(settings, "PAYU_ENVIRONMENT", "test") not in (
        "test",
        "production",
    )
    if missing:
        return [
            Warning(
                "PayU checkout is disabled until merchant credentials are configured.",
                hint=f"Set {', '.join(missing)} in the backend environment.",
                id="payments.W001",
            )
        ]
    if invalid_environment:
        return [
            Warning(
                "PAYU_ENVIRONMENT must be either 'test' or 'production'.",
                id="payments.W002",
            )
        ]
    return []


class PaymentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.payments"

    def ready(self):
        if not settings.PAYU_MERCHANT_KEY or not settings.PAYU_MERCHANT_SALT:
            logger.warning(
                "PayU payment processing is disabled: merchant configuration is incomplete."
            )
