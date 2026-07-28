"""Download the frozen translator once or run the synthetic Day 10 sheet offline."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if __package__:
    from scripts.bilingual_inference import (
        CHECKPOINT,
        CHECKPOINT_REVISION,
        BilingualInference,
        FrozenClassifier,
        OfflineTranslator,
        default_cache_dir,
        directory_size,
        run_synthetic_sheet,
    )
else:
    from bilingual_inference import (  # type: ignore[no-redef]
        CHECKPOINT,
        CHECKPOINT_REVISION,
        BilingualInference,
        FrozenClassifier,
        OfflineTranslator,
        default_cache_dir,
        directory_size,
        run_synthetic_sheet,
    )

MAX_CACHE_BYTES = 400_000_000


def download_checkpoint(cache_dir: Path) -> dict[str, object]:
    """Download only files required by AutoTokenizer and PyTorch AutoModel."""
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    cache_dir.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(
        CHECKPOINT,
        revision=CHECKPOINT_REVISION,
        cache_dir=cache_dir,
        local_files_only=False,
    )
    model = AutoModelForSeq2SeqLM.from_pretrained(
        CHECKPOINT,
        revision=CHECKPOINT_REVISION,
        cache_dir=cache_dir,
        local_files_only=False,
        use_safetensors=False,
    )
    del tokenizer
    del model
    size = directory_size(cache_dir)
    if size > MAX_CACHE_BYTES:
        raise RuntimeError(
            f"translation cache uses {size} bytes, above the 400 MB limit"
        )
    offline = OfflineTranslator(cache_dir)
    return {
        "checkpoint": CHECKPOINT,
        "revision": CHECKPOINT_REVISION,
        "cache_size_bytes": size,
        "offline_load_verified": True,
        "cold_load_seconds": offline.cold_load_seconds,
    }


def run_validation(
    cache_dir: Path, classifier_path: Path, cases_path: Path, output_path: Path
) -> dict[str, object]:
    """Load both frozen artifacts offline and publish the synthetic sheet."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        raise TypeError("synthetic test cases must be a JSON array")
    classifier = FrozenClassifier.load(classifier_path)
    translator = OfflineTranslator(cache_dir)
    pipeline = BilingualInference(classifier, translator)
    return run_synthetic_sheet(
        cases,
        pipeline,
        output_path,
        checkpoint_cache_size_bytes=directory_size(cache_dir),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    download = subparsers.add_parser("download")
    download.add_argument("--cache-dir", type=Path, default=default_cache_dir())
    validate = subparsers.add_parser("validate")
    validate.add_argument("--cache-dir", type=Path, default=default_cache_dir())
    validate.add_argument("--classifier", required=True, type=Path)
    validate.add_argument("--cases", required=True, type=Path)
    validate.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "download":
            result = download_checkpoint(args.cache_dir)
            print(json.dumps(result, indent=2))
        else:
            result = run_validation(
                args.cache_dir,
                args.classifier,
                args.cases,
                args.output,
            )
            print(
                f"Day 10 sheet generated: cases={result['case_count']} "
                f"classification_correct={result['classification']['correct']} "
                "translation_review=pending_owner_review"
            )
    except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Day 10 command failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
