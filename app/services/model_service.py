import json
import re
from pathlib import Path
from typing import Optional

from app.models.schemas import ModelDefinition, TemplateModel

MODELS_DIR = Path("mappings/models")
MODELS_DIR.mkdir(parents=True, exist_ok=True)

_INVALID_NAME_RE = re.compile(r"[\\/\x00\r\n]")


def _model_filename(model_code: str) -> Path:
    if _INVALID_NAME_RE.search(model_code):
        raise ValueError(f"Invalid model_code: {model_code!r}")
    return MODELS_DIR / f"{model_code}.json"


def load_model(model_code: str) -> Optional[ModelDefinition]:
    path = _model_filename(model_code)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return ModelDefinition(**data)


def save_model(model: ModelDefinition) -> None:
    path = _model_filename(model.model_code)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(model.model_dump(), f, indent=2)


def list_models() -> list[ModelDefinition]:
    out: list[ModelDefinition] = []
    for path in sorted(MODELS_DIR.glob("*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                out.append(ModelDefinition(**json.load(f)))
        except Exception:
            pass
    return out


def ensure_model_has_fields(model_code: str, new_field_codes: list[str]) -> ModelDefinition:
    """Append any field_codes not already present; preserve existing order.

    Creates the model file on first call. Duplicates within `new_field_codes`
    are de-duplicated while preserving first-seen order.
    """
    model = load_model(model_code) or ModelDefinition(model_code=model_code, field_codes=[])
    existing = set(model.field_codes)
    for fc in new_field_codes:
        if fc and fc not in existing:
            model.field_codes.append(fc)
            existing.add(fc)
    save_model(model)
    return model


def get_model_fields_for_template(template: TemplateModel) -> list[str]:
    """Return canonical ordered field_codes for this template's model.

    If the model file doesn't exist yet (e.g. legacy template that was never
    re-saved), seed it from the template's own fields so output generation
    still has a stable order.
    """
    model = load_model(template.template_code)
    if model is None:
        model = ensure_model_has_fields(
            template.template_code,
            [f.field_code for f in template.fields],
        )
    return list(model.field_codes)
