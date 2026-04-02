import json
import os
from pathlib import Path
from typing import Any

from app.services.logging_service import get_logger

logger = get_logger()

OUTPUTS_DIR = Path("outputs")
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def generate_output(source_filename: str, field_values: dict[str, Any]) -> str:
    """Write the final output JSON and return its file path."""
    base = os.path.splitext(source_filename)[0]
    output_path = OUTPUTS_DIR / f"{base}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(field_values, f, indent=2, default=str)
    logger.info(f"Output created: {output_path}")
    return str(output_path)


def get_output_path(source_filename: str) -> Path:
    base = os.path.splitext(source_filename)[0]
    return OUTPUTS_DIR / f"{base}.json"
