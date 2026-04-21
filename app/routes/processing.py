import json
import urllib.parse
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
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
    return templates_engine.TemplateResponse(
        request,
        "process.html",
        {
            "all_templates": all_templates,
            "default_template": default_tmpl,
            "msg": msg,
            "msg_type": msg_type,
        },
    )


@router.post("/list-files")
async def list_folder_files(request: Request):
    """AJAX endpoint: list .xlsx files in a given folder."""
    data = await request.json()
    folder = data.get("path", "").strip()
    if not folder:
        return JSONResponse({"ok": False, "error": "Folder path is required"})
    p = Path(folder)
    if not p.exists():
        return JSONResponse({"ok": False, "error": "Folder not found"})
    if not p.is_dir():
        return JSONResponse({"ok": False, "error": "Path is not a folder"})
    files = sorted(
        [f.name for f in p.iterdir() if f.is_file() and f.suffix.lower() == ".xlsx"],
        key=str.lower,
    )
    return JSONResponse({"ok": True, "files": files, "folder": str(p.resolve())})


@router.post("/start")
async def start_processing(
    request: Request,
    file: UploadFile = File(None),
    template_code: str = Form(...),
    template_version: str = Form(...),
    selected_file_path: str = Form(""),
    output_format: str = Form("json"),
):
    dest = None
    file_path = None
    source_filename = None

    # Option 1: file selected from folder listing
    if selected_file_path.strip():
        p = Path(selected_file_path.strip())
        if not p.exists() or not p.suffix.lower() == ".xlsx":
            return _redirect("/process", "Selected file not found or not .xlsx", "error")
        file_path = str(p)
        source_filename = p.name
        logger.info(f"File from folder: source={source_filename}")
    # Option 2: uploaded file
    elif file and file.filename and file.filename.endswith(".xlsx"):
        source_filename = file.filename
        logger.info(f"Upload started: source={source_filename}")
        dest = UPLOADS_DIR / source_filename
        content = await file.read()
        with open(dest, "wb") as f_out:
            f_out.write(content)
        logger.info(f"Upload completed: source={source_filename}")
        file_path = str(dest)
    else:
        return _redirect("/process", "Please select an Excel file (.xlsx)", "error")

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
    finally:
        try:
            if dest:
                dest.unlink()
        except Exception:
            pass

    # Validate
    errors = validate_fields(active_fields, extracted)

    fmt = output_format.strip().lower()
    if fmt not in ("json", "csv"):
        fmt = "json"

    session = {"source_filename": source_filename}
    session["template_code"] = template_code
    session["template_version"] = template_version
    session["output_format"] = fmt
    session["extracted"] = extracted
    session["validation_errors"] = errors
    session["corrections"] = {}

    if errors:
        resp = RedirectResponse(url="/process/correct", status_code=303)
        _set_session(resp, session)
        return resp

    # All valid — generate output
    final_values = _build_final_values(session)
    output_path = generate_output(source_filename, final_values, fmt)
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
            "source_filename": session.get("source_filename", ""),
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
            label_value = raw.get("label_value")
            values_list = raw.get("values")
        else:
            val = raw
            err = None
            label_value = None
            values_list = None

        if fc in corrections:
            # User edited a single scalar — drop the per-cell list so revalidation
            # uses the corrected value.
            merged[fc] = {"value": corrections[fc], "error": None, "label_value": label_value, "values": None}
        else:
            merged[fc] = {"value": val, "error": err, "label_value": label_value, "values": values_list}

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
    fmt = session.get("output_format", "json")
    output_path = generate_output(source_filename, final_values, fmt)
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
    fmt = session.get("output_format", "json")
    preview = None
    try:
        with open(output_path, encoding="utf-8") as f:
            if fmt == "csv":
                preview = f.read()
            else:
                preview = json.dumps(json.load(f), indent=2)
    except Exception:
        pass

    msg = request.query_params.get("msg", "")
    msg_type = request.query_params.get("msg_type", "success")

    return templates_engine.TemplateResponse(
        request,
        "result.html",
        {
            "output_path": output_path,
            "source_filename": session.get("source_filename"),
            "output_format": fmt,
            "preview": preview,
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

    fmt = session.get("output_format", "json")
    media = "text/csv" if fmt == "csv" else "application/json"
    return FileResponse(
        path=output_path,
        filename=Path(output_path).name,
        media_type=media,
    )
