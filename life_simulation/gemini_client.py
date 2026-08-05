"""
Shared Gemini client helper. Both diet/views.py and analyzer/gemini_service.py
use this so there's exactly one place that reads GEMINI_API_KEY and builds the
client — keeps the whole app on the Gemini stack (Build-with-Gemini XPRIZE
requirement) instead of mixing providers.
"""
import os

from google import genai
from google.genai import types as genai_types

_client = None


def get_client():
    """Returns a cached genai.Client, or None if GEMINI_API_KEY isn't set."""
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return None
        _client = genai.Client(api_key=api_key)
    return _client


def generate_json(prompt, model="gemini-3.6-flash"):
    """Text-only prompt -> parsed JSON dict, or None on any failure."""
    data, _, _ = generate_json_with_usage(prompt, model=model)
    return data


def generate_json_with_usage(prompt, model="gemini-3.6-flash"):
    """
    Text-only prompt -> (parsed JSON dict or None, prompt_tokens, completion_tokens).
    Used where callers want to log real Gemini cost/usage (e.g. analyzer app),
    not just the parsed result.
    """
    import json
    client = get_client()
    if client is None:
        return None, 0, 0
    try:
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(response_mime_type="application/json"),
        )
        text = resp.text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        usage = getattr(resp, "usage_metadata", None)
        prompt_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
        completion_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
        return data, prompt_tokens or 0, completion_tokens or 0
    except Exception:
        return None, 0, 0


def generate_json_with_image(prompt, image_bytes, mime_type="image/jpeg", model="gemini-3.6-flash"):
    """Text + image prompt -> parsed JSON dict, or None on any failure."""
    import json
    client = get_client()
    if client is None:
        return None
    try:
        resp = client.models.generate_content(
            model=model,
            contents=[
                genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt,
            ],
            config=genai_types.GenerateContentConfig(response_mime_type="application/json"),
        )
        text = resp.text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception:
        return None