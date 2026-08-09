"""
AI Roadmap engine.

Generates a complete, personalized learning roadmap (phases + checkpoints +
resources + predictions) for ANY goal, and generates adaptive daily missions
day by day. Uses the shared Gemini client (life_simulation.gemini_client) —
same stack as analyzer/diet — and Pydantic for response validation, mirroring
analyzer/gemini_service.py's pattern.
"""
from datetime import timedelta, datetime
import logging

from django.utils import timezone
from pydantic import BaseModel, Field, ValidationError, conint

from life_simulation.gemini_client import generate_json_with_usage
from .models import Roadmap, RoadmapPhase, RoadmapCheckpoint, RoadmapResource, DailyMission, PhaseTest

logger = logging.getLogger(__name__)

MIN_PHASES = 5
MAX_PHASES = 10


def _phase_budget(total_days):
    """
    Returns (min_phases, max_phases) sized to how many days the learner
    actually gave us — NOT a fixed 5-10 regardless of timeframe. A 7-day
    goal doesn't need the same phase count as a 6-month one; forcing 5-10
    phases onto a short deadline is what was making short roadmaps feel
    bloated/overcomplicated.

    total_days=None means the learner gave no deadline — fall back to the
    original unconstrained 5-10 range and let the AI use its judgement.
    """
    if not total_days or total_days <= 0:
        return MIN_PHASES, MAX_PHASES
    if total_days <= 7:
        return 2, 3
    if total_days <= 14:
        return 3, 4
    if total_days <= 30:
        return 4, 6
    if total_days <= 60:
        return 5, 8
    return MIN_PHASES, MAX_PHASES


def _roadmap_total_days(roadmap):
    """Days between today and the learner's target_deadline, or None if no
    deadline was set (open-ended roadmap)."""
    if not roadmap.target_deadline:
        return None
    days = (roadmap.target_deadline - timezone.now().date()).days
    return days if days > 0 else None


# ---------- Pydantic response schemas ----------
class ClarifyingQuestionSchema(BaseModel):
    question: str


class ClarifyingQuestionsResponse(BaseModel):
    questions: list[ClarifyingQuestionSchema] = Field(default_factory=list)


class PhaseTestQuestionSchema(BaseModel):
    type: str  # "mcq" | "text" | "code"
    question: str
    marks: conint(ge=1, le=50)
    options: list[str] = Field(default_factory=list)   # mcq only
    correct_option: int | None = None                    # mcq only (index)
    rubric: str = ""                                     # text/code only — hidden from learner
    topic: str = ""


class PhaseTestResponse(BaseModel):
    questions: list[PhaseTestQuestionSchema]


class GradedAnswerSchema(BaseModel):
    id: str
    awarded_marks: conint(ge=0)
    feedback: str


class GradingResponse(BaseModel):
    grades: list[GradedAnswerSchema] = Field(default_factory=list)


class RemedialPhaseResponse(BaseModel):
    title: str
    objectives: list[str]
    duration_days: conint(ge=2, le=14)
    completion_criteria: str = ""


class PhaseSchema(BaseModel):
    title: str
    objectives: list[str] = Field(default_factory=list)
    duration_days: conint(ge=1, le=120)
    difficulty: str
    xp_reward: conint(ge=10, le=1000)
    completion_criteria: str
    checkpoint_title: str
    checkpoint_description: str = ""


class ResourceSchema(BaseModel):
    phase_index: int = -1  # -1 = general / not phase-specific
    resource_type: str = "article"
    title: str
    url: str = ""
    is_free: bool = True
    note: str = ""


class RoadmapGenerationResponse(BaseModel):
    phases: list[PhaseSchema]
    resources: list[ResourceSchema] = Field(default_factory=list)
    predicted_completion_date: str  # YYYY-MM-DD
    success_probability: conint(ge=0, le=100)
    learning_speed: str = "steady"
    consistency_score: conint(ge=0, le=100) = 50
    what_to_learn_next: list[str] = Field(default_factory=list)
    what_to_skip: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    common_mistakes: list[str] = Field(default_factory=list)
    learning_hacks: list[str] = Field(default_factory=list)


class MissionTaskSchema(BaseModel):
    id: str  # "learning" | "practice" | "revision" | "challenge"
    type: str
    title: str
    description: str = ""
    minutes: conint(ge=5, le=240)


class DailyMissionResponse(BaseModel):
    tasks: list[MissionTaskSchema]
    xp_reward: conint(ge=5, le=200) = 20
    adaptive_note: str = ""


XP_PER_TASK = 5  # every mission sub-task is worth a flat 5 XP — total mission
                  # XP is always task_count * XP_PER_TASK, never AI-decided


# ---------- Prompt construction ----------
def _difficulty_label(level):
    return dict(Roadmap.SKILL_LEVELS).get(level, level)


