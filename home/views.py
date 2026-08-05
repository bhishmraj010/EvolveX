import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import JournalEntry

logger = logging.getLogger(__name__)


def home_view(request):
    """Root '/' — the cinematic AI-OS Home hub. Also loads the user's
    recent journal entries (most recent first) for the right-side panel."""
    from subscriptions.plans import PROMO_DEADLINE, promo_is_active

    journal_entries = []
    if request.user.is_authenticated:
        journal_entries = list(
            JournalEntry.objects.filter(user=request.user).order_by("-date")[:10]
        )

    return render(request, 'home_hub.html', {
        'promo_deadline_iso': PROMO_DEADLINE.isoformat(),
        'promo_active': promo_is_active(),
        'journal_entries': journal_entries,
    })


def _build_journal_prompt(entry_text, past_entries):
    """past_entries: iterable of JournalEntry, most-recent-first, EXCLUDING today."""
    if past_entries:
        history = "\n".join(f"- {e.date}: {e.entry_text[:200]}" for e in past_entries)
    else:
        history = "No previous entries — this is their first."

    return f"""You are a sharp, encouraging AI life coach embedded in EvolveX, a gamified
self-improvement app. The user just wrote a short journal entry describing how
they're doing right now.

TODAY'S ENTRY:
\"\"\"{entry_text}\"\"\"

RECENT PAST ENTRIES (most recent first — for spotting patterns, do not repeat
them back verbatim):
{history}

Read today's entry carefully (and the pattern across past entries, if any)
and respond with a JSON object with exactly these fields:
- reflection: (string, 2-3 sentences) A warm but honest reflection on what
  they wrote. Acknowledge how they're actually feeling — don't just restate it.
- suggestions: (list of 3-5 short strings) Specific, actionable next steps
  tailored to what they described, ranked by usefulness.
- mood_tag: (string, 1-2 words) Their current state, e.g. "Motivated",
  "Burnt Out", "Steady Progress", "Overwhelmed".

Return ONLY a valid JSON object. No markdown, no extra text, no code fences.
"""


def _get_ai_reflection(entry_text, past_entries):
    """Best-effort Gemini call — never raises; caller always gets a
    (reflection, suggestions, mood_tag) tuple, empty on any failure."""
    try:
        from life_simulation.gemini_client import generate_json_with_usage
        prompt = _build_journal_prompt(entry_text, past_entries)
        raw, _pt, _ct = generate_json_with_usage(prompt)
        if not raw:
            return "", [], ""
        reflection = str(raw.get("reflection", "")).strip()
        suggestions = raw.get("suggestions", []) or []
        if not isinstance(suggestions, list):
            suggestions = []
        mood_tag = str(raw.get("mood_tag", "")).strip()
        return reflection, suggestions[:5], mood_tag
    except Exception:
        logger.exception("Journal AI reflection failed")
        return "", [], ""


@login_required
@require_POST
def journal_save_view(request):
    """Saves (or updates) today's journal entry, then asks Gemini for a
    short reflection + suggestions. The entry saves even if the AI call
    fails — the AI fields just stay empty in that case."""
    entry_text = request.POST.get('entry_text', '').strip()
    if not entry_text:
        messages.error(request, "Write something before updating the journal.")
        return redirect('home')

    today = timezone.localdate()
    past_entries = list(
        JournalEntry.objects.filter(user=request.user).exclude(date=today).order_by('-date')[:5]
    )

    reflection, suggestions, mood_tag = _get_ai_reflection(entry_text, past_entries)

    JournalEntry.objects.update_or_create(
        user=request.user, date=today,
        defaults={
            'entry_text': entry_text,
            'ai_response': reflection,
            'ai_suggestions': suggestions,
            'ai_mood_tag': mood_tag,
            'ai_generated_at': timezone.now() if reflection else None,
        },
    )

    if reflection:
        messages.success(request, "Journal updated — check the panel for today's reflection.")
    else:
        messages.success(request, "Journal updated.")

    return redirect('home')


# ── Footer pages ─────────────────────────────────────────────────────────

def about_view(request):
    return render(request, 'home/about.html')


def contact_view(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        message = request.POST.get('message', '').strip()

        if not (name and email and message):
            messages.error(request, "Please fill in every field before sending.")
        else:
            try:
                from django.core.mail import send_mail
                support_to = getattr(settings, 'EMAIL_HOST_USER', None) or 'support@evolvex.local'
                send_mail(
                    subject=f"[EvolveX Contact] {name}",
                    message=f"From: {name} <{email}>\n\n{message}",
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'noreply@evolvex.local',
                    recipient_list=[support_to],
                    fail_silently=False,
                )
                messages.success(request, "Message sent — we'll get back to you soon.")
                return redirect('contact')
            except Exception:
                logger.exception("Contact form email failed")
                messages.error(request, "Couldn't send your message right now — please try again in a bit.")

    return render(request, 'home/contact.html')


def blog_list_view(request):
    return render(request, 'home/blog_list.html')


# ── SEO: robots.txt + sitemap.xml ───────────────────────────────────────
# Plain hand-rolled views (no django.contrib.sitemaps needed) — simplest
# path since this list only has a handful of public, unauthenticated URLs.
# Add a new <url> block here whenever a new PUBLIC page is added; nothing
# behind @login_required belongs in a sitemap (Google shouldn't index
# pages it can't actually reach).

from django.http import HttpResponse
from django.urls import reverse

SITE_DOMAIN = "https://life-simulation-9bqz.onrender.com"


def robots_txt_view(request):
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /users/",
        "Disallow: /dashboard/",
        "Disallow: /tracker/",
        "Disallow: /reports/",
        "Disallow: /diet/",
        "Disallow: /analyzer/",
        "Disallow: /roadmap/",
        "Disallow: /subscriptions/razorpay/",
        "Disallow: /subscriptions/paypal/",
        "Disallow: /admin/",
        "Disallow: /home/journal/",
        f"Sitemap: {SITE_DOMAIN}/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


def sitemap_xml_view(request):
    # (url_name, changefreq, priority) — only PUBLIC, unauthenticated pages.
    public_pages = [
        ("home", "daily", "1.0"),
        ("about", "monthly", "0.6"),
        ("contact", "monthly", "0.5"),
        ("blog_list", "weekly", "0.7"),
        ("pricing", "weekly", "0.8"),
        ("login", "yearly", "0.3"),
        ("register", "yearly", "0.4"),
    ]
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for name, freq, priority in public_pages:
        try:
            url = SITE_DOMAIN + reverse(name)
        except Exception:
            continue
        xml.append(
            f"  <url><loc>{url}</loc><changefreq>{freq}</changefreq><priority>{priority}</priority></url>"
        )
    xml.append("</urlset>")
    return HttpResponse("\n".join(xml), content_type="application/xml")