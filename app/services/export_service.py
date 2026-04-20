"""Export Excel2db templates to Stage 2 mapping format for ed_py_ai processor."""

import json
from pathlib import Path

from app.models.schemas import TemplateModel
from app.services.logging_service import get_logger

logger = get_logger()


def template_to_stage2(template: TemplateModel) -> dict:
    """Convert an Excel2db TemplateModel to Stage 2 MappingTemplate format.

    Stage 2 format uses nested objects (search_area, data_structure) instead of
    flat fields, matching shared.models.MappingTemplate.
    """
    fields = []
    for f in template.fields:
        search_area = {
            "sheet": f.sheet,
            "cell": f.cell,
            "cell_range": None,
            "anchor_text": None,
            "row_offset": 0,
            "col_offset": 0,
        }

        data_structure = {
            "field_name": f.field_name,
            "field_type": f.value_type,
            "hadoop_column": f.field_code,
            "allow_empty": f.allow_empty,
            "validation_regex": None,
        }

        fields.append({
            "field_code": f.field_code,
            "field_name": f.field_name,
            "ai_prompt": f.ai_prompt,
            "search_area": search_area,
            "data_structure": data_structure,
            "active": f.active,
            "raw_cell_value": f.raw_cell_value,
            "description": f.description,
        })

    return {
        "template_code": template.template_code,
        "template_version": template.template_version,
        "description": template.description,
        "fields": fields,
    }


def export_to_file(template: TemplateModel, output_path: str) -> str:
    """Export a template to Stage 2 JSON file.

    Returns the path to the created file.
    """
    data = template_to_stage2(template)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    logger.info(f"Exported Stage 2 mapping: {path}")
    return str(path)