def _build_clarifying_questions_prompt(draft):
    deadline_str = draft.target_deadline.isoformat() if draft.target_deadline else "no fixed deadline"
    return f"""You are a Senior Learning Architect for EvolveX, a gamified self-improvement
platform. A learner just submitted this goal to generate a personalized roadmap for:

GOAL: {draft.goal}
Current skill level: {draft.current_skill_level}
Daily available time: {draft.daily_minutes} minutes
Target deadline: {deadline_str}
Learning preference: {draft.learning_preference}
Existing skills: {draft.existing_skills or "none stated"}
Preferred language: {draft.preferred_language}
Budget: {draft.budget}

Many goals as typed are AMBIGUOUS in a way that would make you silently pick a specific
tech stack/tool/scope the learner didn't ask for. Example: "Full Stack Developer" could mean
MERN, Django+React, Java+Angular, etc — guessing wrong wastes the learner's time. "Learn
Python" is more specific but could still mean general-purpose scripting vs. Django web dev vs.
data science — ask if genuinely unclear.

Decide if this goal needs disambiguation. If yes, write UP TO 5 short, specific questions
(fewer if 5 aren't needed) whose answers would meaningfully change what phases/tools the
roadmap includes. Do NOT ask about anything already answered above (skill level, daily time,
deadline, preference, budget). Do NOT ask generic motivational questions — only ask things
that change the roadmap's actual content (e.g. "Which stack do you want: MERN or
Django+React?", "Is this for web apps, mobile apps, or both?", "Frontend-only or
full-stack?").

If the goal is ALREADY fully specific and unambiguous (e.g. "Learn Django REST Framework for
building APIs"), return an empty questions list — do not invent unnecessary questions.

Return ONLY a valid JSON object: {{"questions": [{{"question": "..."}}, ...]}} — max 5 items.
No markdown, no extra text, JSON only."""


def _build_roadmap_prompt(roadmap, carry_forward_note=""):
    deadline_str = roadmap.target_deadline.isoformat() if roadmap.target_deadline else "no fixed deadline"
    total_days = _roadmap_total_days(roadmap)
    min_phases, max_phases = _phase_budget(total_days)

    if total_days:
        duration_instruction = (
            f"The learner gave a target deadline that is exactly {total_days} days away. "
            f"Break the goal into {min_phases}-{max_phases} logical, ordered phases — keep it "
            f"SIMPLE and proportional to a {total_days}-day timeframe, don't over-engineer it. "
            f"The duration_days of every phase, ADDED TOGETHER, MUST sum to exactly {total_days} "
            f"days — not more, not less. Do not pad with extra phases or extra days just to fill "
            f"a template; a short deadline should produce a short, focused roadmap."
        )
    else:
        duration_instruction = (
            f"No fixed deadline was given. Break the goal into {min_phases}-{max_phases} logical, "
            f"ordered phases sized realistically for {roadmap.daily_minutes} min/day."
        )

    return f"""You are a Senior Product Designer, AI Engineer, and Learning Scientist building the
AI Roadmap engine for EvolveX, a gamified self-improvement platform. Generate a COMPLETE,
personalized learning roadmap from scratch for the goal below. Think Duolingo skill trees +
Coursera Learning Paths + GitHub Skills — not a plain task list.

GOAL: {roadmap.goal}
Current skill level: {_difficulty_label(roadmap.current_skill_level)}
Daily available time: {roadmap.daily_minutes} minutes
Target deadline: {deadline_str}
Learning preference: {roadmap.get_learning_preference_display()}
Existing skills: {roadmap.existing_skills or "none stated"}
Preferred language: {roadmap.preferred_language}
Budget: {roadmap.get_budget_display()}
{carry_forward_note}

{duration_instruction}
Each phase must build on the previous one and end with a checkpoint the learner
must clear before unlocking the next phase.

Also recommend learning resources (YouTube channels, official documentation, books, courses,
articles, practice websites). Prefer FREE resources when budget is "free" or "mixed". Attach each
resource to a phase_index (0-based, matching phase order) or use -1 for general resources.

Return ONLY a valid JSON object with this exact shape:
- phases: list of objects, each with:
  - title (string)
  - objectives (list of strings — concrete learning objectives for this phase)
  - duration_days (int — realistic given {roadmap.daily_minutes} min/day)
  - difficulty ("beginner" | "intermediate" | "advanced" | "expert")
  - xp_reward (int 10-1000, harder/longer phases worth more)
  - completion_criteria (string — how to know the phase is truly done)
  - checkpoint_title (string — short name for the end-of-phase checkpoint/quiz/milestone)
  - checkpoint_description (string)
- resources: list of objects, each with phase_index, resource_type
  ("youtube"|"documentation"|"book"|"course"|"article"|"practice"), title, url, is_free, note
- predicted_completion_date (string, YYYY-MM-DD — realistic estimate given pace and deadline)
- success_probability (int 0-100 — likelihood of finishing on time at this pace)
- learning_speed ("slow" | "steady" | "fast" — relative to the stated deadline)
- consistency_score (int 0-100 — a fair starting estimate; 50 if no history)
- what_to_learn_next (list of strings — 2-4 concrete next steps to start today)
- what_to_skip (list of strings — commonly-taught things that are NOT essential for this goal)
- prerequisites (list of strings — anything the learner should already know or quickly pick up)
- common_mistakes (list of strings — mistakes beginners make pursuing this exact goal)
- learning_hacks (list of strings — specific tactics to learn this faster)

No markdown, no extra text, JSON only."""


