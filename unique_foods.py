#!/usr/bin/env python3
# Copyright (c) 2026 SwitchUpCB
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# SPDX-License-Identifier: MIT

import csv
import logging
from logging.handlers import RotatingFileHandler
import math
import os
import re
import time
import tracemalloc
from datetime import datetime, timedelta
from pathlib import Path
import frontmatter
import psutil
import argparse

# Configuration Constants
SYNC_DAYS = 0  # Set to 0 or None to sync the entire CSV history

EXCLUDED_COLS = {"Date", "Time"}
NON_NUTRIENT_COLS = {"Food Name", "Serving Size", "Serving Qty"}
SCHEMA_VERSION = 2

IGNORED_FOOD_PATTERNS = [
    r"^quick\s*add\b",       # Matches "Quick Add", "Quick Add Calories", "Quick-Add"
    r"^custom\s*calories\b", # Common tracker variant
]


def setup_logger(out_path: Path) -> logging.Logger:
    out_path.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("food_bank_sync")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        log_file = out_path / ".sync.log"
        file_handler = RotatingFileHandler(
            log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def start_build_metrics():
    tracemalloc.start()
    start_time = time.perf_counter()
    process = psutil.Process()

    def log_build_metrics(label: str = "build"):
        elapsed = time.perf_counter() - start_time
        rss_mb = round(process.memory_info().rss / 1024 / 1024)
        heap_used, heap_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        print(
            f"[{label}] Time: {elapsed:.2f}s | "
            f"RSS: {rss_mb} MB | "
            f"Heap Used: {round(heap_used / 1024 / 1024)} MB | "
            f"Heap Total: {round(heap_peak / 1024 / 1024)} MB"
        )

    return log_build_metrics


def is_ignored_food(food_name: str) -> bool:
    normalized = " ".join(food_name.lower().split())
    return any(re.search(pattern, normalized) for pattern in IGNORED_FOOD_PATTERNS)


def to_snake_case(header: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", header.strip().lower())
    return cleaned.strip("_")


def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]+', "", name).strip()


def parse_timestamp(date_str: str, time_str: str) -> datetime:
    raw = f"{date_str.strip()} {time_str.strip()}"
    for fmt in ("%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return datetime.min


def is_valid_weight(weight: float, qty: float, unit: str) -> bool:
    if weight <= 0:
        return False
    if weight < 1.0 and unit.strip().lower() not in {"g", "mg", "mcg"} and qty >= 1:
        return False
    return True


def normalize_row(row: dict, dt: datetime) -> tuple[dict, bool]:
    raw_qty = row.get("Serving Qty", "").strip()
    qty = float(raw_qty) if raw_qty else 1.0
    if qty <= 0:
        qty = 1.0

    is_exact_unit = math.isclose(qty, 1.0, abs_tol=1e-6)
    unit = row.get("Serving Size", "").strip()
    food_name = row.get("Food Name", "").strip()

    profile = {
        "type": "food",
        "source": "macrofactor",
        "schema_version": SCHEMA_VERSION,
        "version_status": "latest",
        "discovered": dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "food_name": food_name,
        "serving_size": unit,
        "serving_qty": 1,
        "exact_unit_source": is_exact_unit,
    }

    for col, raw_val in row.items():
        if col in EXCLUDED_COLS or col in NON_NUTRIENT_COLS:
            continue

        val_str = raw_val.strip()
        if not val_str:
            continue

        try:
            num_val = float(val_str)
        except ValueError:
            continue

        if col == "Serving Weight (g)" and not is_valid_weight(num_val, qty, unit):
            continue

        normalized_val = round(num_val / qty, 2)
        profile[to_snake_case(col)] = int(normalized_val) if normalized_val.is_integer() else normalized_val

    return profile, is_exact_unit


def get_nutrient_keys(profile: dict, allowed_keys: set[str]) -> set[str]:
    return {
        k for k, v in profile.items()
        if k in allowed_keys and isinstance(v, (int, float))
    }


def profiles_match(
    p1: dict, p2: dict, allowed_keys: set[str], loose_rounding: bool = False
) -> bool:
    if str(p1.get("serving_size", "")).lower() != str(p2.get("serving_size", "")).lower():
        return False

    all_keys = get_nutrient_keys(p1, allowed_keys) | get_nutrient_keys(p2, allowed_keys)
    rel_tol = 0.06 if loose_rounding else 0.02
    abs_tol = 0.85 if loose_rounding else 0.05

    for k in all_keys:
        v1 = float(p1.get(k, 0.0))
        v2 = float(p2.get(k, 0.0))
        if not math.isclose(v1, v2, rel_tol=rel_tol, abs_tol=abs_tol):
            return False

    return True


def get_diff_reason(p1: dict, p2: dict, allowed_keys: set[str]) -> str:
    s1 = str(p1.get("serving_size", ""))
    s2 = str(p2.get("serving_size", ""))
    if s1.lower() != s2.lower():
        return f"serving_size ({s1} vs {s2})"

    all_keys = sorted(get_nutrient_keys(p1, allowed_keys) | get_nutrient_keys(p2, allowed_keys))
    both_exact = bool(p1.get("exact_unit_source")) and bool(p2.get("exact_unit_source"))
    rel_tol = 0.02 if both_exact else 0.06
    abs_tol = 0.05 if both_exact else 0.85

    diffs = []
    for k in all_keys:
        v1 = float(p1.get(k, 0.0))
        v2 = float(p2.get(k, 0.0))
        if not math.isclose(v1, v2, rel_tol=rel_tol, abs_tol=abs_tol):
            diffs.append(f"{k} ({v1} vs {v2})")

    return ", ".join(diffs) if diffs else "minor rounding variance"


def order_metadata(data: dict) -> dict:
    priority = [
        "title", "type", "source", "schema_version", "status", "version_status",
        "discovered", "previous_version", "food_name", "serving_size", "serving_qty",
        "exact_unit_source", "needs_review", "review_reason", "reviewed",
        "set_as_final_version", "set_as_only_version", "set_as_unique", "duplicate_of",
    ]
    ordered = {k: data[k] for k in priority if k in data}
    for k in sorted(k for k in data if k not in priority):
        ordered[k] = data[k]
    return ordered


def atomic_write_text(fp: Path, content: str, retries: int = 3) -> None:
    tmp_fp = fp.with_name(f".{fp.name}.tmp")
    for attempt in range(retries):
        try:
            tmp_fp.write_text(content, encoding="utf-8")
            os.replace(tmp_fp, fp)
            return
        except OSError:
            if attempt == retries - 1:
                if tmp_fp.exists():
                    tmp_fp.unlink(missing_ok=True)
                raise
            time.sleep(0.05 * (attempt + 1))


def canonicalize_food_name(name: str) -> str:
    base = re.sub(r"(__v_\d+)+$", "", name).strip()
    base = re.sub(r"\s+by\s+[^,()]+$", "", base, flags=re.IGNORECASE).strip()
    return " ".join(base.lower().split())


def extract_link_target(link_val: object) -> str:
    if not link_val:
        return ""
    s = str(link_val).strip()
    match = re.search(r"\[\[([^\]|#]+)", s)
    if match:
        return match.group(1).strip()
    return s.strip('"').strip("'").strip()


def migrate_v1_metadata(meta: dict) -> bool:
    """Upgrade v1 frontmatter keys (status -> version_status, derived_from -> previous_version) in place."""
    changed = False
    if meta.get("schema_version") == 1 or ("version_status" not in meta and "status" in meta):
        old_status = str(meta.get("status", "")).lower()
        mapping = {"active": "latest", "superseded": "previous", "archived": "unlogged"}
        if old_status in mapping:
            meta["version_status"] = mapping[old_status]
            meta.pop("status", None)
            changed = True
        elif "version_status" not in meta:
            meta["version_status"] = "latest"
            changed = True

    if "derived_from" in meta:
        if "previous_version" not in meta:
            meta["previous_version"] = meta["derived_from"]
        meta.pop("derived_from", None)
        changed = True

    if "lock_profile" in meta:
        if meta["lock_profile"] is True and "set_as_final_version" not in meta:
            meta["set_as_final_version"] = True
        meta.pop("lock_profile", None)
        changed = True

    if "source" not in meta:
        meta["source"] = "macrofactor"
        changed = True

    if meta.get("schema_version") != SCHEMA_VERSION:
        meta["schema_version"] = SCHEMA_VERSION
        changed = True

    return changed


def load_vault_state(
    out_path: Path, logger: logging.Logger
) -> tuple[dict[tuple[str, str], list[dict]], dict[str, str], dict[str, dict]]:
    vault_foods: dict[tuple[str, str], list[dict]] = {}
    alias_to_canonical: dict[str, str] = {}
    entries_by_stem: dict[str, dict] = {}

    for md_file in out_path.glob("*.md"):
        try:
            post = frontmatter.load(md_file)
        except Exception as exc:
            logger.warning(f"Skipping unreadable markdown file '{md_file.name}': {exc}")
            continue

        if post.metadata.get("type") != "food":
            continue

        dirty = migrate_v1_metadata(post.metadata)

        raw_name = str(post.metadata.get("food_name") or post.metadata.get("title") or md_file.stem)
        canonical_key = canonicalize_food_name(raw_name)
        unit_key = str(post.metadata.get("serving_size", "")).strip().lower()

        match = re.search(r"__v_(\d+)$", md_file.stem)
        variant_num = int(match.group(1)) if match else 1

        entry = {
            "variant_num": variant_num,
            "file_path": md_file,
            "stem": md_file.stem,
            "canonical_key": canonical_key,
            "unit_key": unit_key,
            "post": post,
            "dirty": dirty,
            "delete": False,
        }

        vault_foods.setdefault((canonical_key, unit_key), []).append(entry)
        entries_by_stem[md_file.stem.lower()] = entry

        for alias in (post.metadata.get("aliases") or []):
            alias_key = canonicalize_food_name(str(alias))
            if alias_key and alias_key != canonical_key:
                alias_to_canonical[alias_key] = canonical_key

    for entries in vault_foods.values():
        entries.sort(key=lambda e: e["variant_num"])

    return vault_foods, alias_to_canonical, entries_by_stem


def apply_user_directives(
    vault_foods: dict[tuple[str, str], list[dict]],
    entries_by_stem: dict[str, dict],
    alias_to_canonical: dict[str, str],
    out_path: Path,
    claimed_stems: set[str],
    stats: dict[str, int],
    logger: logging.Logger,
) -> None:
    """Execute declarative user controls (duplicate_of, set_as_unique, set_as_only_version) idempotently."""
    # 1. Process duplicate_of links: transfer food_name + aliases to target note and mark source for deletion
    for entries in vault_foods.values():
        for entry in entries:
            if entry["delete"] or entry["post"].metadata.get("source") == "manual":
                continue

            dup_target_raw = extract_link_target(entry["post"].metadata.get("duplicate_of"))
            if not dup_target_raw:
                continue

            target_entry = entries_by_stem.get(dup_target_raw.lower())
            if not target_entry or target_entry is entry or target_entry["delete"]:
                continue

            target_meta = target_entry["post"].metadata
            target_aliases = list(target_meta.get("aliases") or [])
            target_name = str(target_meta.get("food_name", "")).strip()

            names_to_transfer = [str(entry["post"].metadata.get("food_name", "")).strip()] + [
                str(a).strip() for a in (entry["post"].metadata.get("aliases") or [])
            ]
            for name in names_to_transfer:
                if name and name.lower() != target_name.lower() and name not in target_aliases:
                    target_aliases.append(name)
                alias_key = canonicalize_food_name(name)
                if alias_key and alias_key != target_entry["canonical_key"]:
                    alias_to_canonical[alias_key] = target_entry["canonical_key"]

            target_meta["aliases"] = target_aliases
            target_entry["dirty"] = True

            entry["delete"] = True
            logger.info(f"Resolved duplicate_of: merged '{entry['stem']}' into '{target_entry['stem']}'")

    # 2. Process set_as_unique: fork a variant into its own standalone food note while keeping CSV alias
    reassigned: list[tuple[tuple[str, str], dict, tuple[str, str]]] = []
    for old_group_key, entries in list(vault_foods.items()):
        for entry in entries:
            if entry["delete"] or entry["post"].metadata.get("source") == "manual":
                continue

            new_unique_name = str(entry["post"].metadata.get("set_as_unique") or "").strip()
            if not new_unique_name:
                continue

            meta = entry["post"].metadata
            old_food_name = str(meta.get("food_name", "")).strip()
            aliases = list(meta.get("aliases") or [])
            if old_food_name and old_food_name.lower() != new_unique_name.lower() and old_food_name not in aliases:
                aliases.append(old_food_name)

            new_canonical = canonicalize_food_name(new_unique_name)
            unit_key = entry["unit_key"]
            new_group_key = (new_canonical, unit_key)

            meta["food_name"] = new_unique_name
            meta["title"] = new_unique_name
            meta["aliases"] = aliases
            meta["version_status"] = "latest"
            meta["reviewed"] = True
            meta["needs_review"] = False
            meta.pop("review_reason", None)
            meta.pop("previous_version", None)
            meta.pop("set_as_unique", None)

            new_stem = sanitize_filename(new_unique_name)
            if new_stem.lower() in claimed_stems and new_stem.lower() != entry["stem"].lower() and unit_key:
                new_stem = sanitize_filename(f"{new_unique_name} ({unit_key})")
                meta["title"] = new_stem

            old_fp: Path = entry["file_path"]
            new_fp = out_path / f"{new_stem}.md"
            if old_fp != new_fp and not new_fp.exists():
                if old_fp.exists():
                    os.replace(old_fp, new_fp)
                claimed_stems.discard(entry["stem"].lower())
                claimed_stems.add(new_stem.lower())
                entry["file_path"] = new_fp
                entry["stem"] = new_stem
                stats["synced"] += 1

            entry["variant_num"] = 1
            entry["canonical_key"] = new_canonical
            entry["dirty"] = True

            if new_group_key != old_group_key:
                reassigned.append((old_group_key, entry, new_group_key))

            logger.info(f"Split standalone food via set_as_unique -> '{new_stem}.md'")

    for old_gk, entry, new_gk in reassigned:
        vault_foods[old_gk].remove(entry)
        vault_foods.setdefault(new_gk, []).append(entry)

    # 3. Process set_as_only_version: promote chosen variant onto base note and delete all other variants
    for group_key, entries in vault_foods.items():
        active = [e for e in entries if not e["delete"]]
        if not active:
            continue

        only_candidates = [e for e in active if e["post"].metadata.get("set_as_only_version") is True]
        if not only_candidates:
            continue

        chosen = only_candidates[-1]
        base_entry = next(iter(active))

        if chosen is not base_entry:
            # Copy chosen variant's macros & flags onto the clean base note
            preserved = {
                k: base_entry["post"].metadata[k]
                for k in ("title", "food_name", "discovered", "aliases", "status", "tags", "ingredients")
                if k in base_entry["post"].metadata
            }
            merged_aliases = list(dict.fromkeys(
                list(preserved.get("aliases") or []) + list(chosen["post"].metadata.get("aliases") or [])
            ))
            base_entry["post"].metadata = order_metadata({**chosen["post"].metadata, **preserved})
            if merged_aliases:
                base_entry["post"].metadata["aliases"] = merged_aliases
            base_entry["post"].metadata.pop("previous_version", None)
            base_entry["dirty"] = True

        base_entry["post"].metadata["set_as_only_version"] = True
        base_entry["post"].metadata["set_as_final_version"] = True
        base_entry["post"].metadata["version_status"] = "latest"
        base_entry["post"].metadata["reviewed"] = True
        base_entry["post"].metadata["needs_review"] = False
        base_entry["post"].metadata.pop("review_reason", None)
        base_entry["dirty"] = True

        for other in active:
            if other is not base_entry:
                other["delete"] = True
                logger.info(f"Removed '{other['stem']}' due to set_as_only_version on '{base_entry['stem']}'")


def consolidate_variants(entries: list[dict], allowed_keys: set[str], logger: logging.Logger) -> None:
    if len(entries) <= 1:
        return

    survivors: list[dict] = []
    for candidate in entries:
        if candidate["delete"]:
            continue

        cand_exact = bool(candidate["post"].metadata.get("exact_unit_source", False))
        merged = False

        for keeper in survivors:
            keeper_exact = bool(keeper["post"].metadata.get("exact_unit_source", False))
            loose = not (cand_exact and keeper_exact)

            if profiles_match(keeper["post"].metadata, candidate["post"].metadata, allowed_keys, loose_rounding=loose):
                if cand_exact and not keeper_exact and keeper["post"].metadata.get("set_as_final_version") is not True:
                    preserved_meta = {
                        k: keeper["post"].metadata[k]
                        for k in (
                            "title", "previous_version", "discovered", "aliases", "status",
                            "banned", "ban_reason", "tags", "ingredients",
                            "set_as_final_version", "set_as_only_version", "reviewed",
                        )
                        if k in keeper["post"].metadata
                    }
                    keeper["post"].metadata = order_metadata({**candidate["post"].metadata, **preserved_meta})
                    keeper["dirty"] = True

                cand_name = str(candidate["post"].metadata.get("food_name", "")).strip()
                keeper_name = str(keeper["post"].metadata.get("food_name", "")).strip()
                if cand_name and cand_name.lower() != keeper_name.lower():
                    aliases = list(keeper["post"].metadata.get("aliases") or [])
                    if cand_name not in aliases:
                        aliases.append(cand_name)
                        keeper["post"].metadata["aliases"] = aliases
                        keeper["dirty"] = True

                candidate["delete"] = True
                merged = True
                logger.info(f"Merged redundant variant '{candidate['stem']}' into '{keeper['stem']}'")
                break

        if not merged:
            survivors.append(candidate)

    if survivors:
        # Respect set_as_final_version if pinned; otherwise prefer exact 1x source as latest
        survivors.sort(key=lambda e: (
            e["post"].metadata.get("set_as_final_version") is True,
            bool(e["post"].metadata.get("exact_unit_source", False)),
            e["variant_num"],
        ))

        for older in survivors[:-1]:
            if older["post"].metadata.get("version_status") == "latest":
                older["post"].metadata["version_status"] = "previous"
                older["dirty"] = True

        latest = survivors[-1]
        if latest["post"].metadata.get("version_status") == "previous":
            latest["post"].metadata["version_status"] = "latest"
            latest["dirty"] = True


def reconcile_variant_stems(
    entries: list[dict],
    unit_key: str,
    out_path: Path,
    claimed_stems: set[str],
    stats: dict[str, int],
    logger: logging.Logger,
) -> None:
    """Self-heal mismatched variant numbers, filenames, and previous_version links in place."""
    active_entries = [e for e in entries if not e["delete"]]
    if not active_entries:
        return

    active_entries.sort(key=lambda e: e["variant_num"])
    first_entry = next(iter(active_entries))
    if first_entry["post"].metadata.get("source") == "manual":
        return

    base_stem = re.sub(r"(__v_\d+)+$", "", first_entry["stem"]).strip()
    base_fp = out_path / f"{base_stem}.md"
    if first_entry["stem"].lower() != base_stem.lower() and base_fp.exists() and unit_key:
        base_stem = sanitize_filename(f"{base_stem} ({unit_key})")

    for expected_num, entry in enumerate(active_entries, start=1):
        expected_stem = base_stem if expected_num == 1 else sanitize_filename(f"{base_stem}__v_{expected_num}")
        old_fp: Path = entry["file_path"]
        old_stem: str = entry["stem"]

        if entry["variant_num"] != expected_num:
            entry["variant_num"] = expected_num
            entry["dirty"] = True

        if entry["post"].metadata.get("title") != expected_stem:
            entry["post"].metadata["title"] = expected_stem
            entry["dirty"] = True

        if expected_num == 1:
            if "previous_version" in entry["post"].metadata:
                entry["post"].metadata.pop("previous_version", None)
                entry["dirty"] = True
        else:
            prev_stem = active_entries[expected_num - 2]["stem"]
            expected_link = f"[[{prev_stem}]]"
            if entry["post"].metadata.get("previous_version") != expected_link:
                entry["post"].metadata["previous_version"] = expected_link
                entry["dirty"] = True

        if old_stem != expected_stem:
            target_fp = out_path / f"{expected_stem}.md"
            if not target_fp.exists():
                if old_fp.exists():
                    os.replace(old_fp, target_fp)
                claimed_stems.discard(old_stem.lower())
                claimed_stems.add(expected_stem.lower())
                entry["file_path"] = target_fp
                entry["stem"] = expected_stem
                entry["dirty"] = True
                stats["synced"] += 1
                logger.info(f"Self-healed filename '{old_stem}.md' -> '{expected_stem}.md'")

def propagate_ingredient_bans(vault_foods: dict, logger: logging.Logger) -> None:
    """Recursively propagate ban_status='banned' from linked ingredients to parent foods."""
    # 1. Index all active/latest notes by lowercase stem and title for wiki-link resolution
    note_by_ref: dict[str, dict] = {}
    all_entries: list[dict] = []

    for entries in vault_foods.values():
        for entry in entries:
            if entry["delete"]:
                continue
            all_entries.append(entry)
            stem_key = entry["stem"].strip().lower()
            title_key = str(entry["post"].metadata.get("title", "")).strip().lower()
            note_by_ref[stem_key] = entry
            if title_key:
                note_by_ref[title_key] = entry

    def extract_link_targets(raw_ingredients) -> list[str]:
        if not raw_ingredients:
            return []
        items = raw_ingredients if isinstance(raw_ingredients, list) else [raw_ingredients]
        targets = []
        for item in items:
            text = str(item).strip()
            # Match [[Target]] or [[Target|Alias]]
            match = re.search(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", text)
            if match:
                targets.append(match.group(1).strip().lower())
            elif text:
                targets.append(text.lower())
        return targets

    # 2. Cycle-safe DFS to find the first banned ingredient in a food's dependency chain
    def find_banned_ancestor(entry: dict, visited: set[str]) -> str | None:
        stem_id = entry["stem"].lower()
        if stem_id in visited:
            return None
        visited.add(stem_id)

        for ref in extract_link_targets(entry["post"].metadata.get("ingredients")):
            ing_entry = note_by_ref.get(ref)
            if not ing_entry:
                continue
            ing_meta = ing_entry["post"].metadata
            if str(ing_meta.get("ban_status", "")).strip().lower() == "banned":
                return ing_entry["stem"]
            nested = find_banned_ancestor(ing_entry, visited)
            if nested:
                return nested
        return None

    # 3. Apply, override, or clear auto-propagated bans idempotently
    for entry in all_entries:
        meta = entry["post"].metadata
        raw_status = meta.get("ban_status")
        current_status = str(raw_status).strip().lower() if raw_status is not None else "unreviewed"

        raw_reason = meta.get("ban_reason")
        current_reason = str(raw_reason).strip() if raw_reason is not None else ""
        is_auto_reason = current_reason.startswith(("Contains [[", "Overrides [["))

        banned_ing = find_banned_ancestor(entry, set())

        if banned_ing:
            # User explicitly changed an auto-banned food to 'allowed' or 'override' -> honor as exception
            if current_status == "override" or (current_status == "allowed" and is_auto_reason):
                expected_reason = f"Overrides [[{banned_ing}]]"
                if current_status != "override" or current_reason != expected_reason:
                    meta["ban_status"] = "override"
                    meta["ban_reason"] = expected_reason
                    entry["dirty"] = True
                    logger.info(f"Marked '{entry['stem']}' as override ({expected_reason})")
                continue

            # Otherwise, enforce ingredient ban while stashing prior status
            expected_reason = f"Contains [[{banned_ing}]]"
            if "ban_status_prev" not in meta:
                meta["ban_status_prev"] = current_status

            should_update_reason = (not current_reason or is_auto_reason) and current_reason != expected_reason
            if current_status != "banned" or should_update_reason:
                meta["ban_status"] = "banned"
                if should_update_reason:
                    meta["ban_reason"] = expected_reason
                entry["dirty"] = True
                logger.info(f"Auto-banned '{entry['stem']}' ({expected_reason})")
        else:
            # No banned ingredients remain: restore stashed status or clean up overrides
            if current_status == "override":
                meta["ban_status"] = "allowed"
                meta.pop("ban_status_prev", None)
                if is_auto_reason:
                    meta.pop("ban_reason", None)
                entry["dirty"] = True
                logger.info(f"Cleaned up override on '{entry['stem']}' -> 'allowed'")
            elif current_status == "banned" and (is_auto_reason or "ban_status_prev" in meta):
                raw_prev = meta.pop("ban_status_prev", "unreviewed")
                restored = str(raw_prev).strip().lower() if raw_prev is not None else "unreviewed"
                meta["ban_status"] = restored if restored in {"allowed", "banned", "unreviewed"} else "unreviewed"
                if is_auto_reason:
                    meta.pop("ban_reason", None)
                entry["dirty"] = True
                logger.info(f"Restored '{entry['stem']}' to '{meta['ban_status']}'")

            
def sync_food_log(csv_path: str, output_dir: str, days: int | None = 7) -> dict[str, int]:
    out_path = Path(output_dir)
    logger = setup_logger(out_path)
    logger.info(f"Starting sync from '{csv_path}' (days={days})")

    vault_foods, alias_to_canonical, entries_by_stem = load_vault_state(out_path, logger)
    stats = {"synced": 0, "added": 0, "deleted": 0, "unlogged": 0, "errors": 0}

    claimed_stems: set[str] = {
        entry["stem"].lower()
        for entries in vault_foods.values()
        for entry in entries
    }

    # Execute declarative user directives first (duplicate_of, set_as_unique, set_as_only_version)
    apply_user_directives(
        vault_foods, entries_by_stem, alias_to_canonical, out_path, claimed_stems, stats, logger
    )

    IGNORED_NUTRIENT_KEYS = {"serving_weight_g"}

    with open(csv_path, mode="r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        csv_nutrient_keys = {
            to_snake_case(col)
            for col in (reader.fieldnames or [])
            if col not in EXCLUDED_COLS and col not in NON_NUTRIENT_COLS
        } - IGNORED_NUTRIENT_KEYS
        rows = list(reader)

    dated_rows = []
    for line_num, row in enumerate(rows, start=2):
        dt = parse_timestamp(row.get("Date", ""), row.get("Time", ""))
        dated_rows.append((dt, line_num, row))

    dated_rows.sort(key=lambda item: item[0])

    is_full_sync = days is None or days <= 0
    if not is_full_sync and dated_rows:
        latest_dt = dated_rows[-1][0]
        cutoff = latest_dt - timedelta(days=days)
        dated_rows = [(dt, ln, r) for dt, ln, r in dated_rows if dt >= cutoff]

    def is_qty_one(row: dict) -> bool:
        try:
            return math.isclose(float(row.get("Serving Qty", "1").strip() or 1.0), 1.0, abs_tol=1e-6)
        except ValueError:
            return False

    dated_rows.sort(key=lambda item: (not is_qty_one(item[2]), item[0]))
    seen_food_unit_keys: set[tuple[str, str]] = set()

    for dt, line_num, row in dated_rows:
        try:
            raw_name = row.get("Food Name", "").strip()
            if not raw_name or is_ignored_food(raw_name):
                continue

            raw_key = canonicalize_food_name(raw_name)
            new_profile, is_exact_unit = normalize_row(row, dt)
            unit_key = str(new_profile.get("serving_size", "")).strip().lower()

            # Check if an alias-linked food note (e.g., from set_as_unique or duplicate_of) already claims this row
            candidate_canonicals = [raw_key]
            if raw_key in alias_to_canonical and alias_to_canonical[raw_key] not in candidate_canonicals:
                candidate_canonicals.append(alias_to_canonical[raw_key])

            matched = False
            for ck in candidate_canonicals:
                gk = (ck, unit_key)
                variants = vault_foods.get(gk, [])
                for idx, v in enumerate(variants):
                    if v["delete"]:
                        continue

                    # Manual foods and final-pinned foods absorb matching rows without spawning variants
                    is_protected = (
                        v["post"].metadata.get("source") == "manual"
                        or v["post"].metadata.get("set_as_final_version") is True
                        or v["post"].metadata.get("set_as_only_version") is True
                    )
                    existing_is_exact = bool(v["post"].metadata.get("exact_unit_source", False))
                    loose = not (is_exact_unit and existing_is_exact)

                    if is_protected or profiles_match(v["post"].metadata, new_profile, csv_nutrient_keys, loose_rounding=loose):
                        seen_food_unit_keys.add(gk)
                        if (
                            not is_protected
                            and is_exact_unit
                            and not existing_is_exact
                        ):
                            preserved_meta = {
                                k: v["post"].metadata[k]
                                for k in (
                                    "title", "previous_version", "discovered", "aliases", "status",
                                    "banned", "ban_reason", "tags", "ingredients",
                                    "set_as_final_version", "set_as_only_version", "reviewed",
                                )
                                if k in v["post"].metadata
                            }
                            v["post"].metadata = order_metadata({**new_profile, **preserved_meta})
                            v["dirty"] = True

                        existing_name = str(v["post"].metadata.get("food_name", "")).strip()
                        if raw_name and raw_name.lower() != existing_name.lower():
                            aliases = list(v["post"].metadata.get("aliases") or [])
                            if raw_name not in aliases:
                                aliases.append(raw_name)
                                v["post"].metadata["aliases"] = aliases
                                v["dirty"] = True

                        if v["post"].metadata.get("version_status") == "unlogged":
                            v["post"].metadata["version_status"] = "latest"
                            v["dirty"] = True

                        matched = True
                        break
                if matched:
                    break

            if matched:
                continue

            canonical_key = alias_to_canonical.get(raw_key, raw_key)
            group_key = (canonical_key, unit_key)
            seen_food_unit_keys.add(group_key)
            existing_variants = [v for v in vault_foods.setdefault(group_key, []) if not v["delete"]]

            if not existing_variants:
                base_stem = sanitize_filename(raw_name)
                if base_stem.lower() in claimed_stems and unit_key:
                    note_title = f"{raw_name} ({unit_key})"
                else:
                    note_title = raw_name
                variant_num = 1
            else:
                prev = existing_variants[-1]
                base_stem = re.sub(r"(__v_\d+)+$", "", next(iter(existing_variants))["stem"]).strip()
                variant_num = prev["variant_num"] + 1
                note_title = f"{base_stem}__v_{variant_num}"
                new_profile["previous_version"] = f"[[{prev['stem']}]]"

                if prev["post"].metadata.get("version_status") not in {"previous", "unlogged"}:
                    prev["post"].metadata["version_status"] = "previous"
                    prev["dirty"] = True

            new_profile["title"] = note_title
            stem = sanitize_filename(note_title)
            claimed_stems.add(stem.lower())
            file_path = out_path / f"{stem}.md"

            post = frontmatter.Post(content="", **order_metadata(new_profile))
            vault_foods[group_key].append({
                "variant_num": variant_num,
                "file_path": file_path,
                "stem": stem,
                "canonical_key": canonical_key,
                "unit_key": unit_key,
                "post": post,
                "dirty": True,
                "delete": False,
            })
        except Exception as exc:
            stats["errors"] += 1
            logger.error(f"Quarantined malformed CSV row at line {line_num}: {exc}")

    # Two-way cleanup, retroactive deduplication, stem self-healing, and Obsidian Base review flagging
    for group_key, entries in vault_foods.items():
        canonical_key, unit_key = group_key
        consolidate_variants(entries, csv_nutrient_keys, logger)

        for entry in entries:
            if entry["delete"]:
                fp = entry["file_path"]
                if fp.exists():
                    fp.unlink()
                    claimed_stems.discard(entry["stem"].lower())
                    stats["deleted"] += 1
                    logger.info(f"Deleted variant '{fp.name}'")

        reconcile_variant_stems(entries, unit_key, out_path, claimed_stems, stats, logger)

        active_entries = [e for e in entries if not e["delete"]]
        if len(active_entries) <= 1:
            for e in active_entries:
                if e["post"].metadata.get("needs_review") or "review_reason" in e["post"].metadata:
                    e["post"].metadata["needs_review"] = False
                    e["post"].metadata.pop("review_reason", None)
                    e["dirty"] = True
        else:
            first_entry = next(iter(active_entries))
            base_meta = first_entry["post"].metadata
            for e in active_entries:
                if e is first_entry:
                    if e["post"].metadata.get("needs_review") or "review_reason" in e["post"].metadata:
                        e["post"].metadata["needs_review"] = False
                        e["post"].metadata.pop("review_reason", None)
                        e["dirty"] = True
                else:
                    reason = get_diff_reason(base_meta, e["post"].metadata, csv_nutrient_keys)
                    is_reviewed = e["post"].metadata.get("reviewed") is True
                    expected_needs_review = not is_reviewed

                    if (
                        e["post"].metadata.get("needs_review") is not expected_needs_review
                        or e["post"].metadata.get("review_reason") != reason
                    ):
                        e["post"].metadata["needs_review"] = expected_needs_review
                        e["post"].metadata["review_reason"] = reason
                        e["dirty"] = True

        # Soft-archive foods missing from CSV during a full-history sync
        if is_full_sync and group_key not in seen_food_unit_keys:
            for entry in entries:
                if not entry["delete"] and entry["post"].metadata.get("version_status") == "latest":
                    entry["post"].metadata["version_status"] = "unlogged"
                    entry["dirty"] = True
                    stats["unlogged"] += 1
                    logger.info(f"Marked unlogged food '{entry['stem']}'")

    # Propagate ingredient bans across all surviving notes before writing to disk
    propagate_ingredient_bans(vault_foods, logger)

    # Commit deletions and atomic writes
    for entries in vault_foods.values():
        for entry in entries:
            if entry["delete"] or not entry["dirty"]:
                continue

            fp = entry["file_path"]
            entry["post"].metadata = order_metadata(entry["post"].metadata)
            rendered = frontmatter.dumps(entry["post"]) + "\n"

            if not fp.exists():
                atomic_write_text(fp, rendered)
                stats["added"] += 1
                stats["synced"] += 1
                logger.info(f"Added '{fp.name}'")
            elif fp.read_text(encoding="utf-8") != rendered:
                atomic_write_text(fp, rendered)
                stats["synced"] += 1
                logger.info(f"Updated '{fp.name}'")

    logger.info(
        f"Sync complete — Synced: {stats['synced']} | Added: {stats['added']} | "
        f"Deleted: {stats['deleted']} | Unlogged: {stats['unlogged']} | Errors: {stats['errors']}"
    )
    return stats


def resolve_csv_path(cli_csv: str | None = None) -> Path:
    """Resolve CSV path via CLI argument, auto-discovery of newest MacroFactor-*.csv, or interactive prompt."""
    if cli_csv:
        p = Path(cli_csv.strip().strip('"').strip("'")).expanduser()
        if p.is_file():
            return p
        raise FileNotFoundError(f"Specified CSV file not found: {p}")

    # Search current working directory, script directory, and parent vault root
    search_dirs = [Path.cwd(), Path(__file__).resolve().parent, Path(__file__).resolve().parent.parent]
    candidates: list[Path] = []
    for d in search_dirs:
        if d.is_dir():
            candidates.extend(d.glob("MacroFactor-*.csv"))

    if candidates:
        # Pick the most recently modified MacroFactor export
        newest = max(set(candidates), key=lambda f: f.stat().st_mtime)
        print(f"Auto-detected latest MacroFactor export: {newest}")
        return newest

    # Interactive prompt fallback (supports dragging & dropping a file into the terminal)
    while True:
        raw_input_path = input("Drag & drop your MacroFactor CSV file here (or type path): ").strip()
        cleaned = raw_input_path.strip('"').strip("'").strip()
        if not cleaned:
            continue
        p = Path(cleaned).expanduser()
        if p.is_file():
            return p
        print(f"File not found: {p}. Please try again.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sync MacroFactor food log exports into normalized Obsidian Markdown notes."
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        default=None,
        help="Path to MacroFactor-*.csv export (auto-detects newest MacroFactor-*.csv if omitted)",
    )
    parser.add_argument(
        "--out",
        default="../../food-base",
        help="Output folder for food notes (default: ./food-base)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Only process entries from the last N days (skips unlogged archival)",
    )
    args = parser.parse_args()

    resolved_csv = resolve_csv_path(args.csv_path)
    out_dir = Path(args.out)

    stats = sync_food_log(str(resolved_csv), str(out_dir), days=args.days)
    print(
        f"[{out_dir.name}] Synced: {stats['synced']} | Added: {stats['added']} | "
        f"Deleted: {stats['deleted']} | Unlogged: {stats['unlogged']} | Errors: {stats['errors']}"
    )
