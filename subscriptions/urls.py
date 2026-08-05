from django.urls import path
from . import views

urlpatterns = [
    path('', views.pricing_view, name='pricing'),
    path('success/', views.subscription_success_view, name='subscription_success'),

    path('razorpay/create-order/', views.create_razorpay_order, name='razorpay_create_order'),
    path('razorpay/verify/', views.verify_razorpay_payment, name='razorpay_verify'),

    path('paypal/create-order/', views.create_paypal_order, name='paypal_create_order'),
    path('paypal/capture/', views.capture_paypal_order, name='paypal_capture'),
]
