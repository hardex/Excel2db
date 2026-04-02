import re
from datetime import datetime
from typing import Any

from app.models.schemas import FieldModel
from app.services.logging_service import get_logger

logger = get_logger()

# Valid number pattern: 123, -123, 1234.56, 1,234.56, -1,234.56
NUMBER_RE = re.compile(r"^-?(\d{1,3}(,\d{3})*|\d+)(\.\d+)?$")

# Date text formats (in priority order)
DATE_FORMATS = [
    "%Y-%m-%d",   # YYYY-MM-DD
    "%d.%m.%Y",   # DD.MM.YYYY
    "%m/%d/%Y",   # MM/DD/YYYY  (default for ambiguous slash dates)
    "%d/%m/%Y",   # DD/MM/YYYY  (tried second for slash dates)
]


def _validate_field(field: FieldModel, value: Any) -> str | None:
    """Return an error message string, or None if valid."""
    # 1. Empty check
    if not field.allow_empty:
        if value is None or value == "":
            return "Field is required (empty value not allowed)"

    # If value is None or empty and allow_empty is True, skip further checks
    if value is None or value == "":
        return None

    # 2. Type validation
    if field.value_type == "number":
        return _validate_number(value)
    elif field.value_type == "date":
        return _validate_date(value)
    # string: always valid (only allow_empty applies)
    return None


def _validate_number(value: Any) -> str | None:
    """Return error string or None."""
    str_val = str(value)
    if NUMBER_RE.match(str_val):
        return None
    return f"Invalid number format: '{str_val}'. Expected formats: 123, -123, 1234.56, 1,234.56"


def _validate_date(value: Any) -> str | None:
    """Return error string or None."""
    # Native datetime object from openpyxl
    if isinstance(value, datetime):
        return None
    # Try parsing as text
    str_val = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            datetime.strptime(str_val, fmt)
            return None
        except ValueError:
            continue
    return (
        f"Invalid date format: '{str_val}'. "
        "Expected: YYYY-MM-DD, DD.MM.YYYY, MM/DD/YYYY, or a native Excel date"
    )


def validate_fields(
    fields: list[FieldModel],
    extracted: dict[str, Any],
) -> dict[str, str]:
    """Validate all active fields. Returns {field_code: error_message} for failures."""
    errors: dict[str, str] = {}
    for field in fields:
        if not field.active:
            continue
        raw = extracted.get(field.field_code, {})
        # raw may be a dict with {"value": ..., "error": ...} or a plain value
        if isinstance(raw, dict):
            read_error = raw.get("error")
            if read_error:
                errors[field.field_code] = f"Read error: {read_error}"
                logger.warning(
                    f"Validation failed: field_code={field.field_code}, "
                    f"rule=read_error, value={raw.get('value')}"
                )
                continue
            value = raw.get("value")
        else:
            value = raw

        err = _validate_field(field, value)
        if err:
            errors[field.field_code] = err
            logger.warning(
                f"Validation failed: field_code={field.field_code}, "
                f"rule={field.value_type}/allow_empty={field.allow_empty}, value={value!r}"
            )
    return errors
