from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.services import get_log_lines

router = APIRouter(prefix="/logs", tags=["logs"])
templates_engine = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def logs_page(request: Request):
    lines = get_log_lines(200)
    log_content = "".join(lines) if lines else "(No log entries yet)"
    return templates_engine.TemplateResponse(
        request,
        "logs.html",
        {
            "log_content": log_content,
        },
    )
