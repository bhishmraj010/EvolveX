"""
Cleans static/css/main.css:
1. Removes the fully-duplicated "Popup" CSS block if present twice
   (keeps the first, better-commented copy).
2. Removes the dead `h1, .auth-header h1 { ... }` gradient rule that gets
   100% overridden later by the "Vibrant gradient theme" section anyway
   (same selectors, later in cascade — the early one never actually renders).
   The @keyframes heading-shine block is LEFT ALONE since other rules use it.

Run from your project root:
    python clean_css.py

It writes a backup to static/css/main.css.bak before making any changes.
"""
import re
import shutil
from pathlib import Path

CSS_PATH = Path("static/css/main.css")

def main():
    if not CSS_PATH.exists():
        print(f"Could not find {CSS_PATH} — run this from your project root.")
        return

    original = CSS_PATH.read_text(encoding="utf-8")
    content = original

    # ── 1. Remove exact duplicate Popup block ───────────────────────────
    # Find all occurrences of the popup section's distinctive selector.
    marker = ".popup-card.subscription .popup-icon-wrap {"
    first = content.find(marker)
    second = content.find(marker, first + 1) if first != -1 else -1

    if second != -1:
        # The duplicate block starts a bit before the second marker, at the
        # nearest preceding comment banner or blank-line boundary, and runs
        # to the end of file (this block was appended twice, back-to-back).
        # We find the start of the *rule* just before the second marker's
        # containing selector block, then cut from the nearest earlier
        # ".popup-card {" (the block's own opening rule) to EOF, but only
        # if everything from there to EOF is a re-statement of content that
        # already appears earlier in the file.
        block_start_selector = ".popup-card {"
        # Find the LAST occurrence of ".popup-card {" before `second`
        search_region = content[:second]
        last_popup_card = search_region.rfind(block_start_selector)
        if last_popup_card != -1:
            # Also swallow a comment banner immediately above the cut point
            # (e.g. "/* ── Card glow uses theme accent ── */") so no orphan
            # comment is left dangling at the end of the file.
            preceding = content[:last_popup_card]
            comment_match = re.search(r"/\*[^*]*\*/\s*\Z", preceding)
            cut_point = comment_match.start() if comment_match else last_popup_card

            duplicate_chunk = content[cut_point:]
            content = content[:cut_point].rstrip() + "\n"
            print(f"Removed duplicate Popup block: {len(duplicate_chunk)} characters ({duplicate_chunk.count(chr(10))} lines).")
        else:
            print("Found a second popup marker but couldn't locate its block start — skipped, no changes made for this step.")
    else:
        print("No duplicate Popup block found — nothing to remove there.")

    # ── 2. Remove the dead early h1 gradient rule (keep the keyframes) ──
    dead_rule_pattern = re.compile(
        r"/\*\s*──?\s*Animated gradient headline text.*?──?\s*\*/\s*"
        r"h1,\s*\n\.auth-header h1\s*\{[^}]*\}\s*",
        re.DOTALL
    )
    new_content, n = dead_rule_pattern.subn("", content)
    if n:
        content = new_content
        print(f"Removed {n} dead 'h1, .auth-header h1' rule (fully overridden later, kept @keyframes heading-shine).")
    else:
        print("Dead h1 rule pattern not found (may already be removed, or formatted differently) — left as-is, check manually if needed.")

    if content != original:
        shutil.copy(CSS_PATH, CSS_PATH.with_suffix(".css.bak"))
        CSS_PATH.write_text(content, encoding="utf-8")
        print(f"\nDone. Backup saved to {CSS_PATH.with_suffix('.css.bak')}")
        print(f"Original size: {len(original)} chars -> New size: {len(content)} chars "
              f"(saved {len(original) - len(content)} chars)")
    else:
        print("\nNo changes made — file left untouched.")

if __name__ == "__main__":
    main()