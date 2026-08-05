from django.contrib import admin
from .models import UserSubscription


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan_code", "status", "gateway", "currency", "amount", "created_at")
    list_filter = ('status', 'gateway', 'plan_code', 'is_lifetime')
    search_fields = ('user__username', 'user__email', 'gateway_order_id', 'gateway_payment_id')
