from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.prepare_v2_dataset import normalize_and_redact, prepare

TAXONOMY_PATH = Path("data/mapping/myanmar_banking_taxonomy_v2.json")


def taxonomy() -> dict:
    return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))


def record(case: str, text: str, source: str, language: str, category: str) -> dict:
    return {"case_id": case, "text": text, "source_type": source, "language": language, "category_id": category, "source_reference": "controlled-test-fixture", "source_license": "owner-authored-synthetic"}


def test_taxonomy_freezes_eight_bilingual_categories_and_guidance() -> None:
    value = taxonomy()
    assert value["status"] == "frozen_provisional"
    assert value["automatic_routing_enabled"] is False
    assert len(value["category_ids"]) == len(set(value["category_ids"])) == 8
    for category_id in value["category_ids"]:
        category = value["categories"][category_id]
        assert all(category[key] for key in ("name_en", "name_my", "definition_en", "definition_my", "include", "exclude", "examples"))
    assert value["ambiguity_guidance"]


def test_normalization_and_redaction_cover_unicode_and_identifiers() -> None:
    text, markers = normalize_and_redact("ＡＢＣ me@example.com; call +95 (9) 123-4567; account 123456789012")
    assert text.startswith("ABC ")
    assert "example.com" not in text and "912345678" not in text and "123456789012" not in text
    assert markers == {"email", "phone", "long_number"}


def test_duplicate_groups_are_detected_before_and_never_cross_splits() -> None:
    rows = [
        record("s1", "My transfer is pending", "synthetic", "english", "transfers_payments_remittance"),
        record("s2", "My transfer is pending", "synthetic", "english", "transfers_payments_remittance"),
        record("t1", "My transfer is still pending", "translated", "mixed", "transfers_payments_remittance"),
        record("r1", "အကောင့် ဖွင့်မရပါ", "real_public", "myanmar", "account_branch_services"),
    ]
    manifest = prepare(rows, taxonomy(), near_threshold=0.80)
    assert manifest["duplicates"]["checked_before_partitioning"] is True
    assert manifest["duplicates"]["exact_duplicate_pairs"] == 1
    assert manifest["duplicates"]["near_duplicate_pairs"] >= 1
    assert manifest["duplicates"]["cross_split_groups"] == 0
    assert manifest["record_count"] == sum(manifest["counts_by_split"].values())
    assert manifest["counts_by_source_type"] == {"real_public": 1, "synthetic": 2, "translated": 1}
    serialized = json.dumps(manifest, ensure_ascii=False)
    assert "My transfer" not in serialized and "အကောင့်" not in serialized


def test_partitioning_is_reproducible_and_metadata_is_required() -> None:
    rows = [record("s1", "Synthetic card complaint", "synthetic", "english", "cards_atm_pos")]
    assert prepare(rows, taxonomy()) == prepare(rows, taxonomy())
    del rows[0]["source_license"]
    with pytest.raises(ValueError, match="license"):
        prepare(rows, taxonomy())


def test_unknown_labels_languages_and_sources_fail_closed() -> None:
    base = record("s1", "Synthetic complaint", "synthetic", "english", "general_complaints")
    for key, value in (("category_id", "v1_label"), ("language", "unknown"), ("source_type", "customer")):
        invalid = {**base, key: value}
        with pytest.raises(ValueError, match="allowlists"):
            prepare([invalid], taxonomy())
