import json
import urllib.parse
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.models.schemas import FieldModel
from app.services import (
    get_default_template,
    get_template,
    list_templates,
    read_workbook_fields,
    validate_fields,
    generate_output,
    get_output_path,
    get_logger,
)

router = APIRouter(prefix="/process", tags=["processing"])
templates_engine = Jinja2Templates(directory="app/templates")
logger = get_logger()

UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# In-memory session store
SESSIONS: dict[str, dict] = {}
SESSION_COOKIE = "excel2db_session"


# ─── Helpers ────────────────────────────────────────────────────────────────

def _get_session(request: Request) -> dict | None:
    sid = request.cookies.get(SESSION_COOKIE)
    return SESSIONS.get(sid) if sid else None


def _set_session(response, session_data: dict) -> str:
    sid = str(uuid.uuid4())
    SESSIONS[sid] = session_data
    response.set_cookie(SESSION_COOKIE, sid, httponly=True, samesite="lax")
    return sid


def _clear_session(request: Request, response) -> None:
    sid = request.cookies.get(SESSION_COOKIE)
    if sid and sid in SESSIONS:
        del SESSIONS[sid]
    response.delete_cookie(SESSION_COOKIE)


def _redirect(url: str, msg: str = "", msg_type: str = "success") -> RedirectResponse:
    sep = "&" if "?" in url else "?"
    if msg:
        encoded = urllib.parse.quote(msg)
        url = f"{url}{sep}msg={encoded}&msg_type={msg_type}"
    return RedirectResponse(url=url, status_code=303)


def _build_final_values(session: dict) -> dict[str, Any]:
    """Merge extracted values with corrections."""
    extracted = session.get("extracted", {})
    corrections = session.get("corrections", {})
    result: dict[str, Any] = {}
    for field_code, raw in extracted.items():
        if isinstance(raw, dict):
            value = raw.get("value")
        else:
            value = raw
        if field_code in corrections:
            value = corrections[field_code]
        result[field_code] = value
    return result


# ─── Routes ─────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def process_page(request: Request):
    all_templates = list_templates()
    default_tmpl = get_default_template()
    msg = request.query_params.get("msg", "")
    msg_type = request.query_params.get("msg_type", "success")
    session = _get_session(request)
    uploaded_file = session.get("source_filename") if session else None
    selected_code = session.get("template_code") if session else None
    selected_version = session.get("template_version") if session else None
    return templates_engine.TemplateResponse(
        request,
        "process.html",
        {
            "all_templates": all_templates,
            "default_template": default_tmpl,
            "msg": msg,
            "msg_type": msg_type,
            "uploaded_file": uploaded_file,
            "selected_code": selected_code,
            "selected_version": selected_version,
        },
    )


@router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
):
    if not file.filename or not file.filename.endswith(".xlsx"):
        return _redirect("/process", "Only .xlsx files are accepted", "error")

    filename = file.filename
    logger.info(f"Upload started: source={filename}")

    dest = UPLOADS_DIR / filename
    content = await file.read()
    with open(dest, "wb") as f_out:
        f_out.write(content)

    logger.info(f"Upload completed: source={filename}")

    # Create / update session with file info
    session = _get_session(request) or {}
    session["source_filename"] = filename
    # Clear any previous processing state when a new file is uploaded
    for key in ("extracted", "validation_errors", "corrections", "output_path"):
        session.pop(key, None)

    resp = _redirect("/process", f"File '{filename}' uploaded successfully")
    _set_session(resp, session)
    return resp


@router.post("/start")
async def start_processing(
    request: Request,
    template_code: str = Form(...),
    template_version: str = Form(...),
):
    session = _get_session(request)
    if not session or not session.get("source_filename"):
        return _redirect("/process", "Please upload a file first", "error")

    source_filename = session["source_filename"]
    file_path = str(UPLOADS_DIR / source_filename)

    tmpl = get_template(template_code, template_version)
    if not tmpl:
        return _redirect("/process", f"Template {template_code} {template_version} not found", "error")

    logger.info(f"Template selected: template_code={template_code}, template_version={template_version}")
    logger.info(f"Processing started: source={source_filename}")

    # Read fields
    active_fields = [f for f in tmpl.fields if f.active]
    try:
        extracted = read_workbook_fields(file_path, active_fields)
    except Exception as exc:
        logger.error(f"Processing failed: {exc}")
        return _redirect("/process", f"Failed to read workbook: {exc}", "error")

    # Validate
    errors = validate_fields(active_fields, extracted)

    session["template_code"] = template_code
    session["template_version"] = template_version
    session["extracted"] = extracted
    session["validation_errors"] = errors
    session["corrections"] = {}

    if errors:
        resp = RedirectResponse(url="/process/correct", status_code=303)
        _set_session(resp, session)
        return resp

    # All valid — generate output
    final_values = _build_final_values(session)
    output_path = generate_output(source_filename, final_values)
    session["output_path"] = output_path
    logger.info("Processing completed: status=success")

    resp = RedirectResponse(url="/process/result", status_code=303)
    _set_session(resp, session)
    return resp


