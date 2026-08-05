from django.conf import settings
from django.db import models
from django.utils import timezone


class RoadmapDraft(models.Model):
    """
    Holds the user's initial onboarding form answers WHILE the AI is asking
    (and the user is answering) clarifying questions — e.g. "Full Stack Dev"
    is ambiguous (MERN? Django+React? Java+Angular?), so we don't commit to
    a real Roadmap (and burn a generation call) until it's disambiguated.
    Deleted once converted into a real Roadmap.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="roadmap_drafts",
    )

    goal = models.CharField(max_length=200)
    current_skill_level = models.CharField(max_length=20, default="beginner")
    daily_minutes = models.PositiveIntegerField(default=60)
    target_deadline = models.DateField(null=True, blank=True)
    learning_preference = models.CharField(max_length=20, default="mixed")
    existing_skills = models.TextField(blank=True)
    preferred_language = models.CharField(max_length=50, default="English")
    budget = models.CharField(max_length=10, default="free")

    # [{"question": "Which stack — MERN or Django+React?", "answer": ""}, ...]
    # Max 5 entries. Empty list means the AI judged the goal unambiguous.
    clarifying_questions = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Draft: {self.goal} — {self.user}"

    def to_context_note(self):
        """Rendered into the roadmap-generation prompt as extra context."""
        answered = [q for q in self.clarifying_questions if q.get("answer", "").strip()]
        if not answered:
            return ""
        lines = "\n".join(f'- Q: {q["question"]}\n  A: {q["answer"]}' for q in answered)
        return (
            "\nBefore generating, the learner was asked clarifying questions to "
            "disambiguate their exact goal. Use these answers to pick the specific "
            f"stack/tools/scope — do NOT default to a generic or different choice:\n{lines}"
        )


class Roadmap(models.Model):
    """
    One AI-generated learning roadmap for a user's goal. A user can have
    multiple roadmaps over time (old ones archived), but only one ACTIVE
    roadmap drives the "AI Roadmap" dashboard / Today's Missions at a time.

    """

    SKILL_LEVELS = [
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    ]
    LEARNING_PREFERENCES = [
        ("video", "Video-based"),
        ("reading", "Reading / Docs"),
        ("hands_on", "Hands-on / Project-based"),
        ("mixed", "Mixed"),
    ]
    BUDGET_CHOICES = [
        ("free", "Free only"),
        ("paid", "Paid OK"),
        ("mixed", "Free preferred, paid if needed"),
    ]
    STATUS_CHOICES = [
        ("active", "Active"),
        ("completed", "Completed"),
        ("paused", "Paused"),
        ("archived", "Archived"),
    ]
    LEARNING_SPEED_CHOICES = [
        ("slow", "Slower than plan"),
        ("steady", "On pace"),
        ("fast", "Ahead of plan"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="roadmaps",
    )

    # ── User inputs ──
    goal = models.CharField(max_length=200)
    current_skill_level = models.CharField(max_length=20, choices=SKILL_LEVELS, default="beginner")
    daily_minutes = models.PositiveIntegerField(default=60)
    target_deadline = models.DateField(null=True, blank=True)
    learning_preference = models.CharField(max_length=20, choices=LEARNING_PREFERENCES, default="mixed")
    existing_skills = models.TextField(blank=True, help_text="Comma-separated skills the user already has")
    preferred_language = models.CharField(max_length=50, default="English")
    budget = models.CharField(max_length=10, choices=BUDGET_CHOICES, default="free")

    # ── Lifecycle ──
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="active")
    version = models.PositiveIntegerField(default=1)  # bumped each "Regenerate Roadmap"
    regenerated_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="regenerations"
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    # ── Progress (denormalized for fast dashboard reads) ──
    current_phase_index = models.PositiveIntegerField(default=0)
    overall_completion_pct = models.PositiveSmallIntegerField(default=0)
    xp_earned = models.PositiveIntegerField(default=0)
    xp_total_available = models.PositiveIntegerField(default=0)
    day_streak = models.PositiveIntegerField(default=0)
    longest_streak = models.PositiveIntegerField(default=0)

    # ── AI predictions (Learning Prediction Engine) ──
    predicted_completion_date = models.DateField(null=True, blank=True)
    success_probability = models.PositiveSmallIntegerField(default=0)  # 0-100
    learning_speed = models.CharField(max_length=10, choices=LEARNING_SPEED_CHOICES, default="steady")
    consistency_score = models.PositiveSmallIntegerField(default=0)  # 0-100

    # ── Smart recommendations (list[str] each) ──
    what_to_learn_next = models.JSONField(default=list, blank=True)
    what_to_skip = models.JSONField(default=list, blank=True)
    prerequisites = models.JSONField(default=list, blank=True)
    common_mistakes = models.JSONField(default=list, blank=True)
    learning_hacks = models.JSONField(default=list, blank=True)

    # ── AI generation bookkeeping ──
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    generation_failed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.goal} — {self.user} (v{self.version})"

    # ── Convenience ──
    def phases_ordered(self):
        return self.phases.order_by("order")

    def current_phase(self):
        return self.phases.filter(order=self.current_phase_index).first()

    def days_left(self):
        if not self.target_deadline:
            return None
        return max(0, (self.target_deadline - timezone.now().date()).days)

    def recompute_progress(self):
        """Recalculate overall_completion_pct / xp_earned from phase state.
        Call after any phase/checkpoint/mission update."""
        phases = list(self.phases.all())
        if not phases:
            self.overall_completion_pct = 0
        else:
            total_duration = sum(p.duration_days for p in phases) or 1
            weighted_pct = sum(p.completion_pct * p.duration_days for p in phases) / total_duration
            pct = round(weighted_pct)
            # Duration-weighting can round tiny early progress down to 0,
            # which reads as "nothing happened" even after a real completed
            # mission — always surface at least 1% once any phase has moved.
            if pct == 0 and any(p.completion_pct > 0 for p in phases):
                pct = 1
            self.overall_completion_pct = pct
        phase_xp = sum(p.xp_reward for p in phases if p.status == "completed")
        mission_xp = sum(
            m.xp_reward for m in self.daily_missions.filter(status="completed")
        )
        self.xp_earned = phase_xp + mission_xp
        self.xp_total_available = sum(p.xp_reward for p in phases)
        if self.overall_completion_pct >= 100 and self.status == "active":
            self.status = "completed"
        self.save(update_fields=[
            "overall_completion_pct", "xp_earned", "xp_total_available", "status", "updated_at"
        ])


class RoadmapPhase(models.Model):
    """One stage of the roadmap, e.g. 'Basics' -> 'OOP' -> 'Projects'."""

    DIFFICULTY_CHOICES = [
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
        ("expert", "Expert"),
    ]
    STATUS_CHOICES = [
        ("locked", "Locked"),
        ("active", "Active"),
        ("completed", "Completed"),
    ]

    roadmap = models.ForeignKey(Roadmap, on_delete=models.CASCADE, related_name="phases")
    order = models.PositiveIntegerField()  # 0-indexed position in the roadmap
    title = models.CharField(max_length=150)
    objectives = models.JSONField(default=list, blank=True)  # list[str] learning objectives
    duration_days = models.PositiveIntegerField(default=7)
    difficulty = models.CharField(max_length=15, choices=DIFFICULTY_CHOICES, default="beginner")
    xp_reward = models.PositiveIntegerField(default=100)
    completion_criteria = models.TextField(blank=True)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="locked")
    completion_pct = models.PositiveSmallIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    estimated_finish_date = models.DateField(null=True, blank=True)

    # Speculative pre-generation: while the learner is still working through
    # the CURRENT day's mission, the AI generates the NEXT day's mission in
    # the background and stashes it here (not yet a real DailyMission row).
    # The instant the current day is completed, this cache is materialized
    # into a real DailyMission — instant reveal, no AI wait at that moment.
    # Shape: {"date": "YYYY-MM-DD", "tasks": [...], "estimated_minutes": int,
    #         "xp_reward": int, "was_adaptive": bool, "adaptive_note": str}
    next_mission_cache = models.JSONField(null=True, blank=True)
    # When we last TRIED to prefetch (even if it failed) — used to avoid
    # hammering the AI API with repeat retries right after a rate-limit
    # error. Cleared to None as soon as a prefetch actually succeeds.
    next_mission_attempted_at = models.DateTimeField(null=True, blank=True)
    # True while a prefetch call is actively in flight. Lets the
    # "last task just completed" path wait/poll for that call to finish
    # instead of firing its OWN duplicate AI call at the same time.
    next_mission_generating = models.BooleanField(default=False)

    # If this phase exists only because the learner FAILED the checkpoint
    # test for another phase, this points back to that original phase.
    # Clearing THIS phase's checkpoint sends the learner back to retake the
    # original phase's test, instead of advancing forward past it.
    is_remedial_for = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="remedial_phases"
    )

    def latest_test(self):
        return self.tests.order_by("-attempt_number").first()

    def pending_remedial(self):
        """The remedial phase currently blocking a retest, if any."""
        return self.remedial_phases.exclude(status="completed").order_by("-id").first()

    class Meta:
        ordering = ["order"]
        unique_together = [("roadmap", "order")]

    def __str__(self):
        return f"Phase {self.order + 1}: {self.title}"

    def mark_active(self):
        self.status = "active"
        self.started_at = self.started_at or timezone.now()
        self.save(update_fields=["status", "started_at"])

    def mark_completed(self):
        self.status = "completed"
        self.completion_pct = 100
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completion_pct", "completed_at"])

    def recompute_completion(self):
        """Bump this phase's completion_pct as the learner clears daily
        missions inside it, so the roadmap progress bar moves day-to-day
        instead of jumping 0 -> 100 only when the checkpoint is cleared.
        Capped at 99 here — mark_completed() (via checkpoint.clear()) is
        what takes it to the final 100."""
        if self.status == "completed":
            return
        completed_days = self.daily_missions.filter(status="completed").count()
        pct = min(99, round(completed_days / max(self.duration_days, 1) * 100))
        if pct != self.completion_pct:
            self.completion_pct = pct
            self.save(update_fields=["completion_pct"])
            self.roadmap.recompute_progress()


class RoadmapCheckpoint(models.Model):
    """
    Sits at the end of a phase. Must be cleared (checked off, quiz passed,
    etc.) before the next phase unlocks — mirrors tasks.models Boss system.
    """
    phase = models.OneToOneField(RoadmapPhase, on_delete=models.CASCADE, related_name="checkpoint")
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    xp_reward = models.PositiveIntegerField(default=50)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Checkpoint: {self.title}"

    def clear(self):
        """Complete the checkpoint, unlock next phase, award XP."""
        if self.is_completed:
            return
        self.is_completed = True
        self.completed_at = timezone.now()
        self.save(update_fields=["is_completed", "completed_at"])

        phase = self.phase
        phase.mark_completed()

        roadmap = phase.roadmap

        if phase.is_remedial_for_id:
            # This was a remedial detour — send the learner back to retake
            # the ORIGINAL phase's checkpoint test, not forward past it.
            original = phase.is_remedial_for
            original.status = "active"
            original.save(update_fields=["status"])
            roadmap.current_phase_index = original.order
            roadmap.save(update_fields=["current_phase_index"])
        else:
            next_phase = roadmap.phases.filter(order=phase.order + 1).first()
            if next_phase:
                next_phase.mark_active()
                roadmap.current_phase_index = next_phase.order
                roadmap.save(update_fields=["current_phase_index"])

        roadmap.recompute_progress()

        user = roadmap.user
        user.total_xp += self.xp_reward
        user.save(update_fields=["total_xp"])
        user.check_level_up()


class PhaseTest(models.Model):
    """
    A generated checkpoint test for a phase. `questions` holds everything —
    the question, options/rubric (hidden from the learner by the template,
    not the DB), the learner's submitted answer, and the awarded marks —
    so grading results are self-contained per attempt.

    Question shape: {"id", "type": "mcq"|"text"|"code", "question",
    "marks", "options": [...] (mcq only), "correct_option": int (mcq only),
    "rubric": "..." (text/code only, model-answer/grading criteria),
    "topic", "user_answer", "awarded_marks", "feedback"}
    """
    STATUS_CHOICES = [("pending", "Pending"), ("graded", "Graded")]

    phase = models.ForeignKey(RoadmapPhase, on_delete=models.CASCADE, related_name="tests")
    attempt_number = models.PositiveIntegerField(default=1)
    total_marks = models.PositiveIntegerField(default=50)
    passing_marks = models.PositiveIntegerField(default=16)
    questions = models.JSONField(default=list)

    score = models.PositiveIntegerField(null=True, blank=True)
    passed = models.BooleanField(null=True)
    weak_topics = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    graded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-attempt_number"]

    def __str__(self):
        return f"Test for {self.phase} (attempt {self.attempt_number})"


class DailyMission(models.Model):
    """
    A single day's generated missions for a roadmap: learning task, practice
    task, revision task, mini challenge. `tasks` holds the structured list so
    the UI (and adaptive engine) can render/update each sub-task independently.

    Unique per (roadmap, phase, date) rather than just (roadmap, date) — if a
    learner clears a checkpoint and jumps to the next phase mid-day, that new
    phase gets its own mission immediately instead of waiting for tomorrow.
    """
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("skipped", "Skipped"),
    ]

    roadmap = models.ForeignKey(Roadmap, on_delete=models.CASCADE, related_name="daily_missions")
    phase = models.ForeignKey(RoadmapPhase, on_delete=models.SET_NULL, null=True, blank=True, related_name="daily_missions")
    date = models.DateField(default=timezone.localdate)

    # tasks: [{"id": "learning", "type": "learning", "title": "...",
    #          "description": "...", "minutes": 30, "completed": false}, ...]
    tasks = models.JSONField(default=list, blank=True)

    estimated_minutes = models.PositiveIntegerField(default=0)
    xp_reward = models.PositiveIntegerField(default=20)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")
    completed_at = models.DateTimeField(null=True, blank=True)
    was_adaptive = models.BooleanField(default=False)  # True if difficulty was auto-adjusted
    adaptive_note = models.CharField(max_length=200, blank=True)  # e.g. "Harder task — you're ahead"

    class Meta:
        ordering = ["date"]
        unique_together = [("roadmap", "phase", "date")]

    def __str__(self):
        return f"Mission {self.date} — {self.roadmap.goal}"

    def completion_pct(self):
        if not self.tasks:
            return 0
        done = sum(1 for t in self.tasks if t.get("completed"))
        return round(done / len(self.tasks) * 100)

    def toggle_task(self, task_id):
        """Flip a single sub-task's completed flag; auto-complete mission
        + award XP when every sub-task is done."""
        changed = False
        for t in self.tasks:
            if t.get("id") == task_id:
                t["completed"] = not t.get("completed", False)
                changed = True
                break
        if not changed:
            return False

        all_done = all(t.get("completed") for t in self.tasks)
        was_completed = self.status == "completed"

        if all_done and not was_completed:
            self.status = "completed"
            self.completed_at = timezone.now()
            user = self.roadmap.user
            user.total_xp += self.xp_reward
            user.save(update_fields=["total_xp"])
            user.check_level_up()
        elif not all_done and was_completed:
            # user unchecked something after completing — claw back XP once
            self.status = "in_progress"
            self.completed_at = None
            user = self.roadmap.user
            user.total_xp = max(0, user.total_xp - self.xp_reward)
            user.save(update_fields=["total_xp"])
        elif any(t.get("completed") for t in self.tasks):
            self.status = "in_progress"

        self.save(update_fields=["tasks", "status", "completed_at"])

        # Keep phase completion % and roadmap-level XP/progress in sync with
        # today's mission, instead of only updating on full checkpoint clear.
        if self.phase_id:
            self.phase.recompute_completion()
        self.roadmap.recompute_progress()

        return True


class RoadmapResource(models.Model):
    """AI-recommended learning resource for a roadmap or a specific phase."""

    RESOURCE_TYPES = [
        ("youtube", "YouTube Channel/Video"),
        ("documentation", "Documentation"),
        ("book", "Book"),
        ("course", "Course"),
        ("article", "Article"),
        ("practice", "Practice Website"),
    ]

    roadmap = models.ForeignKey(Roadmap, on_delete=models.CASCADE, related_name="resources")
    phase = models.ForeignKey(RoadmapPhase, on_delete=models.SET_NULL, null=True, blank=True, related_name="resources")
    resource_type = models.CharField(max_length=15, choices=RESOURCE_TYPES, default="article")
    title = models.CharField(max_length=200)
    url = models.URLField(blank=True)
    is_free = models.BooleanField(default=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["phase__order", "resource_type"]

    def __str__(self):
        return self.title