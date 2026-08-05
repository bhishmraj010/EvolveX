"""
Lists every Gemini model your API key can actually access, plus what each
one supports (generateContent, etc). Use this to find the correct value(s)
for IMAGE_MODEL_CANDIDATES in generate_boss_images.py.

Usage:
    python manage.py list_gemini_models
"""
from django.core.management.base import BaseCommand
from life_simulation.gemini_client import get_client


class Command(BaseCommand):
    help = "List Gemini models available to this API key."

    def handle(self, *args, **options):
        client = get_client()
        if client is None:
            self.stderr.write(self.style.ERROR("GEMINI_API_KEY isn't set — check your .env."))
            return

        self.stdout.write("Models available to your key:\n")
        count = 0
        for m in client.models.list():
            count += 1
            actions = getattr(m, "supported_actions", None)
            self.stdout.write(f"  {m.name}  ->  {actions}")

        if count == 0:
            self.stdout.write(self.style.WARNING("No models returned — key may be invalid or has no access at all."))
        else:
            self.stdout.write(f"\n{count} model(s) total. Look for ones with 'image' in the name that list 'generateContent' as supported.")
