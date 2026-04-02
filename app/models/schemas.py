from pydantic import BaseModel
from typing import List, Optional


class FieldModel(BaseModel):
    field_code: str
    field_name: str
    sheet: str
    cell: str
    value_type: str  # "string", "number", "date"
    allow_empty: bool = False
    active: bool = True
    description: str = ""


class TemplateModel(BaseModel):
    template_code: str
    template_version: str
    description: str = ""
    is_default: bool = False
    fields: List[FieldModel] = []
