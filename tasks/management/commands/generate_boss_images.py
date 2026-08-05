"""
Generates a real AI portrait for every Boss (or just the ones missing an
image) using Gemini's image-generation models, and saves it straight into
Boss.image — replacing the SVG placeholder that shows whenever no image
is set.

Usage:
    python manage.py generate_boss_images            # only bosses with no image yet
    python manage.py generate_boss_images --force     # regenerate ALL bosses' images
    python manage.py generate_boss_images --level 5   # just one level

Requires GEMINI_API_KEY (already used elsewhere in this project) AND that
your API key/project has access to an image-generation model. This tries
each model in IMAGE_MODEL_CANDIDATES in order and reports exactly which
ones failed and why — if ALL of them 404, open Google AI Studio, check
which image model your key can actually use, and put it first in the list.
"""
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from tasks.models import Boss
from life_simulation.gemini_client import get_client

# Tried in order — first one that works for your API key wins. Gemini's
# image-generation models (and their names) have moved fast; the old
# Imagen `generate_images()` call is deprecated in favor of `generate_content()`
# with one of these image-capable models.
#
# NOTE: confirmed against `python manage.py list_gemini_models` output for
# this key. `gemini-2.5-flash-image` is listed as available but its free-tier
# quota is 0 (429 RESOURCE_EXHAUSTED) — kept last as a longshot in case quota
# is ever granted. Imagen models (imagen-4.0-*) are NOT included here because
# they only support the `predict` action, not `generateContent`, so they need
# a different API call than the one this command makes.
IMAGE_MODEL_CANDIDATES = [
    "nano-banana-pro-preview",
    "gemini-3.1-flash-image",
    "gemini-3-pro-image",
    "gemini-3.1-flash-image-preview",
    "gemini-3-pro-image-preview",
    "gemini-3.1-flash-lite-image",
    "gemini-2.5-flash-image",
]

STYLE_GUIDE = (
    "Dark fantasy video-game boss portrait, dramatic rim lighting, painterly "
    "digital art, moody purple-and-crimson color palette, ornate armor/silhouette, "
    "glowing eyes, cinematic close-up bust shot, square composition, no text, no watermark."
)


class Command(BaseCommand):
    help = "Generate AI portraits for Boss objects via Gemini's image-generation models."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Regenerate images even if one already exists")
        parser.add_argument("--level", type=int, default=None, help="Only generate for this level_number")

    def handle(self, *args, **options):
        client = get_client()
        if client is None:
            self.stderr.write(self.style.ERROR(
                "GEMINI_API_KEY isn't set — can't generate images. Check your .env."
            ))
            return

        bosses = Boss.objects.all().order_by("level_number", "order")
        if options["level"] is not None:
            bosses = bosses.filter(level_number=options["level"])
        if not options["force"]:
            bosses = bosses.filter(image="")

        if not bosses.exists():
            self.stdout.write("Nothing to do — every matching boss already has an image. Use --force to regenerate.")
            return

        working_model = None  # once one candidate succeeds, stick with it for the rest of the run

        for boss in bosses:
            prompt = self._build_prompt(boss)
            self.stdout.write(f"Generating image for L{boss.level_number} {boss.name}...")

            image_bytes = None
            models_to_try = [working_model] if working_model else IMAGE_MODEL_CANDIDATES
            errors = []

            for model_name in models_to_try:
                try:
                    image_bytes = self._generate_one(client, model_name, prompt)
                    if image_bytes:
                        working_model = model_name
                        break
                except Exception as e:
                    errors.append(f"{model_name}: {e}")

            if not image_bytes:
                self.stderr.write(self.style.ERROR(f"  Failed for {boss.name} — every model tried failed:"))
                for err in errors:
                    self.stderr.write(f"    - {err}")
                continue

            filename = f"boss_l{boss.level_number}_{boss.name.lower().replace(' ', '_')}.png"
            boss.image.save(filename, ContentFile(image_bytes), save=True)
            self.stdout.write(self.style.SUCCESS(f"  Saved ({working_model}): {filename}"))

        self.stdout.write(self.style.SUCCESS("Done. Refresh Boss Fights in the browser to see the new portraits."))

    def _generate_one(self, client, model_name, prompt):
        """Returns raw PNG bytes for the first image found in the response,
        or None if this model returned no image (caller tries the next)."""
        response = client.models.generate_content(model=model_name, contents=prompt)
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                inline_data = getattr(part, "inline_data", None)
                if inline_data is not None and inline_data.data:
                    return inline_data.data
        return None

    def _build_prompt(self, boss):
        parts = [STYLE_GUIDE, f"Subject: a boss monster named '{boss.name}'."]
        if boss.tagline:
            parts.append(f"Theme: {boss.tagline}.")
        if boss.lore:
            parts.append(f"Backstory for inspiration (do not render any text): {boss.lore[:300]}")
        if boss.boss_type == "final":
            parts.append("This is a FINAL boss — make it the most imposing, elaborate design in the series.")
        return " ".join(parts)