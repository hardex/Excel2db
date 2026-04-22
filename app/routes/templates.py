import re
import urllib.parse
import json
from pathlib import Path

from fastapi import APIRouter, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.models.schemas import FieldModel, TemplateModel
from app.services import (
    list_templates,
    get_template,
    save_template,
    delete_template,
    set_default_template,
    template_exists,
    read_single_cell,
    get_logger,
    template_to_stage2,
    export_to_file,
)

router = APIRouter(prefix="/templates", tags=["templates"])
templates_engine = Jinja2Templates(directory="app/templates")
logger = get_logger()

UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


# ─── Helpers ────────────────────────────────────────────────────────────────

# `template_code` and `template_version` are used both as filename segments
# (mappings/{code}_{version}.json) and as URL path parameters, so they must
# not contain path separators, NUL, or newlines.
_INVALID_NAME_RE = re.compile(r"[\\/\x00\r\n]")

# Extensions openpyxl can read. xlsm is the same Open-XML container as xlsx
# plus a macro stream that is ignored on read.
EXCEL_EXTS = (".xlsx", ".xlsm")


def _is_excel_filename(name: str) -> bool:
    return bool(name) and name.lower().endswith(EXCEL_EXTS)


def _excel_ext(name: str) -> str:
    """Return the lowercase Excel extension of `name` (xlsx or xlsm),
    defaulting to .xlsx when the caller forgot to validate first."""
    suffix = Path(name or "").suffix.lower()
    return suffix if suffix in EXCEL_EXTS else ".xlsx"


def _validate_template_identifiers(code: str, version: str) -> str | None:
    """Return a user-facing error message, or None if valid."""
    if _INVALID_NAME_RE.search(code):
        return "Template code must not contain \\, /, or newline characters"
    if _INVALID_NAME_RE.search(version):
        return "Template version must not contain \\, /, or newline characters"
    return None


def _redirect(url: str, msg: str = "", msg_type: str = "success") -> RedirectResponse:
    sep = "&" if "?" in url else "?"
    if msg:
        encoded = urllib.parse.quote(msg)
        url = f"{url}{sep}msg={encoded}&msg_type={msg_type}"
    return RedirectResponse(url=url, status_code=303)


def _parse_fields_from_form(form: dict) -> list[FieldModel]:
    """Extract fields list from a flat form POST (field_code_0, field_name_0, …)."""
    fields: list[FieldModel] = []
    index = 0
    while True:
        fc = form.get(f"field_code_{index}")
        if fc is None:
            break
        fields.append(
            FieldModel(
                field_code=str(fc).strip(),
                field_name=str(form.get(f"field_name_{index}", "")).strip(),
                field_name_cell=str(form.get(f"field_name_cell_{index}", "")).strip(),
                sheet=str(form.get(f"sheet_{index}", "")).strip(),
                cell=str(form.get(f"cell_{index}", "")).strip(),
                value_type=str(form.get(f"value_type_{index}", "string")).strip(),
                allow_empty=form.get(f"allow_empty_{index}") in ("on", "true", "1", True),
                active=form.get(f"active_{index}") in ("on", "true", "1", True),
                raw_cell_value=form.get(f"raw_cell_value_{index}") in ("on", "true", "1", True),
                description=str(form.get(f"description_{index}", "")).strip(),
                ai_prompt=str(form.get(f"ai_prompt_{index}", "")).strip(),
            )
        )
        index += 1
    return fields