def _build_daily_mission_prompt(roadmap, phase, adaptive_ctx, target_date):
    pace_note = {
        "ahead": (
            "The learner is AHEAD of schedule (finishing tasks early / high completion rate). "
            "Generate a HARDER mission today — stretch objectives, a mini project step, or a "
            "tougher challenge than usual."
        ),
        "behind": (
            "The learner has been SKIPPING or falling behind. Generate a RECOVERY mission: "
            "shorter, lower-friction, focused on rebuilding momentum and re-covering the most "
            "recently missed concept rather than piling on new material."
        ),
        "struggling": (
            "The learner is struggling (low completion rate even when attempting tasks). SLOW "
            "DOWN the roadmap: re-teach the current concept with a different angle/example "
            "before introducing anything new."
        ),
        "steady": "The learner is on pace. Generate a normal, well-paced mission.",
    }[adaptive_ctx["state"]]

    return f"""You are the AI Roadmap engine for EvolveX. Generate TODAY's missions for a learner
working toward: "{roadmap.goal}" (overall preference: {roadmap.get_learning_preference_display()},
{roadmap.daily_minutes} minutes/day available, language: {roadmap.preferred_language}).

Current phase: "{phase.title}" (difficulty: {phase.difficulty})
Phase objectives: {", ".join(phase.objectives) if phase.objectives else "n/a"}
Phase completion criteria: {phase.completion_criteria}
Today's date: {target_date.isoformat()}

ADAPTIVE CONTEXT: {pace_note}
Recent stats: {adaptive_ctx["completed_last_7"]}/{adaptive_ctx["total_last_7"]} missions completed in
the last 7 days, current streak {adaptive_ctx["streak"]} days.

Generate exactly 4 tasks for today, each mapped to one of these ids/types:
- id "learning", type "learning": core concept to learn today
- id "practice", type "practice": hands-on practice/exercise applying it
- id "revision", type "revision": quick revision of a recent concept
- id "challenge", type "challenge": a mini challenge/quiz to test understanding

Each task needs: id, type, title (short, action-oriented), description (1-2 sentences, specific
— not generic), minutes (realistic, total across all 4 tasks should be close to but not exceed
{roadmap.daily_minutes} minutes).

Return ONLY a valid JSON object:
- tasks: list of the 4 task objects above
- xp_reward (int 5-200 — total XP for completing all of today's tasks; scale with difficulty/effort)
- adaptive_note (string, <=15 words — shown to the user, e.g. "Harder challenge — you're ahead!" or
  "Lighter day — let's rebuild momentum." Empty string if pace is steady.)

No markdown, no extra text, JSON only."""


# ---------- Gemini callers ----------
def _call_gemini(prompt, schema_cls):
    raw, pt, ct = generate_json_with_usage(prompt)
    if raw is None:
        return None, pt, ct
    try:
        validated = schema_cls(**raw)
        return validated.model_dump(), pt, ct
    except ValidationError as e:
        logger.error(f"AI Roadmap: Gemini response validation failed: {e}")
        return None, pt, ct


# ---------- Public API: pre-generation clarifying questions ----------
def generate_clarifying_questions(draft):
    """
    Ask the AI whether `draft.goal` is ambiguous, and if so, up to 5 short
    questions to disambiguate it BEFORE we spend a full roadmap-generation
    call. Returns a list[str] of questions (possibly empty).
    """
    prompt = _build_clarifying_questions_prompt(draft)
    result, pt, ct = _call_gemini(prompt, ClarifyingQuestionsResponse)
    if result is None:
        return []
    return [q["question"] for q in result["questions"][:5]]


