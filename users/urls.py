from django.urls import path
from . import views
from .views import set_timezone

urlpatterns = [
    path('register/',          views.register_view,      name='register'),
    path('login/',             views.login_view,          name='login'),
    path('firebase-login/',    views.firebase_login_view, name='firebase_login'),
    path('complete-profile/',  views.complete_profile_view, name='complete_profile'),
    path('verify-otp/',        views.verify_otp_view,     name='verify_otp'),
    path('resend-otp/',        views.resend_otp_view,     name='resend_otp'),
    path('logout/',            views.logout_view,         name='logout'),
    path('profile/',           views.profile_view,        name='profile'),
    path('profile/edit/',      views.edit_profile,        name='edit_profile'),
    path('profile/delete/',    views.delete_account,      name='delete_account'),
    path('debug-session/',     views.debug_session_view,  name='debug_session'),
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('reset-password/', views.reset_password_view, name='reset_password'),
    path('resend-reset-otp/', views.resend_reset_otp_view, name='resend_reset_otp'),
    path("set-timezone/", set_timezone, name="set_timezone"),
]