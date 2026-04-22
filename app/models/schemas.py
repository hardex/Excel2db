from pydantic import BaseModel
from typing import List, Optional


class FieldModel(BaseModel):
    field_code: str
    field_name: str
    field_name_cell: str = ""              # cell that holds the field's label in Excel
    sheet: str
    cell: str                              # value cell(s): single cell, range, or comma-separated list
    value_type: str  # "string", "number", "date"
    allow_empty: bool = True
    active: bool = True
    raw_cell_value: bool = False
    description: str = ""
    ai_prompt: str = ""                    # what to find — prompt for OpenAI validation


class TemplateModel(BaseModel):
    template_code: str
    template_version: str
    description: str = ""
    is_default: bool = False
    test_file_path: str = ""
    # Auto-detect configuration: if version_cell is set, the processor can match
    # an uploaded file to this template by reading the cell and comparing its
    # value to model_version (or to template_version when model_version is blank).
    version_cell_sheet: str = ""
    version_cell: str = ""
    model_version: str = ""
    fields: List[FieldModel] = []


class ModelDefinition(BaseModel):
    """Canonical field list shared by every template with the same
    template_code. Grows via union whenever a template is saved; fields are
    never pruned so output schema stays stable across template versions."""
    model_code: str
    field_codes: List[str] = []