# ---------- Public API: full roadmap generation ----------
def _rescale_phase_durations(phases_data, total_days):
    """
    Server-side safety net: even with the prompt constraint above, the AI can
    still return a duration total that doesn't match the learner's deadline.
    If it's off, proportionally rescale every phase's duration_days so the
    roadmap always adds up to exactly what the learner asked for, instead of
    silently running longer (or shorter) than their chosen timeframe.
    """
    if not total_days or not phases_data:
        return phases_data

    current_total = sum(p["duration_days"] for p in phases_data)
    if current_total == 0 or current_total == total_days:
        return phases_data

    ratio = total_days / current_total
    running = 0
    for i, p in enumerate(phases_data):
        if i == len(phases_data) - 1:
            # last phase absorbs any rounding remainder so the sum is exact
            p["duration_days"] = max(1, total_days - running)
        else:
            scaled = max(1, round(p["duration_days"] * ratio))
            p["duration_days"] = scaled
            running += scaled
    return phases_data


def generate_roadmap(roadmap, carry_forward_note=""):
    """
    Populate `roadmap` (already saved, no phases yet) with AI-generated
    phases, checkpoints, resources, and predictions. Returns True on success.
    On failure, marks roadmap.generation_failed and leaves it phase-less so
    the view can show a retry option.
    """
    total_days = _roadmap_total_days(roadmap)
    _, max_phases_for_this_roadmap = _phase_budget(total_days)

    prompt = _build_roadmap_prompt(roadmap, carry_forward_note)
    result, pt, ct = _call_gemini(prompt, RoadmapGenerationResponse)

    roadmap.prompt_tokens = pt
    roadmap.completion_tokens = ct

    if result is None:
        roadmap.generation_failed = True
        roadmap.save(update_fields=["prompt_tokens", "completion_tokens", "generation_failed"])
        return False

    phases_data = result["phases"][:max_phases_for_this_roadmap] or []
    phases_data = _rescale_phase_durations(phases_data, total_days)
    created_phases = []
    for i, p in enumerate(phases_data):
        phase = RoadmapPhase.objects.create(
            roadmap=roadmap,
            order=i,
            title=p["title"],
            objectives=p["objectives"],
            duration_days=p["duration_days"],
            difficulty=p["difficulty"] if p["difficulty"] in dict(RoadmapPhase.DIFFICULTY_CHOICES) else "beginner",
            xp_reward=p["xp_reward"],
            completion_criteria=p["completion_criteria"],
            status="active" if i == 0 else "locked",
        )
        RoadmapCheckpoint.objects.create(
            phase=phase,
            title=p["checkpoint_title"],
            description=p.get("checkpoint_description", ""),
            xp_reward=max(20, p["xp_reward"] // 4),
        )
        created_phases.append(phase)

    for r in result.get("resources", []):
        phase_obj = None
        if 0 <= r.get("phase_index", -1) < len(created_phases):
            phase_obj = created_phases[r["phase_index"]]
        rtype = r["resource_type"] if r["resource_type"] in dict(RoadmapResource.RESOURCE_TYPES) else "article"
        RoadmapResource.objects.create(
            roadmap=roadmap,
            phase=phase_obj,
            resource_type=rtype,
            title=r["title"],
            url=r.get("url", ""),
            is_free=r.get("is_free", True),
            note=r.get("note", ""),
        )

    try:
        roadmap.predicted_completion_date = datetime.strptime(
            result["predicted_completion_date"], "%Y-%m-%d"
        ).date()
    except (ValueError, TypeError):
        roadmap.predicted_completion_date = None

    roadmap.success_probability = result["success_probability"]
    roadmap.learning_speed = result["learning_speed"] if result["learning_speed"] in dict(Roadmap.LEARNING_SPEED_CHOICES) else "steady"
    roadmap.consistency_score = result["consistency_score"]
    roadmap.what_to_learn_next = result["what_to_learn_next"]
    roadmap.what_to_skip = result["what_to_skip"]
    roadmap.prerequisites = result["prerequisites"]
    roadmap.common_mistakes = result["common_mistakes"]
    roadmap.learning_hacks = result["learning_hacks"]
    roadmap.generation_failed = False
    roadmap.current_phase_index = 0
    roadmap.save()
    roadmap.recompute_progress()
    return True


# ---------- Adaptive context (drives point 5: Adaptive Roadmap) ----------
def _compute_adaptive_context(roadmap):
    since = timezone.localdate() - timedelta(days=7)
    recent = list(roadmap.daily_missions.filter(date__gte=since).order_by("date"))
    total_last_7 = len(recent)
    completed_last_7 = sum(1 for m in recent if m.status == "completed")
    skipped_last_7 = sum(1 for m in recent if m.status == "skipped")

    # streak: consecutive completed days ending today/yesterday
    streak = 0
    for m in sorted(roadmap.daily_missions.all(), key=lambda x: x.date, reverse=True):
        if m.status == "completed":
            streak += 1
        else:
            break

    if total_last_7 == 0:
        state = "steady"
    elif skipped_last_7 >= 3:
        state = "behind"
    elif total_last_7 >= 3 and completed_last_7 / total_last_7 < 0.4:
        state = "struggling"
    elif total_last_7 >= 3 and completed_last_7 / total_last_7 >= 0.9:
        state = "ahead"
    else:
        state = "steady"

    return {
        "state": state,
        "completed_last_7": completed_last_7,
        "total_last_7": total_last_7,
        "skipped_last_7": skipped_last_7,
        "streak": streak,
    }


def _phase_content_complete(phase):
    """True once the phase has logged at least `duration_days` completed
    missions. Past this point, no MORE days should be generated for this
    phase — the learner needs to clear the checkpoint to advance, not keep
    getting extra days manufactured."""
    return phase.daily_missions.filter(status="completed").count() >= phase.duration_days


def get_or_create_daily_mission(roadmap, target_date=None):
    """
    Lazily generate (and cache in the DB) the current mission for the
    roadmap's active phase. Progression is NOT tied to the real calendar —
    as soon as the learner finishes every task in the current mission, the
    next one (dated one day after the previous) generates immediately,
    instead of waiting for the real next day to arrive. `date` on the
    DailyMission row is still a real calendar date (for display / streaks),
    it's just chosen as "previous mission's date + 1", not "today".

    If `prefetch_next_mission()` already speculatively generated the next
    day in the background, this materializes it INSTANTLY from
    `phase.next_mission_cache` — no AI call, no wait — and only falls back
    to a live AI call if that cache is missing or stale.

    Returns (DailyMission or None, was_cached).
    """
    phase = roadmap.current_phase()
    if phase is None:
        return None, False

    if target_date is None:
        latest = phase.daily_missions.order_by("-date").first()
        if latest is None:
            target_date = timezone.localdate()
        elif latest.status != "completed":
            # Still-open mission for this phase — nothing new to generate yet.
            return latest, True
        elif _phase_content_complete(phase):
            # Enough days already logged for this phase — stop generating
            # more content. The learner needs to clear the checkpoint to
            # advance to the next phase, not get endless extra days.
            return latest, True
        else:
            target_date = latest.date + timedelta(days=1)

    existing = roadmap.daily_missions.filter(date=target_date, phase=phase).first()
    if existing:
        return existing, True

    # Was this exact day already pre-generated in the background? Use it
    # instantly instead of calling the AI again.
    cache = phase.next_mission_cache
    if cache and cache.get("date") == target_date.isoformat():
        mission = DailyMission.objects.create(
            roadmap=roadmap,
            phase=phase,
            date=target_date,
            tasks=cache["tasks"],
            estimated_minutes=cache["estimated_minutes"],
            xp_reward=len(cache["tasks"]) * XP_PER_TASK,
            was_adaptive=cache.get("was_adaptive", False),
            adaptive_note=cache.get("adaptive_note", ""),
        )
        phase.next_mission_cache = None
        phase.save(update_fields=["next_mission_cache"])
        return mission, False

    adaptive_ctx = _compute_adaptive_context(roadmap)
    prompt = _build_daily_mission_prompt(roadmap, phase, adaptive_ctx, target_date)
    result, pt, ct = _call_gemini(prompt, DailyMissionResponse)

    if result is None:
        return None, False

    total_minutes = sum(t["minutes"] for t in result["tasks"])
    mission = DailyMission.objects.create(
        roadmap=roadmap,
        phase=phase,
        date=target_date,
        tasks=[{**t, "completed": False} for t in result["tasks"]],
        estimated_minutes=total_minutes,
        xp_reward=len(result["tasks"]) * XP_PER_TASK,
        was_adaptive=adaptive_ctx["state"] != "steady",
        adaptive_note=result.get("adaptive_note", ""),
    )
    return mission, False


PREFETCH_COOLDOWN_SECONDS = 120  # after a failed prefetch (e.g. rate limit), wait this long before trying again


def check_next_mission_ready(roadmap):
    """
    Non-generating check used by the 'last task just completed' path: does
    the next mission already exist, or is a cached/in-flight prefetch about
    to produce it? Never calls the AI itself — just reports status so the
    caller can wait/poll instead of firing a duplicate concurrent call.
    Returns one of: ("ready", DailyMission), ("generating", None),
    ("none", None) — "none" means no prefetch is running and there's
    nothing cached, so the caller should fall back to a live generation.
    """
    phase = roadmap.current_phase()
    if phase is None:
        return "none", None

    latest = phase.daily_missions.order_by("-date").first()
    if latest is None or latest.status != "completed":
        return "none", None

    next_date = latest.date + timedelta(days=1)
    existing = roadmap.daily_missions.filter(date=next_date, phase=phase).first()
    if existing:
        return "ready", existing

    if phase.next_mission_generating:
        return "generating", None

    return "none", None


def prefetch_next_mission(roadmap):
    """
    Speculatively generate the mission for the day AFTER the current one —
    even though the current one isn't finished yet — and stash it on
    `phase.next_mission_cache` (NOT as a real DailyMission row, so it stays
    invisible/locked in the UI until the learner actually finishes today).
    Meant to be called from a background thread so it doesn't block a
    request. Safe to call repeatedly — no-ops if a fresh cache already
    exists or if there's nothing to prefetch yet.

    Throttled: if the last attempt failed (e.g. the AI API rate-limited us),
    we wait out PREFETCH_COOLDOWN_SECONDS before trying again, instead of
    re-firing on every single task toggle and burning through quota.
    """
    phase = roadmap.current_phase()
    if phase is None:
        return

    if _phase_content_complete(phase):
        return  # phase is done — wait for the checkpoint, don't manufacture more days

    current = phase.daily_missions.order_by("-date").first()
    if current is None:
        return  # nothing generated yet for this phase — nothing to prefetch ahead of

    next_date = current.date + timedelta(days=1)

    if roadmap.daily_missions.filter(date=next_date, phase=phase).exists():
        return  # already materialized (e.g. race with get_or_create_daily_mission)

    if phase.next_mission_cache and phase.next_mission_cache.get("date") == next_date.isoformat():
        return  # already prefetched and fresh

    if phase.next_mission_generating:
        return  # another prefetch is already in flight — don't fire a duplicate call

    if phase.next_mission_attempted_at:
        elapsed = (timezone.now() - phase.next_mission_attempted_at).total_seconds()
        if elapsed < PREFETCH_COOLDOWN_SECONDS:
            return  # a recent attempt already failed — sit out the cooldown

    # Mark that we're attempting now, BEFORE calling the API. If this call
    # fails too, the timestamp we just wrote is what makes the *next*
    # attempt wait out the cooldown instead of firing immediately again.
    phase.next_mission_attempted_at = timezone.now()
    phase.next_mission_generating = True
    phase.save(update_fields=["next_mission_attempted_at", "next_mission_generating"])

    try:
        adaptive_ctx = _compute_adaptive_context(roadmap)
        prompt = _build_daily_mission_prompt(roadmap, phase, adaptive_ctx, next_date)
        result, pt, ct = _call_gemini(prompt, DailyMissionResponse)
        if result is None:
            return  # failed — next call will respect the cooldown above

        total_minutes = sum(t["minutes"] for t in result["tasks"])
        phase.next_mission_cache = {
            "date": next_date.isoformat(),
            "tasks": [{**t, "completed": False} for t in result["tasks"]],
            "estimated_minutes": total_minutes,
            "xp_reward": result["xp_reward"],
            "was_adaptive": adaptive_ctx["state"] != "steady",
            "adaptive_note": result.get("adaptive_note", ""),
        }
        phase.next_mission_attempted_at = None  # success — clear so future cycles aren't throttled unnecessarily
        phase.save(update_fields=["next_mission_cache", "next_mission_attempted_at"])
    finally:
        phase.next_mission_generating = False
        phase.save(update_fields=["next_mission_generating"])


# ---------- Regeneration (point 8: Roadmap Regeneration) ----------
def regenerate_roadmap(old_roadmap, *, daily_minutes=None, target_deadline=None,
                        learning_preference=None, extra_notes=""):
    """
    "Regenerate Roadmap" — archives the old roadmap and creates a fresh v(n+1)
    that accounts for new available time / deadline / progress so far /
    new interests, per the spec's Roadmap Regeneration Logic.
    """
    completed_titles = [p.title for p in old_roadmap.phases.filter(status="completed")]
    carry_forward = (
        f"\nThis is a REGENERATION of an existing roadmap (v{old_roadmap.version}). "
        f"The learner already completed: {', '.join(completed_titles) or 'nothing yet'}. "
        f"Do not re-teach fully mastered material — build forward from there. "
        f"{extra_notes}"
    )

    new_roadmap = Roadmap.objects.create(
        user=old_roadmap.user,
        goal=old_roadmap.goal,
        current_skill_level=old_roadmap.current_skill_level,
        daily_minutes=daily_minutes or old_roadmap.daily_minutes,
        target_deadline=target_deadline or old_roadmap.target_deadline,
        learning_preference=learning_preference or old_roadmap.learning_preference,
        existing_skills=old_roadmap.existing_skills,
        preferred_language=old_roadmap.preferred_language,
        budget=old_roadmap.budget,
        version=old_roadmap.version + 1,
        regenerated_from=old_roadmap,
    )

    ok = generate_roadmap(new_roadmap, carry_forward_note=carry_forward)

    old_roadmap.status = "archived"
    old_roadmap.save(update_fields=["status"])

    return new_roadmap, ok


# ---------- Public API: phase checkpoint tests ----------
def _build_phase_test_prompt(phase, attempt_number, weak_topics=None):
    objectives = "\n".join(f"- {o}" for o in phase.objectives) or "General mastery of the phase"
    weak_note = ""
    if weak_topics:
        topics_str = ", ".join(weak_topics)
        weak_note = (
            f"\nThis is a RETAKE (attempt #{attempt_number}) after the learner already did a focused "
            f"remedial mini-phase on: {topics_str}. Weight the test a bit more toward these topics to "
            f"confirm the gap is actually closed, but still cover the full phase."
        )

    return f"""You are creating a checkpoint test for a self-paced AI learning roadmap platform (EvolveX).

Phase: {phase.title}
Difficulty: {phase.difficulty}
Objectives:
{objectives}
Completion criteria: {phase.completion_criteria or "General mastery of the above objectives"}
{weak_note}

Create a TOTAL 50-MARK test covering this phase's material with a MIX of question types:
- "mcq": 4 options, exactly one correct (0-indexed in "correct_option")
- "text": short-answer / conceptual explanation. Include a "rubric" field — a 1-3 sentence model
  answer / grading criteria. This is NEVER shown to the learner, only used for grading.
- "code": ONLY include code questions if this phase's subject is a programming/technical skill
  (e.g. web dev, DSA, backend, data science). If the phase is non-technical (language learning,
  fitness, exam prep, etc.), NEVER include "code" questions — use only "mcq" and "text".
  Code questions also need a "rubric" describing what a correct solution must do.

Rules:
- 6-10 questions total, marks must sum to EXACTLY 50.
- Tag every question with a short "topic" string (the specific sub-topic it tests) — this is used
  later to figure out exactly what the learner needs to review if they fail.
- Questions should test understanding, not just memorized trivia.

Return ONLY valid JSON, no markdown:
{{"questions": [{{"type":"mcq"|"text"|"code","question":"...","marks":int,
"options":["...","...","...","..."],"correct_option":0,"rubric":"","topic":"..."}}, ...]}}
(omit "options"/"correct_option" for non-mcq, omit "rubric" for mcq)"""


def generate_phase_test(phase, weak_topics=None):
    """
    Generate a new 50-mark checkpoint test attempt for `phase`. Returns the
    created PhaseTest, or None if generation failed.
    """
    attempt_number = phase.tests.count() + 1
    prompt = _build_phase_test_prompt(phase, attempt_number, weak_topics)
    result, pt, ct = _call_gemini(prompt, PhaseTestResponse)
    if result is None:
        return None

    questions = []
    for i, q in enumerate(result["questions"]):
        questions.append({
            "id": f"q{i + 1}",
            "type": q["type"],
            "question": q["question"],
            "marks": q["marks"],
            "options": q.get("options") or [],
            "correct_option": q.get("correct_option"),
            "rubric": q.get("rubric") or "",
            "topic": q.get("topic") or "",
            "user_answer": None,
            "awarded_marks": None,
            "feedback": "",
        })
    if not questions:
        return None

    # Normalize marks to sum to exactly 50 even if the AI didn't land on it.
    total = sum(q["marks"] for q in questions) or 1
    if total != 50:
        running = 0
        for q in questions[:-1]:
            q["marks"] = max(1, round(q["marks"] * 50 / total))
            running += q["marks"]
        questions[-1]["marks"] = max(1, 50 - running)

    return PhaseTest.objects.create(phase=phase, attempt_number=attempt_number, questions=questions)


def _grade_text_and_code_questions(questions):
    """Mutates `questions` in place, filling in awarded_marks + feedback
    for text/code questions by asking the AI to grade against each
    question's rubric."""
    items = "\n\n".join(
        f'ID: {q["id"]}\nTOPIC: {q["topic"]}\nMAX MARKS: {q["marks"]}\n'
        f'QUESTION: {q["question"]}\nRUBRIC / MODEL ANSWER: {q["rubric"]}\n'
        f'LEARNER\'S ANSWER: {q["user_answer"] or "(no answer given)"}'
        for q in questions
    )
    prompt = f"""You are grading a learner's checkpoint test answers for a self-paced learning platform.

For each item below, award marks out of MAX MARKS based on how well the learner's answer matches
the rubric/model answer. Give partial credit for partially-correct or partially-complete answers.
Give brief (max 1 sentence) constructive feedback per item.

{items}

Return ONLY valid JSON, no markdown:
{{"grades": [{{"id":"q1","awarded_marks":int,"feedback":"..."}}, ...]}}"""

    result, pt, ct = _call_gemini(prompt, GradingResponse)
    by_id = {g["id"]: g for g in (result["grades"] if result else [])}

    for q in questions:
        g = by_id.get(q["id"])
        if g:
            q["awarded_marks"] = min(g["awarded_marks"], q["marks"])
            q["feedback"] = g["feedback"]
        else:
            # Grading failed for this item — fail safe to 0 rather than
            # silently passing someone on an ungraded answer.
            q["awarded_marks"] = 0
            q["feedback"] = "Couldn't be graded automatically — treated as 0 for now."


def grade_phase_test(test, answers):
    """
    Grade `test` given `answers` (dict: question_id -> submitted answer).
    MCQ auto-graded by index match; text/code graded by AI against each
    question's rubric. Mutates and saves `test`. Returns `test`.
    """
    text_code_questions = []

    for q in test.questions:
        submitted = answers.get(q["id"])
        q["user_answer"] = submitted

        if q["type"] == "mcq":
            try:
                correct = submitted is not None and int(submitted) == q["correct_option"]
            except (TypeError, ValueError):
                correct = False
            q["awarded_marks"] = q["marks"] if correct else 0
            q["feedback"] = "Correct." if correct else "Incorrect."
        else:
            text_code_questions.append(q)

    if text_code_questions:
        _grade_text_and_code_questions(text_code_questions)

    weak_topics = []
    for q in test.questions:
        awarded = q["awarded_marks"] or 0
        if q["marks"] and awarded < q["marks"] * 0.6 and q["topic"]:
            weak_topics.append(q["topic"])

    test.score = sum(q["awarded_marks"] or 0 for q in test.questions)
    test.passed = test.score >= test.passing_marks
    test.status = "graded"
    test.graded_at = timezone.now()
    test.weak_topics = list(dict.fromkeys(weak_topics))  # dedupe, keep order
    test.save(update_fields=["questions", "score", "passed", "status", "graded_at", "weak_topics"])
    return test


def generate_remedial_phase(failed_phase, weak_topics):
    """
    Insert a short, tightly-scoped remedial RoadmapPhase right after
    `failed_phase`, focused only on `weak_topics`. Shifts every later
    phase's order by +1 to make room. Sets it as the roadmap's current
    phase. Returns the new RoadmapPhase, or None if generation failed.
    """
    roadmap = failed_phase.roadmap
    topics_str = ", ".join(weak_topics) if weak_topics else "the core concepts of this phase"

    prompt = f"""The learner FAILED the checkpoint test for this phase of their learning roadmap:

Phase: {failed_phase.title}
Weak topics identified from their test: {topics_str}

Create a focused REMEDIAL mini-phase (2-6 days) that re-teaches and reinforces ONLY these weak
areas before the learner retakes the checkpoint test. Keep it tightly scoped to just the weak
topics — do not repeat the entire original phase.

Return ONLY valid JSON, no markdown:
{{"title": "...", "objectives": ["...", "..."], "duration_days": int, "completion_criteria": "..."}}"""

    result, pt, ct = _call_gemini(prompt, RemedialPhaseResponse)
    if result is None:
        result = {
            "title": f"Remedial: {failed_phase.title}",
            "objectives": weak_topics or ["Review the core concepts of this phase"],
            "duration_days": 4,
            "completion_criteria": "Review the weak areas, then retake the checkpoint test.",
        }

    # Shift every phase AFTER the failed one to make room for the remedial
    # phase. Done as individual saves, HIGHEST order first — not a single
    # bulk .update(order=F("order")+1) — because (roadmap, order) is a
    # unique_together constraint and SQLite checks it per-row as the
    # UPDATE runs; shifting ascending can transiently collide with a row
    # that hasn't moved yet. Descending order guarantees the target slot
    # is always free before we write to it.
    phases_to_shift = list(
        RoadmapPhase.objects.filter(roadmap=roadmap, order__gt=failed_phase.order).order_by("-order")
    )
    for p in phases_to_shift:
        p.order += 1
        p.save(update_fields=["order"])

    remedial = RoadmapPhase.objects.create(
        roadmap=roadmap,
        order=failed_phase.order + 1,
        title=result["title"],
        objectives=result["objectives"],
        duration_days=result["duration_days"],
        difficulty=failed_phase.difficulty,
        xp_reward=max(30, failed_phase.xp_reward // 3),
        completion_criteria=result.get("completion_criteria", ""),
        status="active",
        is_remedial_for=failed_phase,
    )
    RoadmapCheckpoint.objects.create(
        phase=remedial,
        title=f"Ready to retry: {failed_phase.title}",
        description="Clear this checkpoint to retake the phase's test.",
        xp_reward=20,
    )

    # The original phase stays "active" (content-complete, but not passed
    # yet) — it'll get a fresh test attempt once the remedial phase clears.
    failed_phase.status = "active"
    failed_phase.save(update_fields=["status"])

    roadmap.current_phase_index = remedial.order
    roadmap.save(update_fields=["current_phase_index"])

    return remedial