import urllib.parse
from collections import OrderedDict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.services import list_models, list_templates, load_model, save_model

router = APIRouter(prefix="/models", tags=["models"])
templates_engine = Jinja2Templates(directory="app/templates")


def _resolve_field_usage(model_code: str):
    """For a given model_code, return:
      - field_names: {field_code: first-found field_name from current templates}
      - field_versions: {field_code: [template_version, ...] that still define it}
    Only templates with matching template_code contribute."""
    field_names: dict[str, str] = {}
    field_versions: OrderedDict[str, list[str]] = OrderedDict()
    for tmpl in list_templates():
        if tmpl.template_code != model_code:
            continue
        for f in tmpl.fields:
            if f.field_code not in field_names:
                field_names[f.field_code] = f.field_name
            field_versions.setdefault(f.field_code, []).append(tmpl.template_version)
    return field_names, field_versions


@router.get("", response_class=HTMLResponse)
async def models_index(request: Request):
    models = list_models()
    msg = request.query_params.get("msg", "")
    msg_type = request.query_params.get("msg_type", "success")
    return templates_engine.TemplateResponse(
        request,
        "models_list.html",
        {"models": models, "msg": msg, "msg_type": msg_type},
    )


@router.get("/{model_code}", response_class=HTMLResponse)
async def model_detail(request: Request, model_code: str):
    model = load_model(model_code)
    msg = request.query_params.get("msg", "")
    msg_type = request.query_params.get("msg_type", "error" if not model else "success")
    if not model:
        return templates_engine.TemplateResponse(
            request,
            "model_view.html",
            {
                "model": None,
                "model_code": model_code,
                "rows": [],
                "msg": msg or f"Model '{model_code}' not found.",
                "msg_type": msg_type,
            },
        )

    field_names, field_versions = _resolve_field_usage(model_code)
    rows = []
    removed_count = 0
    for fc in model.field_codes:
        versions = field_versions.get(fc, [])
        if not versions:
            removed_count += 1
        rows.append(
            {
                "field_code": fc,
                "field_name": field_names.get(fc, ""),
                "versions": versions,
            }
        )

    return templates_engine.TemplateResponse(
        request,
        "model_view.html",
        {
            "model": model,
            "model_code": model_code,
            "rows": rows,
            "removed_count": removed_count,
            "msg": msg,
            "msg_type": msg_type,
        },
    )


@router.post("/{model_code}/prune-removed")
async def prune_removed_fields(model_code: str):
    """Drop field_codes that no current template of this model still defines.

    This is an intentional, user-initiated destructive action — it breaks the
    default keep-forever guarantee for the fields it removes. Downstream
    output files written after this no longer include those fields."""
    model = load_model(model_code)
    if not model:
        return _redirect(f"/models/{urllib.parse.quote(model_code)}",
                         f"Model '{model_code}' not found.", "error")

    _, field_versions = _resolve_field_usage(model_code)
    before = len(model.field_codes)
    model.field_codes = [fc for fc in model.field_codes if field_versions.get(fc)]
    removed = before - len(model.field_codes)
    save_model(model)

    return _redirect(
        f"/models/{urllib.parse.quote(model_code)}",
        f"Removed {removed} field(s) no longer defined by any template.",
        "success" if removed else "info",
    )


def _redirect(url: str, msg: str, msg_type: str) -> RedirectResponse:
    sep = "&" if "?" in url else "?"
    encoded = urllib.parse.quote(msg)
    return RedirectResponse(
        url=f"{url}{sep}msg={encoded}&msg_type={msg_type}",
        status_code=303,
    )