@router.get("/correct", response_class=HTMLResponse)
async def correct_page(request: Request):
    session = _get_session(request)
    if not session:
        return _redirect("/process", "Session expired — please start again", "error")

    tmpl = get_template(session.get("template_code", ""), session.get("template_version", ""))
    if not tmpl:
        return _redirect("/process", "Template not found — please start again", "error")

    errors = session.get("validation_errors", {})
    extracted = session.get("extracted", {})
    corrections = session.get("corrections", {})

    # Build rows for invalid fields
    invalid_fields = []
    for field in tmpl.fields:
        if not field.active:
            continue
        if field.field_code not in errors:
            continue
        raw = extracted.get(field.field_code, {})
        if isinstance(raw, dict):
            original_value = raw.get("value")
        else:
            original_value = raw
        corrected = corrections.get(field.field_code, "")
        invalid_fields.append(
            {
                "field": field,
                "original_value": original_value,
                "error": errors[field.field_code],
                "corrected": corrected,
            }
        )

    msg = request.query_params.get("msg", "")
    msg_type = request.query_params.get("msg_type", "error")

    return templates_engine.TemplateResponse(
        request,
        "correction.html",
        {
            "invalid_fields": invalid_fields,
            "template": tmpl,
            "msg": msg,
            "msg_type": msg_type,
        },
    )


@router.post("/correct")
async def submit_corrections(request: Request):
    session = _get_session(request)
    if not session:
        return _redirect("/process", "Session expired — please start again", "error")

    tmpl = get_template(session.get("template_code", ""), session.get("template_version", ""))
    if not tmpl:
        return _redirect("/process", "Template not found", "error")

    form = await request.form()
    form_dict = dict(form)

    errors = session.get("validation_errors", {})
    corrections = session.get("corrections", {})
    extracted = session.get("extracted", {})
    now_ts = datetime.utcnow().isoformat()

    active_fields = [f for f in tmpl.fields if f.active]

    for field_code in list(errors.keys()):
        key = f"correction_{field_code}"
        if key in form_dict:
            new_val = form_dict[key]  # No trimming per spec
            raw = extracted.get(field_code, {})
            if isinstance(raw, dict):
                orig_val = raw.get("value")
            else:
                orig_val = raw
            corrections[field_code] = new_val
            logger.info(
                f"Manual correction: field_code={field_code}, "
                f"original_value={orig_val!r}, corrected_value={new_val!r}, "
                f"corrected_at={now_ts}"
            )

    # Build merged values for revalidation
    merged: dict[str, Any] = {}
    for field in active_fields:
        fc = field.field_code
        raw = extracted.get(fc, {})
        if isinstance(raw, dict):
            val = raw.get("value")
            err = raw.get("error")
        else:
            val = raw
            err = None

        if fc in corrections:
            merged[fc] = {"value": corrections[fc], "error": None}
        else:
            merged[fc] = {"value": val, "error": err}

    new_errors = validate_fields(active_fields, merged)

    session["corrections"] = corrections
    session["validation_errors"] = new_errors

    if new_errors:
        resp = RedirectResponse(
            url="/process/correct?msg=Some+fields+still+have+errors&msg_type=error",
            status_code=303,
        )
        _set_session(resp, session)
        return resp

    # All valid — generate output
    final_values = _build_final_values(session)
    source_filename = session["source_filename"]
    output_path = generate_output(source_filename, final_values)
    session["output_path"] = output_path
    logger.info("Processing completed: status=success")

    resp = RedirectResponse(url="/process/result", status_code=303)
    _set_session(resp, session)
    return resp


@router.get("/result", response_class=HTMLResponse)
async def result_page(request: Request):
    session = _get_session(request)
    if not session or not session.get("output_path"):
        return _redirect("/process", "No result available — please process a file first", "error")

    output_path = session["output_path"]
    try:
        with open(output_path, encoding="utf-8") as f:
            json_preview = json.dumps(json.load(f), indent=2)
    except Exception:
        json_preview = None

    msg = request.query_params.get("msg", "")
    msg_type = request.query_params.get("msg_type", "success")

    return templates_engine.TemplateResponse(
        request,
        "result.html",
        {
            "output_path": output_path,
            "source_filename": session.get("source_filename"),
            "json_preview": json_preview,
            "msg": msg,
            "msg_type": msg_type,
        },
    )


@router.get("/download")
async def download_output(request: Request):
    session = _get_session(request)
    if not session or not session.get("output_path"):
        return _redirect("/process", "No output file available", "error")

    output_path = session["output_path"]
    if not Path(output_path).exists():
        return _redirect("/process/result", "Output file not found on disk", "error")

    return FileResponse(
        path=output_path,
        filename=Path(output_path).name,
        media_type="application/json",
    )
