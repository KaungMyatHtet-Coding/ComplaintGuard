"""Privacy-safe V2 corpus preparation; publishes aggregate evidence only."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

SOURCE_TYPES = ("real_public", "translated", "synthetic")
LANGUAGES = ("myanmar", "english", "mixed")
SPLITS = (("train", 70), ("calibration", 10), ("validation", 10), ("held_out", 10))
EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d(). -]{5,}\d)(?!\w)")
LONG_NUMBER = re.compile(r"(?<!\d)\d(?:[ -]?\d){8,}(?!\d)")
WHITESPACE = re.compile(r"\s+")


def normalize_and_redact(text: str) -> tuple[str, set[str]]:
    value = unicodedata.normalize("NFKC", text)
    markers: set[str] = set()
    value, count = EMAIL.subn("[REDACTED_EMAIL]", value)
    if count:
        markers.add("email")
    phone_count = 0
    def redact_phone(match: re.Match[str]) -> str:
        nonlocal phone_count
        candidate = match.group()
        if not any(character in candidate for character in "+()-"):
            return candidate
        phone_count += 1
        return "[REDACTED_PHONE]"
    value = PHONE.sub(redact_phone, value)
    if phone_count:
        markers.add("phone")
    value, count = LONG_NUMBER.subn("[REDACTED_NUMBER]", value)
    if count:
        markers.add("long_number")
    return WHITESPACE.sub(" ", value).strip(), markers


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.casefold().encode("utf-8")).hexdigest()


def _split(group_fingerprint: str) -> str:
    bucket = int(group_fingerprint[:8], 16) % 100
    total = 0
    for name, weight in SPLITS:
        total += weight
        if bucket < total:
            return name
    raise AssertionError("split weights must total 100")


def prepare(records: list[dict], taxonomy: dict, near_threshold: float = 0.90) -> dict:
    ids = tuple(taxonomy["category_ids"])
    if tuple(taxonomy["categories"]) != ids or len(set(ids)) != 8:
        raise ValueError("taxonomy IDs/order are not the frozen eight-category contract")
    cleaned = []
    for record in records:
        source = record.get("source_type")
        language = record.get("language")
        category = record.get("category_id")
        if source not in SOURCE_TYPES or language not in LANGUAGES or category not in ids:
            raise ValueError("record metadata is outside the V2 allowlists")
        if not record.get("source_reference") or not record.get("source_license"):
            raise ValueError("source reference and license/consent metadata are required")
        text, markers = normalize_and_redact(str(record.get("text", "")))
        if not text:
            raise ValueError("record text is empty after normalization")
        cleaned.append({**record, "text": text, "markers": markers, "fingerprint": _fingerprint(text)})

    parent = list(range(len(cleaned)))
    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def union(a: int, b: int) -> None:
        ra, rb = root(a), root(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    exact_pairs = near_pairs = 0
    for i in range(len(cleaned)):
        for j in range(i):
            if cleaned[i]["fingerprint"] == cleaned[j]["fingerprint"]:
                exact_pairs += 1
                union(i, j)
            elif SequenceMatcher(None, cleaned[i]["text"].casefold(), cleaned[j]["text"].casefold()).ratio() >= near_threshold:
                near_pairs += 1
                union(i, j)

    groups: dict[int, list[int]] = {}
    for index in range(len(cleaned)):
        groups.setdefault(root(index), []).append(index)
    split_by_index = {}
    for members in groups.values():
        group_hash = min(cleaned[index]["fingerprint"] for index in members)
        split = _split(group_hash)
        split_by_index.update({index: split for index in members})

    counts = lambda key, values: dict(sorted(Counter(row[key] for row in values).items()))
    split_counts = Counter(split_by_index.values())
    cross_split_groups = sum(len({split_by_index[i] for i in members}) > 1 for members in groups.values())
    return {
        "manifest_schema_version": 1,
        "dataset_version": "dataset_v2",
        "mapping_version": "mapping_v2",
        "taxonomy_version": taxonomy["taxonomy_version"],
        "automatic_routing_enabled": False,
        "record_count": len(cleaned),
        "counts_by_source_type": counts("source_type", cleaned),
        "counts_by_language": counts("language", cleaned),
        "counts_by_category": counts("category_id", cleaned),
        "counts_by_split": {name: split_counts[name] for name, _ in SPLITS},
        "privacy": {"unicode_normalization": "NFKC", "redacted_record_count": sum(bool(row["markers"]) for row in cleaned), "redaction_marker_counts": dict(sorted(Counter(marker for row in cleaned for marker in row["markers"]).items())), "raw_text_published": False},
        "duplicates": {"comparison": "normalized casefolded text; SequenceMatcher ratio", "near_duplicate_threshold": near_threshold, "exact_duplicate_pairs": exact_pairs, "near_duplicate_pairs": near_pairs, "duplicate_groups": sum(len(v) > 1 for v in groups.values()), "cross_split_groups": cross_split_groups, "checked_before_partitioning": True},
        "partitioning": {"method": "duplicate-group SHA-256 modulo 100", "weights": dict(SPLITS), "seed": "content-addressed-v2", "locked": True},
        "source_inventory": [{"source_type": source, "record_count": sum(row["source_type"] == source for row in cleaned), "classification": "real" if source == "real_public" else f"{source}_not_real"} for source in SOURCE_TYPES],
        "text_or_identifiers_in_manifest": False
    }


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True, help="Privacy-reviewed JSONL; never published by this script")
    parser.add_argument("--taxonomy", type=Path, default=Path("data/mapping/myanmar_banking_taxonomy_v2.json"))
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if args.manifest.exists():
        raise FileExistsError("refusing to overwrite an existing manifest")
    report = prepare(load_jsonl(args.input), json.loads(args.taxonomy.read_text(encoding="utf-8")))
    args.manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
