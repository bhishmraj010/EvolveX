import hmac
import random
import time
import zoneinfo

from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.http import JsonResponse

from django.core.mail import send_mail
from django.conf import settings
from datetime import timedelta
import json
from .forms import (
    RegisterForm, LoginForm, ProfileForm, CompleteProfileForm, OTPForm,
    ForgotPasswordForm, ResetPasswordForm,
)
from .achievements import get_badges

OTP_VALID_SECONDS = 10 * 60  # 10 minutes
OTP_MAX_ATTEMPTS = 5  # after this many wrong guesses, the code is invalidated


def _check_otp(request, entered_otp, otp_key, expiry_key, attempts_key):
    """
    Shared OTP verification used by both signup and password-reset.
    Returns 'ok', 'expired', 'locked', or 'wrong'. On 'wrong', increments
    the attempt counter; after OTP_MAX_ATTEMPTS wrong guesses the code is
    invalidated (forces a resend) instead of allowing unlimited brute-force
    guessing of a 6-digit code.
    """
    real_otp = request.session.get(otp_key)
    expiry = request.session.get(expiry_key, 0)
    attempts = request.session.get(attempts_key, 0)

    if not real_otp:
        return 'expired'
    if time.time() > expiry:
        return 'expired'
    if attempts >= OTP_MAX_ATTEMPTS:
        for key in (otp_key, expiry_key, attempts_key):
            request.session.pop(key, None)
        return 'locked'

    # Constant-time comparison — a 6-digit code is low-entropy already,
    # but there's no reason not to compare it safely.
    if hmac.compare_digest(str(entered_otp), str(real_otp)):
        request.session.pop(attempts_key, None)
        return 'ok'

    request.session[attempts_key] = attempts + 1
    return 'wrong'


