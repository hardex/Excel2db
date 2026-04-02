import openpyxl
from typing import Any

from app.models.schemas import FieldModel
from app.services.logging_service import get_logger

logger = get_logger()


def read_workbook_fields(file_path: str, fields: list[FieldModel]) -> dict[str, dict]:
    """Read raw values from an Excel workbook for the given fields.

    Uses data_only=False so formula cells return the formula string.
    """
    wb = openpyxl.load_workbook(file_path, data_only=False)
    logger.info("Workbook opened successfully")
    results: dict[str, dict] = {}

    for field in fields:
        if not field.active:
            continue
        sheet_name = field.sheet
        cell_addr = field.cell

        if sheet_name not in wb.sheetnames:
            results[field.field_code] = {
                "value": None,
                "error": f"Sheet '{sheet_name}' not found",
            }
            logger.warning(
                f"Read field: field_code={field.field_code}, sheet={sheet_name}, "
                f"cell={cell_addr} — sheet not found"
            )
            continue

        ws = wb[sheet_name]
        try:
            cell = ws[cell_addr]
            value = cell.value
            # Merged cells: openpyxl returns value from the top-left cell
            results[field.field_code] = {"value": value, "error": None}
            logger.info(
                f"Read field: field_code={field.field_code}, sheet={sheet_name}, cell={cell_addr}"
            )
        except Exception as exc:
            results[field.field_code] = {"value": None, "error": str(exc)}
            logger.warning(
                f"Read field: field_code={field.field_code}, sheet={sheet_name}, "
                f"cell={cell_addr} — error: {exc}"
            )

    wb.close()
    return results


def read_single_cell(file_path: str, sheet_name: str, cell_addr: str, raw: bool = True) -> dict:
    """Read a single cell value from a workbook (used by Test Cell feature).

    Args:
        raw: If True, read raw values (formulas as text). If False, read calculated values.
    """
    try:
        wb = openpyxl.load_workbook(file_path, data_only=not raw)
    except Exception as exc:
        return {"value": None, "error": f"Cannot open workbook: {exc}"}

    if sheet_name not in wb.sheetnames:
        wb.close()
        return {"value": None, "error": f"Sheet '{sheet_name}' not found. Available: {', '.join(wb.sheetnames)}"}

    ws = wb[sheet_name]
    try:
        cell = ws[cell_addr]
        value = cell.value
        wb.close()
        return {"value": value, "error": None}
    except Exception as exc:
        wb.close()
        return {"value": None, "error": str(exc)}


def get_sheet_names(file_path: str) -> list[str]:
    """Return list of sheet names from a workbook."""
    try:
        wb = openpyxl.load_workbook(file_path, data_only=False, read_only=True)
        names = list(wb.sheetnames)
        wb.close()
        return names
    except Exception:
        return []