# ─── Routes ─────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def template_list(request: Request):
    all_templates = list_templates()
    msg = request.query_params.get("msg", "")
    msg_type = request.query_params.get("msg_type", "success")
    return templates_engine.TemplateResponse(
        request,
        "template_list.html",
        {
            "templates": all_templates,
            "msg": msg,
            "msg_type": msg_type,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def template_new_form(request: Request):
    msg = request.query_params.get("msg", "")
    msg_type = request.query_params.get("msg_type", "error")
    return templates_engine.TemplateResponse(
        request,
        "template_edit.html",
        {
            "template": None,
            "template_fields_json": [],
            "is_new": True,
            "msg": msg,
            "msg_type": msg_type,
            "test_file_available": False,
            "test_result": None,
            "test_error": None,
        },
    )


@router.post("/new")
async def template_new_submit(request: Request):
    form = await request.form()
    form_dict = dict(form)

    template_code = str(form_dict.get("template_code", "")).strip()
    template_version = str(form_dict.get("template_version", "")).strip()

    if not template_code or not template_version:
        return _redirect("/templates/new", "Template code and version are required", "error")

    bad = _validate_template_identifiers(template_code, template_version)
    if bad:
        return _redirect("/templates/new", bad, "error")

    if template_exists(template_code, template_version):
        return _redirect(
            "/templates/new",
            f"Template {template_code}_{template_version} already exists",
            "error",
        )

    fields = _parse_fields_from_form(form_dict)

    test_file_path = str(form_dict.get("test_file_path", "")).strip()

    # Save uploaded test file if provided
    test_file = form_dict.get("test_file")
    if test_file and hasattr(test_file, "filename") and _is_excel_filename(test_file.filename or ""):
        ext = _excel_ext(test_file.filename)
        saved_path = UPLOADS_DIR / f"test_{template_code}_{template_version}{ext}"
        content = await test_file.read()
        with open(saved_path, "wb") as f_out:
            f_out.write(content)
        test_file_path = str(saved_path.resolve())

    # Determine if this should be default
    all_tmpl = list_templates()
    is_default = form_dict.get("is_default") in ("on", "true", "1") or len(all_tmpl) == 0

    tmpl = TemplateModel(
        template_code=template_code,
        template_version=template_version,
        description=str(form_dict.get("description", "")).strip(),
        is_default=is_default,
        test_file_path=test_file_path,
        version_cell_sheet=str(form_dict.get("version_cell_sheet", "")).strip(),
        version_cell=str(form_dict.get("version_cell", "")).strip(),
        model_version=str(form_dict.get("model_version", "")).strip(),
        fields=fields,
    )

    if is_default:
        # Clear default from others first
        for t in all_tmpl:
            if t.is_default:
                t.is_default = False
                save_template(t)

    save_template(tmpl)
    logger.info(f"Template created: {template_code}_{template_version}")
    return _redirect("/templates", f"Template {template_code} {template_version} created successfully")


@router.get("/{code}/{version}/edit", response_class=HTMLResponse)
async def template_edit_form(request: Request, code: str, version: str):
    tmpl = get_template(code, version)
    if not tmpl:
        return _redirect("/templates", f"Template {code}_{version} not found", "error")
    msg = request.query_params.get("msg", "")
    msg_type = request.query_params.get("msg_type", "success")
    test_result = request.query_params.get("test_result", None)
    test_error = request.query_params.get("test_error", None)
    test_file_available = bool(tmpl.test_file_path and Path(tmpl.test_file_path).exists())
    return templates_engine.TemplateResponse(
        request,
        "template_edit.html",
        {
            "template": tmpl,
            "template_fields_json": [f.model_dump() for f in tmpl.fields],
            "is_new": False,
            "msg": msg,
            "msg_type": msg_type,
            "test_file_available": test_file_available,
            "test_result": test_result,
            "test_error": test_error,
        },
    )


@router.post("/{code}/{version}/edit")
async def template_edit_submit(request: Request, code: str, version: str):
    existing = get_template(code, version)
    if not existing:
        return _redirect("/templates", f"Template {code}_{version} not found", "error")

    form = await request.form()
    form_dict = dict(form)

    new_code = str(form_dict.get("template_code", code)).strip()
    new_version = str(form_dict.get("template_version", version)).strip()

    if not new_code or not new_version:
        return _redirect(
            f"/templates/{code}/{version}/edit",
            "Template code and version are required",
            "error",
        )

    bad = _validate_template_identifiers(new_code, new_version)
    if bad:
        return _redirect(f"/templates/{code}/{version}/edit", bad, "error")

    code_changed = new_code != code or new_version != version

    # If code/version changed, check the new name doesn't already exist
    if code_changed and template_exists(new_code, new_version):
        return _redirect(
            f"/templates/{code}/{version}/edit",
            f"Template {new_code}_{new_version} already exists",
            "error",
        )

    fields = _parse_fields_from_form(form_dict)
    is_default = form_dict.get("is_default") in ("on", "true", "1")

    test_file_path = str(form_dict.get("test_file_path", "")).strip()
    if not test_file_path:
        test_file_path = existing.test_file_path

    # Save uploaded test file if provided
    test_file = form_dict.get("test_file")
    if test_file and hasattr(test_file, "filename") and _is_excel_filename(test_file.filename or ""):
        ext = _excel_ext(test_file.filename)
        saved_path = UPLOADS_DIR / f"test_{new_code}_{new_version}{ext}"
        content = await test_file.read()
        with open(saved_path, "wb") as f_out:
            f_out.write(content)
        test_file_path = str(saved_path.resolve())

    updated = TemplateModel(
        template_code=new_code,
        template_version=new_version,
        description=str(form_dict.get("description", "")).strip(),
        is_default=is_default,
        test_file_path=test_file_path,
        version_cell_sheet=str(form_dict.get("version_cell_sheet", "")).strip(),
        version_cell=str(form_dict.get("version_cell", "")).strip(),
        model_version=str(form_dict.get("model_version", "")).strip(),
        fields=fields,
    )

    if is_default:
        all_tmpl = list_templates()
        for t in all_tmpl:
            if t.is_default and not (t.template_code == new_code and t.template_version == new_version):
                t.is_default = False
                save_template(t)

    save_template(updated)

    if code_changed:
        logger.info(f"Template saved as new: {new_code}_{new_version} (from {code}_{version})")
    else:
        logger.info(f"Template updated: {new_code}_{new_version}")

    return _redirect(
        f"/templates/{new_code}/{new_version}/edit",
        "Template saved successfully",
        "success",
    )


@router.post("/{code}/{version}/delete")
async def template_delete(code: str, version: str):
    deleted = delete_template(code, version)
    if deleted:
        logger.info(f"Template deleted: {code}_{version}")
        return _redirect("/templates", f"Template {code} {version} deleted")
    return _redirect("/templates", f"Template {code}_{version} not found", "error")


@router.post("/{code}/{version}/set-default")
async def template_set_default(code: str, version: str):
    tmpl = get_template(code, version)
    if not tmpl:
        return _redirect("/templates", f"Template {code}_{version} not found", "error")
    set_default_template(code, version)
    logger.info(f"Default template set: {code}_{version}")
    return _redirect("/templates", f"Template {code} {version} set as default")


@router.post("/test-cell")
async def test_cell(
    request: Request,
    file: UploadFile = File(...),
    sheet: str = Form(...),
    cell: str = Form(...),
    template_code: str = Form(""),
    template_version: str = Form(""),
):
    """Read a single cell from an uploaded test file and redirect back to the editor."""
    if not _is_excel_filename(file.filename or ""):
        msg = "Only .xlsx/.xlsm files are accepted for cell testing"
        if template_code and template_version:
            return _redirect(
                f"/templates/{template_code}/{template_version}/edit",
                msg,
                "error",
            )
        return _redirect("/templates/new", msg, "error")

    # Save temp file
    temp_path = UPLOADS_DIR / f"_test_{file.filename}"
    with open(temp_path, "wb") as f_out:
        content = await file.read()
        f_out.write(content)

    result = read_single_cell(str(temp_path), sheet.strip(), cell.strip().upper())

    # Clean up temp file
    try:
        temp_path.unlink()
    except Exception:
        pass

    if template_code and template_version:
        base = f"/templates/{template_code}/{template_version}/edit"
    else:
        base = "/templates/new"

    if result["error"]:
        err_enc = urllib.parse.quote(str(result["error"]))
        return RedirectResponse(url=f"{base}?test_error={err_enc}", status_code=303)
    else:
        val = result["value"]
        display = str(val) if val is not None else "(empty)"
        val_enc = urllib.parse.quote(display)
        return RedirectResponse(url=f"{base}?test_result={val_enc}", status_code=303)


@router.post("/upload-test-file")
async def upload_test_file(
    file: UploadFile = File(...),
    template_code: str = Form(""),
    template_version: str = Form(""),
):
    """AJAX endpoint: upload test file and return its saved path."""
    if not _is_excel_filename(file.filename or ""):
        return JSONResponse({"ok": False, "error": "Only .xlsx/.xlsm files are accepted"})

    code = template_code.strip() or "unsaved"
    ver = template_version.strip() or "draft"
    ext = _excel_ext(file.filename)
    saved_path = UPLOADS_DIR / f"test_{code}_{ver}{ext}"
    content = await file.read()
    with open(saved_path, "wb") as f_out:
        f_out.write(content)
    return JSONResponse({"ok": True, "path": str(saved_path.resolve())})


@router.post("/check-file")
async def check_file(request: Request):
    data = await request.json()
    file_path = data.get("path", "").strip()
    if not file_path:
        return JSONResponse({"exists": False})
    return JSONResponse({"exists": Path(file_path).exists()})


@router.post("/check-cell")
async def check_cell(
    file: UploadFile = File(None),
    sheet: str = Form(...),
    cell: str = Form(...),
    value_type: str = Form("string"),
    allow_empty: str = Form("false"),
    raw: str = Form("true"),
    stored_test_file: str = Form(""),
    field_name: str = Form(""),
    field_name_cell: str = Form(""),
):
    """AJAX endpoint: mirrors the AI prompt checks.

    1) If `field_name_cell` is provided, read it and verify it equals `field_name`.
    2) Read `cell` (value cell — may be a range or comma-separated) and validate
       it against `value_type` + `allow_empty`.
    """
    import uuid
    from app.services.validation_service import _validate_field
    from app.services import _load_workbook, read_cells_from_workbook
    from app.models.schemas import FieldModel

    try:
        temp_path = None
        file_path = None

        if file and _is_excel_filename(file.filename or ""):
            ext = _excel_ext(file.filename)
            temp_path = UPLOADS_DIR / f"_check_{uuid.uuid4().hex}{ext}"
            with open(temp_path, "wb") as f_out:
                content = await file.read()
                f_out.write(content)
            file_path = str(temp_path)
        elif stored_test_file and Path(stored_test_file).exists():
            file_path = stored_test_file
        else:
            return JSONResponse({"ok": False, "error": "Select or enter a valid .xlsx/.xlsm test file path"})

        is_raw = raw in ("true", "on", "1")
        sheet_s = sheet.strip()

        # Open workbooks once per request. The label always uses calculated
        # (data_only) values; the value cell may need raw formula text when
        # raw_cell_value is True — reuse the calc workbook for both otherwise.
        wb_calc = _load_workbook(file_path, data_only=True)
        wb_raw = _load_workbook(file_path, data_only=False) if is_raw else None
        try:
            # --- Label check (Field Name vs Field Name Cell) ---------------------
            label_check = None
            fnc = field_name_cell.strip()
            fn = field_name.strip()
            if fnc:
                label_res = read_cells_from_workbook(wb_calc, sheet_s, fnc)
                if label_res["error"]:
                    label_check = {
                        "cell": fnc,
                        "value": None,
                        "expected": fn,
                        "ok": False,
                        "error": label_res["error"],
                    }
                else:
                    actual = label_res["value"]
                    actual_s = "" if actual is None else str(actual).strip()
                    # Empty label in file is always valid.
                    # Invalid only when actual_s is non-empty AND doesn't match the template's Field Name.
                    if not actual_s:
                        matches = True
                        err = None
                    elif not fn:
                        matches = False
                        err = "Field Name is empty in template — cannot compare."
                    else:
                        matches = (actual_s == fn)
                        err = None if matches else f"Label at {fnc} is '{actual_s}', expected '{fn}'."
                    label_check = {
                        "cell": fnc,
                        "value": actual_s if actual_s else "(empty)",
                        "expected": fn,
                        "ok": matches,
                        "error": err,
                    }

            # --- Value cell read + type validation -------------------------------
            wb_for_value = wb_raw if is_raw else wb_calc
            value_res = read_cells_from_workbook(
                wb_for_value, sheet_s, cell.strip(), value_type=value_type.strip()
            )
        finally:
            try:
                wb_calc.close()
            except Exception:
                pass
            if wb_raw is not None:
                try:
                    wb_raw.close()
                except Exception:
                    pass

        if temp_path:
            try:
                temp_path.unlink()
            except Exception:
                pass

        if value_res["error"]:
            return JSONResponse({
                "ok": False,
                "error": str(value_res["error"]),
                "label_check": label_check,
            })

        val = value_res["value"]
        vals = value_res.get("values") or []
        display = str(val) if val is not None else "(empty)"

        field = FieldModel(
            field_code="_check",
            field_name=fn or "_check",
            sheet=sheet_s,
            cell=cell.strip(),
            value_type=value_type.strip(),
            allow_empty=allow_empty in ("true", "on", "1"),
        )
        if len(vals) > 1:
            validation_error = None
            for v in vals:
                e = _validate_field(field, v)
                if e:
                    validation_error = e
                    break
        else:
            validation_error = _validate_field(field, val)

        return JSONResponse({
            "ok": True,
            "value": display,
            "validation_error": validation_error,
            "label_check": label_check,
        })
    except Exception as exc:
        logger.error(f"Check cell failed: {exc}")
        return JSONResponse({"ok": False, "error": str(exc)})


# ─── Stage 2 Export & Feedback ────────────────────────────────────────────────

EXPORT_DIR = Path("exports")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/{code}/{version}/export")
async def export_stage2(code: str, version: str):
    """Export a template as Stage 2 mapping JSON (download)."""
    from fastapi.responses import FileResponse

    tmpl = get_template(code, version)
    if not tmpl:
        return _redirect("/templates", f"Template {code}_{version} not found", "error")

    filename = f"{code}_{version}_stage2.json"
    export_path = EXPORT_DIR / filename
    export_to_file(tmpl, str(export_path))

    return FileResponse(
        path=str(export_path),
        filename=filename,
        media_type="application/json",
    )


@router.post("/{code}/{version}/export-to-processor")
async def export_to_processor(request: Request, code: str, version: str):
    """Export mapping directly to the ed_py_ai processor mappings folder."""
    tmpl = get_template(code, version)
    if not tmpl:
        return JSONResponse({"ok": False, "error": f"Template {code}_{version} not found"})

    data = await request.json()
    target_folder = data.get("target_folder", "")

    if not target_folder:
        # Default: try to find ed_py_ai relative to this project
        for candidate in [
            Path(__file__).resolve().parent.parent.parent.parent / "ed_py_ai" / "excel_processor" / "mappings",
            Path.home() / "Documents" / "dev" / "ai" / "ed_py_ai" / "excel_processor" / "mappings",
        ]:
            if candidate.parent.exists():
                target_folder = str(candidate)
                break

    if not target_folder:
        return JSONResponse({"ok": False, "error": "Could not determine target folder. Provide target_folder."})

    filename = f"{code}_{version}.json"
    export_path = Path(target_folder) / filename
    export_to_file(tmpl, str(export_path))

    return JSONResponse({"ok": True, "path": str(export_path)})


@router.post("/{code}/{version}/import-feedback")
async def import_feedback(request: Request, code: str, version: str):
    """Import Stage 2 feedback report to update field AI prompts and search areas.

    Expects JSON: { "field_code": { "valid": false, "reason": "...", "suggestion": "..." }, ... }
    """
    tmpl = get_template(code, version)
    if not tmpl:
        return JSONResponse({"ok": False, "error": f"Template {code}_{version} not found"})

    feedback = await request.json()
    updated_count = 0

    for field in tmpl.fields:
        fb = feedback.get(field.field_code)
        if not fb or fb.get("valid", True):
            continue

        # Append feedback to description for user review
        reason = fb.get("reason", "")
        suggestion = fb.get("suggestion", "")
        feedback_note = f" [Stage 2 feedback: {reason}"
        if suggestion:
            feedback_note += f" Suggestion: {suggestion}"
        feedback_note += "]"

        if feedback_note not in field.description:
            field.description += feedback_note
            updated_count += 1

    if updated_count > 0:
        save_template(tmpl)
        logger.info(f"Imported feedback for {code}_{version}: {updated_count} fields updated")

    return JSONResponse({"ok": True, "updated": updated_count})
