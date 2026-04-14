import csv
import io
import json
import os
from pathlib import Path
from typing import Any

from app.services.logging_service import get_logger

logger = get_logger()

OUTPUTS_DIR = Path("outputs")
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def generate_output(source_filename: str, field_values: dict[str, Any], output_format: str = "json") -> str:
    """Write the final output file and return its file path."""
    base = os.path.splitext(source_filename)[0]

    if output_format == "csv":
        output_path = OUTPUTS_DIR / f"{base}.csv"
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=",")
            keys = list(field_values.keys())
            vals = [str(field_values[k]).replace("\n", " ").replace("\r", " ") if field_values[k] is not None else "" for k in keys]
            writer.writerow(keys)
            writer.writerow(vals)
    else:
        output_path = OUTPUTS_DIR / f"{base}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(field_values, f, indent=2, default=str)

    logger.info(f"Output created: {output_path}")
    return str(output_path)


def get_output_path(source_filename: str, output_format: str = "json") -> Path:
    base = os.path.splitext(source_filename)[0]
    ext = "csv" if output_format == "csv" else "json"
    return OUTPUTS_DIR / f"{base}.{ext}"
