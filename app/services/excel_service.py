import openpyxl
from typing import Any

from app.models.schemas import FieldModel
from app.services.logging_service import get_logger

logger = get_logger()


def read_workbook_fields(file_path: str, fields: list[FieldModel]) -> dict[str, dict]:
    """Read values from an Excel workbook for the given fields.

    Each field's raw_cell_value flag controls whether to read raw (formulas as
    text) or calculated values.  The workbook is opened in both modes only when
    needed.
    """
    active_fields = [f for f in fields if f.active]
    needs_raw = any(f.raw_cell_value for f in active_fields)
    needs_calc = any(not f.raw_cell_value for f in active_fields)

    wb_raw = openpyxl.load_workbook(file_path, data_only=False) if needs_raw else None
    wb_calc = openpyxl.load_workbook(file_path, data_only=True) if needs_calc else None
    logger.info("Workbook opened successfully")

    results: dict[str, dict] = {}

    for field in active_fields:
        sheet_name = field.sheet
        cell_addr = field.cell
        wb = wb_raw if field.raw_cell_value else wb_calc

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
            results[field.field_code] = {"value": value, "error": None}
            logger.info(
                f"Read field: field_code={field.field_code}, sheet={sheet_name}, "
                f"cell={cell_addr}, raw={field.raw_cell_value}"
            )
        except Exception as exc:
            results[field.field_code] = {"value": None, "error": str(exc)}
            logger.warning(
                f"Read field: field_code={field.field_code}, sheet={sheet_name}, "
                f"cell={cell_addr} — error: {exc}"
            )

    if wb_raw:
        wb_raw.close()
    if wb_calc:
        wb_calc.close()
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
