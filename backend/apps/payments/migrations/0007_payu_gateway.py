from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0006_payment_payment_status_created_idx"),
    ]

    operations = [
        migrations.RenameField(
            model_name="payment",
            old_name="razorpay_order_id",
            new_name="provider_order_id",
        ),
        migrations.RenameField(
            model_name="payment",
            old_name="razorpay_payment_id",
            new_name="provider_payment_id",
        ),
        migrations.AddField(
            model_name="payment",
            name="provider",
            field=models.CharField(
                choices=[("RAZORPAY", "Razorpay (legacy)"), ("PAYU", "PayU")],
                default="RAZORPAY",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="provider_status",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="payment",
            name="payment_method",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AlterField(
            model_name="payment",
            name="status",
            field=models.CharField(
                choices=[
                    ("CREATING", "Creating order"),
                    ("CREATED", "Order created"),
                    ("PENDING", "Pending"),
                    ("AUTHORIZED", "Authorized"),
                    ("CAPTURED", "Captured"),
                    ("FAILED", "Failed"),
                ],
                default="CREATING",
                max_length=12,
            ),
        ),
    ]
