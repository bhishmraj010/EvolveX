import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.http import HttpResponse

from .models import JournalEntry

logger = logging.getLogger(__name__)


def home_view(request):
    """Root '/' — the cinematic AI-OS Home hub. Also loads the user's
    recent journal entries (most recent first) for the right-side panel,
    plus today's entries specifically. Multiple entries per day are
    allowed, so 'todays_entries' is a list, most recent first — the
    textarea itself always starts empty."""
    from subscriptions.plans import PROMO_DEADLINE, promo_is_active

    journal_entries = []
    todays_entries = []
    if request.user.is_authenticated:
        journal_entries = list(
            JournalEntry.objects.filter(user=request.user).order_by("-date", "-created_at")[:10]
        )
        today = timezone.localdate()
        todays_entries = [e for e in journal_entries if e.date == today]

    return render(request, 'home_hub.html', {
        'promo_deadline_iso': PROMO_DEADLINE.isoformat(),
        'promo_active': promo_is_active(),
        'journal_entries': journal_entries,
        'todays_entries': todays_entries,
        # kept for any template still referencing the old single-entry name
        'todays_entry': todays_entries[0] if todays_entries else None,
    })


def _build_journal_prompt(entry_text, past_entries):
    """past_entries: iterable of JournalEntry, most-recent-first."""
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
    """Creates a new journal entry — multiple per day are allowed, each
    submission is its own row, most recent shown first — then asks Gemini
    for a short reflection + suggestions. The entry saves even if the AI
    call fails — the AI fields just stay empty in that case."""
    entry_text = request.POST.get('entry_text', '').strip()
    if not entry_text:
        messages.error(request, "Write something before updating the journal.")
        return redirect('home')

    today = timezone.localdate()
    past_entries = list(
        JournalEntry.objects.filter(user=request.user).order_by('-date', '-created_at')[:5]
    )

    reflection, suggestions, mood_tag = _get_ai_reflection(entry_text, past_entries)

    JournalEntry.objects.create(
        user=request.user,
        date=today,
        entry_text=entry_text,
        ai_response=reflection,
        ai_suggestions=suggestions,
        ai_mood_tag=mood_tag,
        ai_generated_at=timezone.now() if reflection else None,
    )

    if reflection:
        messages.success(request, "Journal entry added — check the panel for today's reflection.")
    else:
        messages.success(request, "Journal entry added.")

    return redirect('home')


def about_view(request):
    """Static 'About' page."""
    return render(request, 'home/about.html')


def contact_view(request):
    """Static 'Contact' page."""
    return render(request, 'home/contact.html')


def blog_list_view(request):
    """Blog listing page."""
    return render(request, 'home/blog_list.html')

def robots_txt_view(request):
    """Serves a basic robots.txt."""
    content = (
        "User-agent: *\n"
        "Allow: /\n"
    )
    return HttpResponse(content, content_type="text/plain")

def sitemap_xml_view(request):
    """Serves a basic sitemap.xml."""
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        '</urlset>\n'
    )
    return HttpResponse(content, content_type="application/xml")