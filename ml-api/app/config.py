"""Configuration for the local ComplaintGuard ML API."""

from dataclasses import dataclass
from pathlib import Path

MODEL_SHA256 = "bafc086fe5b11bdcc5cbc4f04f3f3f222de8cbad27fe66d62a6685cc30f953d5"
MODEL_VERSION = "v1"
MAX_COMPLAINT_LENGTH = 5_000


@dataclass(frozen=True)
class Settings:
    """Runtime settings that never expose local paths through API responses."""

    model_path: Path
    expected_model_sha256: str = MODEL_SHA256

    @classmethod
    def default(cls) -> "Settings":
        repository_root = Path(__file__).resolve().parents[2]
        return cls(
            model_path=repository_root
            / "models"
            / "generated"
            / "cfpb_department_model_v1.joblib"
        )
