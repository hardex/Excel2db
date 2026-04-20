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
    fields: List[FieldModel] = []
