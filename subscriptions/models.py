from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class UserSubscription(models.Model):
    PLAN_CHOICES = [
        ("monthly", "Monthly"),
        ("quarterly", "3-Month Pass"),
        ("yearly", "Yearly"),
    ]
    GATEWAY_CHOICES = [
        ("razorpay", "Razorpay"),
        ("paypal", "PayPal"),
    ]
    CURRENCY_CHOICES = [
        ("USD", "USD"),
        ("INR", "INR"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("active", "Active"),
        ("expired", "Expired"),
        ("cancelled", "Cancelled"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions"
    )
    plan_code = models.CharField(max_length=20, choices=PLAN_CHOICES)
    is_lifetime = models.BooleanField(default=False)
    duration_days = models.PositiveIntegerField(null=True, blank=True)

    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="USD")
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    gateway = models.CharField(max_length=20, choices=GATEWAY_CHOICES)
    gateway_order_id = models.CharField(max_length=120, blank=True, db_index=True)
    gateway_payment_id = models.CharField(max_length=120, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} — {self.plan_code} ({self.status})"

    def activate(self):
        self.status = "active"
        self.started_at = timezone.now()
        if self.is_lifetime:
            self.expires_at = None
        else:
            self.expires_at = self.started_at + timedelta(days=self.duration_days or 30)
        self.save()

    def is_active(self):
        if self.status != "active":
            return False
        if self.is_lifetime:
            return True
        return bool(self.expires_at and self.expires_at > timezone.now())

    @classmethod
    def get_active_for_user(cls, user):
        sub = cls.objects.filter(user=user, status="active").order_by("-created_at").first()
        if sub and sub.is_active():
            return sub
        return None