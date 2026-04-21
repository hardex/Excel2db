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


def _validate_label(field: FieldModel, label_value: Any) -> str | None:
    """Label rule: empty label in file → valid. Mismatch → invalid."""
    fn = field.field_name.strip()
    fnc = field.field_name_cell.strip()
    if not fnc or not fn or label_value is None:
        return None
    actual = str(label_value).strip()
    if not actual:
        return None
    if actual == fn:
        return None
    return f"Label mismatch at {fnc}: expected '{fn}', got '{actual}'"


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
        # raw may be a dict with {"value": ..., "values": [...], "error": ..., "label_value": ...} or a plain value
        label_value = None
        values_list: list | None = None
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
            label_value = raw.get("label_value")
            values_list = raw.get("values")
        else:
            value = raw

        # Multi-cell reads: validate each cell individually so a comma-joined
        # string like "208, , 205, , 0.5" doesn't fail the scalar regex.
        if values_list is not None and len(values_list) > 1:
            value_err = None
            for v in values_list:
                e = _validate_field(field, v)
                if e:
                    value_err = e
                    break
        else:
            value_err = _validate_field(field, value)
        label_err = _validate_label(field, label_value)

        combined: str | None
        if value_err and label_err:
            combined = f"{label_err}; {value_err}"
        elif value_err:
            combined = value_err
        elif label_err:
            combined = label_err
        else:
            combined = None

        if combined:
            errors[field.field_code] = combined
            logger.warning(
                f"Validation failed: field_code={field.field_code}, "
                f"rule={field.value_type}/allow_empty={field.allow_empty}, "
                f"value={value!r}, label_value={label_value!r}"
            )
    return errors
