import hashlib
import hmac

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .models import UserSubscription
from .plans import PLANS, all_plans_context, get_plan_context
from .pricing_utils import get_pricing_currency


def _user_phone(request):
    """Best-effort phone lookup — adjust field name to match your User/Profile model."""
    return getattr(request.user, "phone_number", None) or getattr(request.user, "phone", None)


def _queue_subscription_popup(request, sub):
    """Global popup queue — see life_simulation/context_processors.py ->
    pending_popup. Fires on whichever page the user next loads (normally
    the success page redirect right after this)."""
    request.session['pending_popup'] = {
        'type': 'subscription',
        'plan_name': sub.get_plan_code_display(),
        'is_lifetime': sub.is_lifetime,
    }


@login_required
def pricing_view(request):
    currency = get_pricing_currency(request, phone_number=_user_phone(request))
    context = {
        "plans": all_plans_context(currency),
        "currency": currency,
        "active_sub": UserSubscription.get_active_for_user(request.user),
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
        "paypal_client_id": settings.PAYPAL_CLIENT_ID,
    }
    return render(request, "subscriptions/pricing.html", context)


@login_required
def subscription_success_view(request):
    sub = UserSubscription.get_active_for_user(request.user)
    return render(request, "subscriptions/success.html", {"sub": sub})


# ── Razorpay (INR only) ───────────────────────────────────────────────────

@login_required
@require_POST
def create_razorpay_order(request):
    plan_code = request.POST.get("plan_code")
    if plan_code not in PLANS:
        return JsonResponse({"error": "Invalid plan"}, status=400)

    # Razorpay here is India-only. If the detected currency isn't INR,
    # tell the frontend to fall back to the PayPal flow instead.
    currency = get_pricing_currency(request, phone_number=_user_phone(request))
    if currency != "INR":
        return JsonResponse(
            {"error": "Razorpay is only available for India. Use PayPal for USD."},
            status=400,
        )

    plan = get_plan_context(plan_code, currency="INR")
    amount_paise = int(round(plan["price"] * 100))

    import razorpay
    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    try:
        order = client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "payment_capture": 1,
            "notes": {"user_id": str(request.user.id), "plan_code": plan_code},
        })
    except Exception as e:
        print(f"[ERROR] Razorpay order create: {e}")
        return JsonResponse({"error": "Could not create order"}, status=500)

    sub = UserSubscription.objects.create(
        user=request.user,
        plan_code=plan_code,
        is_lifetime=plan["effective_is_lifetime"],
        duration_days=plan["effective_duration_days"],
        currency="INR",
        amount=plan["price"],
        gateway="razorpay",
        gateway_order_id=order["id"],
        status="pending",
    )

    return JsonResponse({
        "order_id": order["id"],
        "amount": amount_paise,
        "currency": "INR",
        "key": settings.RAZORPAY_KEY_ID,
        "subscription_id": sub.id,
    })


@login_required
@require_POST
def verify_razorpay_payment(request):
    order_id = request.POST.get("razorpay_order_id")
    payment_id = request.POST.get("razorpay_payment_id")
    signature = request.POST.get("razorpay_signature")

    sub = UserSubscription.objects.filter(
        user=request.user, gateway_order_id=order_id, gateway="razorpay"
    ).first()
    if not sub:
        return JsonResponse({"error": "Subscription not found"}, status=404)

    expected_signature = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(),
        f"{order_id}|{payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()

    if expected_signature != signature:
        sub.status = "failed"
        sub.save()
        return JsonResponse({"error": "Signature verification failed"}, status=400)

    sub.gateway_payment_id = payment_id
    sub.activate()
    _queue_subscription_popup(request, sub)

    return JsonResponse({"success": True, "redirect": "/subscriptions/success/"})


# ── PayPal (USD only) ──────────────────────────────────────────────────────

def _paypal_base_url():
    return (
        "https://api-m.sandbox.paypal.com"
        if settings.PAYPAL_MODE == "sandbox"
        else "https://api-m.paypal.com"
    )


def _paypal_access_token():
    resp = requests.post(
        f"{_paypal_base_url()}/v1/oauth2/token",
        headers={"Accept": "application/json"},
        data={"grant_type": "client_credentials"},
        auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


@login_required
@require_POST
def create_paypal_order(request):
    plan_code = request.POST.get("plan_code")
    if plan_code not in PLANS:
        return JsonResponse({"error": "Invalid plan"}, status=400)

    # PayPal always charges USD — this is the international path regardless
    # of what get_pricing_currency() says, so an India user can still opt
    # into it manually if they want (e.g. no Indian card).
    plan = get_plan_context(plan_code, currency="USD")

    try:
        token = _paypal_access_token()
        resp = requests.post(
            f"{_paypal_base_url()}/v2/checkout/orders",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "intent": "CAPTURE",
                "purchase_units": [{
                    "amount": {"currency_code": "USD", "value": f"{plan['price']:.2f}"},
                    "custom_id": f"{request.user.id}:{plan_code}",
                }],
            },
            timeout=15,
        )
        resp.raise_for_status()
        order = resp.json()
    except Exception as e:
        print(f"[ERROR] PayPal order create: {e}")
        return JsonResponse({"error": "Could not create PayPal order"}, status=500)

    UserSubscription.objects.create(
        user=request.user,
        plan_code=plan_code,
        is_lifetime=plan["effective_is_lifetime"],
        duration_days=plan["effective_duration_days"],
        currency="USD",
        amount=plan["price"],
        gateway="paypal",
        gateway_order_id=order["id"],
        status="pending",
    )

    return JsonResponse({"order_id": order["id"]})


@login_required
@require_POST
def capture_paypal_order(request):
    order_id = request.POST.get("order_id")
    sub = UserSubscription.objects.filter(
        user=request.user, gateway_order_id=order_id, gateway="paypal"
    ).first()
    if not sub:
        return JsonResponse({"error": "Subscription not found"}, status=404)

    try:
        token = _paypal_access_token()
        resp = requests.post(
            f"{_paypal_base_url()}/v2/checkout/orders/{order_id}/capture",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15,
        )
        result = resp.json()
    except Exception as e:
        print(f"[ERROR] PayPal capture: {e}")
        sub.status = "failed"
        sub.save()
        return JsonResponse({"error": "Could not capture payment"}, status=500)

    if resp.status_code not in (200, 201) or result.get("status") != "COMPLETED":
        sub.status = "failed"
        sub.save()
        return JsonResponse({"error": "Payment not completed"}, status=400)

    sub.gateway_payment_id = result.get("id", order_id)
    sub.activate()
    _queue_subscription_popup(request, sub)

    return JsonResponse({"success": True, "redirect": "/subscriptions/success/"})