import json
import os
from pathlib import Path
from typing import Optional

from app.models.schemas import TemplateModel

MAPPINGS_DIR = Path("mappings")
MAPPINGS_DIR.mkdir(parents=True, exist_ok=True)


def _template_filename(code: str, version: str) -> Path:
    return MAPPINGS_DIR / f"{code}_{version}.json"


def list_templates() -> list[TemplateModel]:
    """Return all templates sorted by code then version."""
    templates = []
    for path in sorted(MAPPINGS_DIR.glob("*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            templates.append(TemplateModel(**data))
        except Exception:
            pass
    return templates


def get_template(code: str, version: str) -> Optional[TemplateModel]:
    path = _template_filename(code, version)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return TemplateModel(**data)


def get_default_template() -> Optional[TemplateModel]:
    templates = list_templates()
    for t in templates:
        if t.is_default:
            return t
    return templates[0] if templates else None


def save_template(template: TemplateModel) -> None:
    path = _template_filename(template.template_code, template.template_version)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(template.model_dump(), f, indent=2)


def delete_template(code: str, version: str) -> bool:
    path = _template_filename(code, version)
    if path.exists():
        path.unlink()
        return True
    return False


def set_default_template(code: str, version: str) -> None:
    """Mark one template as default, clearing all others."""
    templates = list_templates()
    for t in templates:
        was_default = t.is_default
        t.is_default = t.template_code == code and t.template_version == version
        if was_default != t.is_default:
            save_template(t)
        elif t.template_code == code and t.template_version == version:
            save_template(t)


def template_exists(code: str, version: str) -> bool:
    return _template_filename(code, version).exists()
