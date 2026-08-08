"""Configuration for the local ComplaintGuard ML API."""

import os
from dataclasses import dataclass
from pathlib import Path

MODEL_SHA256 = "bafc086fe5b11bdcc5cbc4f04f3f3f222de8cbad27fe66d62a6685cc30f953d5"
MODEL_VERSION = "v1"
MAX_COMPLAINT_LENGTH = 5_000
DEFAULT_ROUTING_CONFIDENCE_THRESHOLD = 0.60


@dataclass(frozen=True)
class Settings:
    """Runtime settings that never expose local paths through API responses."""

    model_path: Path
    expected_model_sha256: str = MODEL_SHA256
    routing_confidence_threshold: float = DEFAULT_ROUTING_CONFIDENCE_THRESHOLD
    allowed_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )

    @classmethod
    def default(cls) -> "Settings":
        repository_root = Path(__file__).resolve().parents[2]
        threshold = float(
            os.getenv(
                "ROUTING_CONFIDENCE_THRESHOLD",
                str(DEFAULT_ROUTING_CONFIDENCE_THRESHOLD),
            )
        )
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("ROUTING_CONFIDENCE_THRESHOLD must be between 0 and 1")
        return cls(
            model_path=repository_root
            / "models"
            / "generated"
            / "cfpb_department_model_v1.joblib",
            routing_confidence_threshold=threshold,
            allowed_origins=tuple(
                origin.strip()
                for origin in os.getenv(
                    "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
                ).split(",")
                if origin.strip()
            ),
        )
