"""
diary_ingest.py — Ingest daily summary files into the palace.

Architecture:
- ONE drawer per day — full verbatim content, upserted as the day grows
- Closets pack topics up to 1500 chars, never split mid-topic
- Only new entries are processed (tracks entry count in state file)
- Entities extracted and stamped on metadata for filterable search

Usage:
    python -m mempalace.diary_ingest --dir ~/daily_summaries --palace ~/.mempalace/palace
    python -m mempalace.diary_ingest --dir ~/daily_summaries --palace ~/.mempalace/palace --force
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .palace import (
    get_collection,
    get_closets_collection,
    build_closet_lines,
    upsert_closet_lines,
    CLOSET_CHAR_LIMIT,
)
from .miner import _extract_entities_for_metadata


DIARY_ENTRY_RE = re.compile(r"^## .+", re.MULTILINE)


def _split_entries(text):
    """Split diary text into (header, body) pairs per ## entry."""
    parts = DIARY_ENTRY_RE.split(text)
    headers = DIARY_ENTRY_RE.findall(text)
    entries = []
    for i, header in enumerate(headers):
        body = parts[i + 1] if i + 1 < len(parts) else ""
        entries.append((header.strip(), body.strip()))
    return entries


def ingest_diaries(
    diary_dir,
    palace_path,
    wing="diary",
    force=False,
):
    """Ingest daily summary files into the palace.

    Each date file gets ONE drawer (upserted as day grows) and
    closets that pack topics atomically up to 1500 chars.
    """
    diary_dir = Path(diary_dir).expanduser().resolve()
    if not diary_dir.exists():
        print(f"Diary directory not found: {diary_dir}")
        return

    diary_files = sorted(diary_dir.glob("*.md"))
    if not diary_files:
        print(f"No .md files in {diary_dir}")
        return

    # State tracks which entries have been closeted per file
    state_file = diary_dir / ".diary_ingest_state.json"
    state = {} if force else (
        json.loads(state_file.read_text()) if state_file.exists() else {}
    )

    drawers_col = get_collection(palace_path)
    closets_col = get_closets_collection(palace_path)

    days_updated = 0
    closets_created = 0

    for diary_path in diary_files:
        text = diary_path.read_text(encoding="utf-8", errors="replace")
        if len(text.strip()) < 50:
            continue

        date_match = re.match(r"(\d{4}-\d{2}-\d{2})", diary_path.stem)
        if not date_match:
            continue
        date_str = date_match.group(1)

        # Skip if content hasn't changed
        prev_size = state.get(diary_path.name, {}).get("size", 0)
        curr_size = len(text)
        if curr_size == prev_size and not force:
            continue

        now_iso = datetime.now(timezone.utc).isoformat()
        drawer_id = f"drawer_diary_{date_str}"

        # Extract entities from full day text
        entities = _extract_entities_for_metadata(text)

        # UPSERT the day's drawer (full verbatim, replaces as day grows)
        drawer_meta = {
            "date": date_str,
            "wing": wing,
            "room": "daily",
            "source_file": str(diary_path),
            "source_session": "daily_diary",
            "filed_at": now_iso,
        }
        if entities:
            drawer_meta["entities"] = entities
        drawers_col.upsert(
            documents=[text],
            ids=[drawer_id],
            metadatas=[drawer_meta],
        )

        # Split into entries and find new ones
        entries = _split_entries(text)
        prev_entry_count = state.get(diary_path.name, {}).get("entry_count", 0)
        new_entries = entries[prev_entry_count:] if not force else entries

        if new_entries:
            # Build closet lines from new entries
            all_lines = []
            for header, body in new_entries:
                entry_text = f"{header}\n{body}"
                entry_lines = build_closet_lines(
                    str(diary_path), [drawer_id], entry_text, wing, "daily"
                )
                all_lines.extend(entry_lines)

            if all_lines:
                closet_id_base = f"closet_diary_{date_str}"
                closet_meta = {
                    "date": date_str,
                    "wing": wing,
                    "room": "daily",
                    "source_file": str(diary_path),
                    "filed_at": now_iso,
                }
                if entities:
                    closet_meta["entities"] = entities
                n = upsert_closet_lines(
                    closets_col, closet_id_base, all_lines, closet_meta
                )
                closets_created += n

        state[diary_path.name] = {
            "size": curr_size,
            "entry_count": len(entries),
            "ingested_at": now_iso,
        }
        days_updated += 1

    state_file.write_text(json.dumps(state, indent=2))
    if days_updated:
        print(f"Diary: {days_updated} days updated, {closets_created} new closets")

    return {"days_updated": days_updated, "closets_created": closets_created}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ingest daily summaries into the palace")
    parser.add_argument("--dir", required=True, help="Path to daily_summaries directory")
    parser.add_argument("--palace", default=os.path.expanduser("~/.mempalace/palace"))
    parser.add_argument("--wing", default="diary")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    ingest_diaries(args.dir, args.palace, wing=args.wing, force=args.force)
