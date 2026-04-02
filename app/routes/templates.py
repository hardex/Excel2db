import urllib.parse
import json
import os
import shutil
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
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
)

router = APIRouter(prefix="/templates", tags=["templates"])
templates_engine = Jinja2Templates(directory="app/templates")
logger = get_logger()

UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


# ─── Helpers ────────────────────────────────────────────────────────────────

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
                sheet=str(form.get(f"sheet_{index}", "")).strip(),
                cell=str(form.get(f"cell_{index}", "")).strip(),
                value_type=str(form.get(f"value_type_{index}", "string")).strip(),
                allow_empty=form.get(f"allow_empty_{index}") in ("on", "true", "1", True),
                active=form.get(f"active_{index}") in ("on", "true", "1", True),
                description=str(form.get(f"description_{index}", "")).strip(),
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

    if template_exists(template_code, template_version):
        return _redirect(
            "/templates/new",
            f"Template {template_code}_{template_version} already exists",
            "error",
        )

    fields = _parse_fields_from_form(form_dict)

    # Determine if this should be default
    all_tmpl = list_templates()
    is_default = form_dict.get("is_default") in ("on", "true", "1") or len(all_tmpl) == 0

    tmpl = TemplateModel(
        template_code=template_code,
        template_version=template_version,
        description=str(form_dict.get("description", "")).strip(),
        is_default=is_default,
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
    return templates_engine.TemplateResponse(
        request,
        "template_edit.html",
        {
            "template": tmpl,
            "template_fields_json": [f.model_dump() for f in tmpl.fields],
            "is_new": False,
            "msg": msg,
            "msg_type": msg_type,
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

    fields = _parse_fields_from_form(form_dict)
    is_default = form_dict.get("is_default") in ("on", "true", "1")

    updated = TemplateModel(
        template_code=code,
        template_version=version,
        description=str(form_dict.get("description", "")).strip(),
        is_default=is_default,
        fields=fields,
    )

    if is_default:
        all_tmpl = list_templates()
        for t in all_tmpl:
            if t.is_default and not (t.template_code == code and t.template_version == version):
                t.is_default = False
                save_template(t)

    save_template(updated)
    logger.info(f"Template updated: {code}_{version}")
    return _redirect(
        f"/templates/{code}/{version}/edit",
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
    if not file.filename or not file.filename.endswith(".xlsx"):
        msg = "Only .xlsx files are accepted for cell testing"
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


@router.post("/check-cell")
async def check_cell(
    file: UploadFile = File(...),
    sheet: str = Form(...),
    cell: str = Form(...),
    value_type: str = Form("string"),
    allow_empty: str = Form("false"),
    raw: str = Form("true"),
):
    """AJAX endpoint: read a single cell, validate, and return JSON result."""
    import uuid
    from fastapi.responses import JSONResponse
    from app.services.validation_service import _validate_field
    from app.models.schemas import FieldModel

    try:
        if not file.filename or not file.filename.endswith(".xlsx"):
            return JSONResponse({"ok": False, "error": "Only .xlsx files are accepted"})

        # Use a safe temp filename to avoid issues with special characters
        temp_path = UPLOADS_DIR / f"_check_{uuid.uuid4().hex}.xlsx"
        with open(temp_path, "wb") as f_out:
            content = await file.read()
            f_out.write(content)

        is_raw = raw in ("true", "on", "1")
        result = read_single_cell(str(temp_path), sheet.strip(), cell.strip().upper(), raw=is_raw)

        try:
            temp_path.unlink()
        except Exception:
            pass

        if result["error"]:
            return JSONResponse({"ok": False, "error": str(result["error"])})

        val = result["value"]
        display = str(val) if val is not None else "(empty)"

        # Validate against field type rules
        field = FieldModel(
            field_code="_check",
            field_name="_check",
            sheet=sheet.strip(),
            cell=cell.strip().upper(),
            value_type=value_type.strip(),
            allow_empty=allow_empty in ("true", "on", "1"),
        )
        validation_error = _validate_field(field, val)

        return JSONResponse({
            "ok": True,
            "value": display,
            "validation_error": validation_error,
        })
    except Exception as exc:
        logger.error(f"Check cell failed: {exc}")
        return JSONResponse({"ok": False, "error": str(exc)})