def register_view(request):
    if request.user.is_authenticated:
        return redirect('reports_home')
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, f'Welcome, {user.get_display_name()}! 🎮')
        return redirect('reports_home')
    return render(request, 'users/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('reports_home')
    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        messages.success(request, f'Welcome back, {user.get_display_name()}! 🔥')

        # Only follow ?next=... if it's a safe, same-site URL — otherwise
        # an attacker could craft a login link like
        # /users/login/?next=https://evil.com and redirect people there
        # right after they authenticate.
        next_url = request.GET.get('next') or request.POST.get('next')
        if next_url and url_has_allowed_host_and_scheme(
            url=next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return redirect(next_url)
        return redirect('reports_home')
    return render(request, 'users/login.html', {'form': form})


def _send_otp_email(email, otp, name=''):
    """Sends the 6-digit verification code. With EMAIL_BACKEND set to the
    console backend (dev default), this just prints to the terminal instead
    of actually emailing anyone — switch to an SMTP backend to send for
    real."""
    subject = 'Your EvolveX verification code'
    message = (
        f'Hi {name or "there"},\n\n'
        f'Your EvolveX verification code is: {otp}\n\n'
        f'This code expires in 10 minutes. If you did not request this, '
        f'you can safely ignore this email.\n\n'
        f'— EvolveX'
    )
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'noreply@evolvex.local'
    send_mail(subject, message, from_email, [email], fail_silently=False)


def _send_reset_otp_email(email, otp, name=''):
    """Sends the password-reset verification code. Uses the same console/SMTP
    EMAIL_BACKEND as signup OTPs — prints to terminal in dev, sends for real
    once EMAIL_BACKEND is switched to SMTP."""
    subject = 'Your EvolveX password reset code'
    message = (
        f'Hi {name or "there"},\n\n'
        f'Your EvolveX password reset code is: {otp}\n\n'
        f'This code expires in 10 minutes. If you did not request a password '
        f'reset, you can safely ignore this email — your password will not be changed.\n\n'
        f'— EvolveX'
    )
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'noreply@evolvex.local'
    send_mail(subject, message, from_email, [email], fail_silently=False)


def complete_profile_view(request):
    email = request.session.get('pending_google_email')
    if not email:
        return redirect('login')
    name = request.session.get('pending_google_name', '')
    form = CompleteProfileForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        # Don't create the account yet — stash the submitted data in the
        # session and send an OTP to the user's email first. The account is
        # only created once the code is verified (see verify_otp_view).
        request.session['pending_profile_data'] = {
            'username': form.cleaned_data['username'],
            'phone_number': form.cleaned_data['phone_number'],
            'password1': form.cleaned_data['password1'],
        }
        otp = f'{random.randint(0, 999999):06d}'
        request.session['pending_otp'] = otp
        request.session['pending_otp_expiry'] = time.time() + OTP_VALID_SECONDS

        try:
            _send_otp_email(email, otp, name)
        except Exception as e:
            print(f"[ERROR] Sending OTP email: {e}")
            messages.error(request, 'Could not send the verification email. Please try again.')
            return render(request, 'users/complete_profile.html', {'form': form, 'email': email})

        messages.info(request, f'We sent a verification code to {email}.')
        return redirect('verify_otp')
    return render(request, 'users/complete_profile.html', {'form': form, 'email': email})


def verify_otp_view(request):
    email = request.session.get('pending_google_email')
    profile_data = request.session.get('pending_profile_data')
    if not email or not profile_data:
        return redirect('login')

    form = OTPForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        entered_otp = form.cleaned_data['otp']
        result = _check_otp(request, entered_otp, 'pending_otp', 'pending_otp_expiry', 'pending_otp_attempts')

        if result == 'expired':
            messages.error(request, 'That code has expired. Please request a new one.')
        elif result == 'locked':
            messages.error(request, 'Too many incorrect attempts. Please request a new code.')
        elif result == 'wrong':
            messages.error(request, 'Incorrect code. Please check your email and try again.')
        else:  # 'ok'
            User = get_user_model()
            name = request.session.get('pending_google_name', '')
            try:
                user = User.objects.create_user(
                    username=profile_data['username'],
                    email=email,
                    password=profile_data['password1'],
                )
            except Exception as e:
                # Rare race: username/phone got taken by someone else in
                # the window between form-submit and OTP-verify. Fail
                # gracefully back to the profile step instead of a 500.
                print(f"[ERROR] Account creation after OTP verify: {e}")
                messages.error(
                    request,
                    'That username or phone number was just taken by someone else — please pick another.'
                )
                return redirect('complete_profile')

            user.name = name
            user.phone_number = profile_data['phone_number']
            user.save()

            for key in ('pending_google_email', 'pending_google_name',
                        'pending_profile_data', 'pending_otp', 'pending_otp_expiry',
                        'pending_otp_attempts'):
                request.session.pop(key, None)

            login(request, user)
            messages.success(request, f'Welcome to EvolveX, {user.get_display_name()}!')
            return redirect('reports_home')

    return render(request, 'users/verify_otp.html', {'form': form, 'email': email})


def resend_otp_view(request):
    email = request.session.get('pending_google_email')
    profile_data = request.session.get('pending_profile_data')
    if not email or not profile_data:
        return redirect('login')

    name = request.session.get('pending_google_name', '')
    otp = f'{random.randint(0, 999999):06d}'
    request.session['pending_otp'] = otp
    request.session['pending_otp_expiry'] = time.time() + OTP_VALID_SECONDS
    request.session.pop('pending_otp_attempts', None)

    try:
        _send_otp_email(email, otp, name)
        messages.info(request, f'A new verification code has been sent to {email}.')
    except Exception as e:
        print(f"[ERROR] Resending OTP email: {e}")
        messages.error(request, 'Could not resend the verification email. Please try again.')

    return redirect('verify_otp')


def logout_view(request):
    logout(request)
    messages.info(request, 'You have logged out. See you tomorrow, protagonist.')
    return redirect('login')


def forgot_password_view(request):
    if request.user.is_authenticated:
        return redirect('reports_home')

    form = ForgotPasswordForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']
        User = get_user_model()
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            # Form validation already checks this, but the account could
            # theoretically vanish in between — fail gracefully, not a 500.
            messages.error(request, 'No account found with this email.')
            return render(request, 'users/forgot_password.html', {'form': form})

        otp = f'{random.randint(0, 999999):06d}'
        request.session['reset_email'] = email
        request.session['reset_otp'] = otp
        request.session['reset_otp_expiry'] = time.time() + OTP_VALID_SECONDS
        request.session.pop('reset_otp_attempts', None)

        try:
            _send_reset_otp_email(email, otp, user.get_display_name())
        except Exception as e:
            print(f"[ERROR] Sending reset OTP email: {e}")
            messages.error(request, 'Could not send the reset email. Please try again.')
            return render(request, 'users/forgot_password.html', {'form': form})

        messages.info(request, f'We sent a password reset code to {email}.')
        return redirect('reset_password')

    return render(request, 'users/forgot_password.html', {'form': form})


def reset_password_view(request):
    email = request.session.get('reset_email')
    if not email:
        return redirect('forgot_password')

    form = ResetPasswordForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        entered_otp = form.cleaned_data['otp']
        result = _check_otp(request, entered_otp, 'reset_otp', 'reset_otp_expiry', 'reset_otp_attempts')

        if result == 'expired':
            messages.error(request, 'That code has expired. Please request a new one.')
        elif result == 'locked':
            messages.error(request, 'Too many incorrect attempts. Please request a new code.')
        elif result == 'wrong':
            messages.error(request, 'Incorrect code. Please check your email and try again.')
        else:  # 'ok'
            User = get_user_model()
            user = User.objects.filter(email__iexact=email).first()
            if user is None:
                # Rare: account was deleted between requesting the reset
                # and submitting this form. Fail gracefully, not a 500.
                for key in ('reset_email', 'reset_otp', 'reset_otp_expiry', 'reset_otp_attempts'):
                    request.session.pop(key, None)
                messages.error(request, 'That account no longer exists.')
                return redirect('forgot_password')

            user.set_password(form.cleaned_data['new_password1'])
            user.save()

            for key in ('reset_email', 'reset_otp', 'reset_otp_expiry', 'reset_otp_attempts'):
                request.session.pop(key, None)

            messages.success(request, 'Password reset successful! Please log in with your new password.')
            return redirect('login')

    return render(request, 'users/reset_password.html', {'form': form, 'email': email})


def resend_reset_otp_view(request):
    email = request.session.get('reset_email')
    if not email:
        return redirect('forgot_password')

    User = get_user_model()
    user = User.objects.filter(email__iexact=email).first()
    otp = f'{random.randint(0, 999999):06d}'
    request.session['reset_otp'] = otp
    request.session['reset_otp_expiry'] = time.time() + OTP_VALID_SECONDS
    request.session.pop('reset_otp_attempts', None)

    try:
        _send_reset_otp_email(email, otp, user.get_display_name() if user else '')
        messages.info(request, f'A new reset code has been sent to {email}.')
    except Exception as e:
        print(f"[ERROR] Resending reset OTP email: {e}")
        messages.error(request, 'Could not resend the reset email. Please try again.')

    return redirect('reset_password')


# ─── ✅ FIREBASE LOGIN VIEW (JSON) ──────────────────────────────────────────
def firebase_login_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        id_token = data.get('idToken')
    except:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if not id_token:
        return JsonResponse({'error': 'Missing idToken'}, status=400)

    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
        from django.conf import settings

        decoded = google_id_token.verify_firebase_token(
            id_token,
            google_requests.Request(),
            audience=settings.FIREBASE_PROJECT_ID,
        )
        if decoded is None:
            return JsonResponse({'error': 'Invalid token'}, status=401)

        email = decoded.get('email')
        name = decoded.get('name', '')
        if not email:
            return JsonResponse({'error': 'No email in token'}, status=400)

        User = get_user_model()
        user = User.objects.filter(email=email).first()

        if user is None:
            request.session['pending_google_email'] = email
            request.session['pending_google_name'] = name
            return JsonResponse({'success': True, 'redirect': '/users/complete-profile/', 'new_user': True})

        if not user.is_active:
            user.is_active = True
            user.save()

        login(request, user)
        request.session.save()

        print(f"[DEBUG] User {email} logged in. Session key: {request.session.session_key}")

        return JsonResponse({'success': True, 'redirect': '/reports/'})

    except ValueError as e:
        print(f"[ERROR] Token verification: {e}")
        return JsonResponse({'error': f'Token verification failed: {e}'}, status=401)
    except Exception as e:
        print(f"[ERROR] Firebase login: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# ─── DEBUG SESSION VIEW ──────────────────────────────────────────────────────
def debug_session_view(request):
    return JsonResponse({
        'is_authenticated': request.user.is_authenticated,
        'username': request.user.username if request.user.is_authenticated else None,
        'session_key': request.session.session_key,
    })


# ── Profile Views ────────────────────────────────────────────────────────────

@login_required
def profile_view(request):
    user = request.user
    today = timezone.localdate()

    if request.method == 'POST':
        action = request.POST.get('action', 'update_info')
        if action == 'update_info':
            form = ProfileForm(request.POST, request.FILES, instance=user)
            if form.is_valid():
                form.save()
                messages.success(request, 'Profile updated!')
            else:
                messages.error(request, 'Please fix the errors below.')
            return redirect('profile')
        elif action == 'change_password':
            old_pw = request.POST.get('old_password', '')
            new_pw1 = request.POST.get('new_password1', '')
            new_pw2 = request.POST.get('new_password2', '')
            if not user.check_password(old_pw):
                messages.error(request, 'Current password is incorrect.')
            elif new_pw1 != new_pw2:
                messages.error(request, 'New passwords do not match.')
            else:
                try:
                    validate_password(new_pw1, user=user)
                except DjangoValidationError as e:
                    messages.error(request, ' '.join(e.messages))
                else:
                    user.set_password(new_pw1)
                    user.save()
                    update_session_auth_hash(request, user)
                    messages.success(request, 'Password changed successfully!')
            return redirect('profile')

    from tasks.models import DailyLog, Task

    all_logs = DailyLog.objects.filter(user=user)
    win_days = all_logs.filter(day_status='win').count()
    survive_days = all_logs.filter(day_status='survive').count()
    lose_days = all_logs.filter(day_status='lose').count()
    tasks_completed = Task.objects.filter(user=user, status='completed').count()
    streak_list = list(all_logs.order_by('date').values_list('streak', flat=True))
    max_streak = max(streak_list) if streak_list else 0
    cur_streak = streak_list[-1] if streak_list else 0
    user._survive_days = survive_days

    badges = get_badges(user, win_days, tasks_completed, max_streak)
    badges_unlocked = sum(1 for b in badges if b['unlocked'])

    # In case a badge unlocked from something that doesn't already run the
    # achievements check (e.g. a diet-profile setup elsewhere) — this is a
    # harmless no-op if nothing new unlocked since the last check.
    from .achievements import check_and_queue_achievement_popup
    check_and_queue_achievement_popup(user, request)

    cur_level = user.current_level_data()
    nxt_level = user.next_level_data()
    xp_pct = user.xp_progress_pct()
    xp_to_next = user.xp_to_next_level()

    titles = {1: 'Novice Warrior', 2: 'Iron Warrior', 3: 'Steel Warrior', 4: 'Elite Warrior', 5: 'Legendary Warrior'}
    character_title = titles.get(user.level, f'Level {user.level} Warrior')

    week_start = today - timedelta(days=today.weekday())
    week_tasks = Task.objects.filter(user=user, due_date__gte=week_start, due_date__lte=today)
    week_total = week_tasks.count()
    week_done = week_tasks.filter(status='completed').count()
    weekly_goal_pct = round(week_done / week_total * 100) if week_total else 0

    from home.models import JournalEntry
    # Multiple entries per day are now allowed — order explicitly
    # (most recent day first, most recent time within that day first)
    # instead of relying on the model's implicit Meta.ordering.
    journal_entries = JournalEntry.objects.filter(user=user).order_by('-date', '-created_at')[:20]

    context = {
        'form': ProfileForm(instance=user),
        'cur_level': cur_level,
        'nxt_level': nxt_level,
        'xp_pct': xp_pct,
        'xp_to_next': xp_to_next,
        'win_days': win_days,
        'survive_days': survive_days,
        'lose_days': lose_days,
        'tasks_completed': tasks_completed,
        'cur_streak': cur_streak,
        'max_streak': max_streak,
        'badges': badges,
        'badges_unlocked': badges_unlocked,
        'badges_total': len(badges),
        'character_title': character_title,
        'weekly_goal_pct': weekly_goal_pct,
        'journal_entries': journal_entries,
    }
    return render(request, 'users/profile.html', context)


@login_required
def edit_profile(request):
    return redirect('profile')


@login_required
def delete_account(request):
    if request.method == 'POST':
        password = request.POST.get('confirm_password', '')
        user = request.user
        if user.check_password(password):
            logout(request)
            user.delete()
            messages.success(request, 'Account deleted. Goodbye, Warrior. 💀')
            return redirect('login')
        else:
            messages.error(request, '❌ Incorrect password. Account not deleted.')
            return redirect('profile')
    return redirect('profile')

@require_POST
def set_timezone(request):
    """
    Called by tz-detect.js (see base.html) with the browser's IANA timezone
    name. Saves it on the logged-in user's profile (so backend logic —
    streaks, daily resets, deadlines — uses it via UserTimezoneMiddleware),
    and always sets a `tz` cookie too, so anonymous users and the very first
    page load before login also get correct local-time display.
    """
    tz_name = request.POST.get("tz", "").strip()
 
    try:
        zoneinfo.ZoneInfo(tz_name)  # validates it's a real IANA name
    except Exception:
        return JsonResponse({"ok": False, "error": "invalid timezone"}, status=400)
 
    if request.user.is_authenticated and request.user.timezone != tz_name:
        request.user.timezone = tz_name
        request.user.save(update_fields=["timezone"])
 
    response = JsonResponse({"ok": True, "tz": tz_name})
    response.set_cookie("tz", tz_name, max_age=60 * 60 * 24 * 365, samesite="Lax")
    return response