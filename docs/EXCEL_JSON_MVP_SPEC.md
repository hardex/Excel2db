
# Excel Template Mapping and JSON Extraction Tool
## Technical Specification (MVP v1)

## 1. Project Overview

Build a **local web application** for processing structured `.xlsx` Excel files using configurable template mappings.

The application must allow a user to:

- upload an `.xlsx` file;
- select a template manually;
- manage template mappings in a web UI;
- store mappings as editable JSON files;
- support multiple template versions;
- extract values from mapped cells across one or more sheets;
- validate extracted values;
- allow manual correction of invalid fields only;
- log processing actions and manual corrections;
- generate a final business JSON file only after all validation errors are resolved.

This MVP is designed for:

- **local use on one computer**;
- **no authentication**;
- **no database**;
- **file-based storage only**.

---

## 2. Scope

### Included in MVP

- local web UI;
- `.xlsx` upload;
- manual template selection;
- default template preselection;
- template editor;
- mapping storage in JSON files;
- support for multiple sheets;
- support for multiple template versions;
- coordinate-based extraction (`sheet + cell`);
- reading **raw Excel values**;
- reading **formulas as formulas**, not calculated results;
- validation:
  - required / optional;
  - number;
  - date;
- manual correction of invalid fields only;
- log file generation;
- JSON output generation;
- "Test Cell" feature in template editor.

### Excluded from MVP

- `.xls` support;
- OCR;
- automatic template detection;
- database integration;
- batch processing;
- user accounts;
- multi-user access;
- autosave of unfinished sessions;
- automatic normalization / cleanup / transformation of values.

---

## 3. Core Business Rules

1. Only `.xlsx` files are supported.
2. Files may contain multiple sheets.
3. Templates are assumed to be stable by cell coordinates.
4. Merged cells may exist.
5. If a mapped cell contains a formula, the system must read and store the **formula text itself**.
6. Dropdown fields, if present, are treated as regular values; only the stored cell value is read.
7. Protected sheets are out of scope.
8. No automatic normalization is allowed.
9. The system must **not** automatically:
   - trim spaces;
   - remove extra spaces;
   - reformat dates;
   - reformat numbers;
   - change case;
   - silently correct values.
10. A string containing only spaces, e.g. `"   "`, must be treated as a **value**, not as empty.
11. Final JSON must not be created until all validation issues are resolved.
12. If the user leaves the processing page, the current temporary state is discarded.

---

## 4. User and Environment

### User
Single local operator.

### Runtime
- local machine only;
- accessed through browser.

### Authentication
Not required in MVP.

---

## 5. Main Modules

The application must include:

1. Template Management
2. Template Mapping Editor
3. Excel Processing
4. Validation
5. Manual Correction
6. Logging
7. JSON Export

---

## 6. Template Management

### Template Definition

Each template must include:

- `template_code`
- `template_version`
- `description`
- `is_default`
- `fields`

### Versioning

Multiple versions of the same template must be supported.

Example:

- `customer_form` / `v1`
- `customer_form` / `v2`

### Default Template

One template may be marked as default.

Behavior:

- default template is preselected on processing page;
- user may still choose another template manually.

### Supported Template Operations

The UI must allow:

- create template;
- edit template;
- create new version;
- delete template;
- add field;
- edit field;
- delete field;
- enable / disable field;
- mark as default;
- test-read a cell from an uploaded `.xlsx` file.

---

## 7. Mapping File Format

### Storage

Mappings must be stored as JSON files in:

```text
/mappings
```

### File Naming

Suggested format:

```text
{template_code}_{template_version}.json
```

Example:

```text
customer_form_v1.json
customer_form_v2.json
```

### Required Template Fields

- `template_code`
- `template_version`
- `description`
- `is_default`
- `fields`

### Required Field Properties

Each field must contain:

- `field_code`
- `field_name`
- `sheet`
- `cell`
- `value_type`
- `allow_empty`

Optional:

- `active`
- `description`

### Example Mapping

```json
{
  "template_code": "customer_form",
  "template_version": "v1",
  "description": "Customer form version 1",
  "is_default": true,
  "fields": [
    {
      "field_code": "customer_name",
      "field_name": "Customer Name",
      "sheet": "Sheet1",
      "cell": "C7",
      "value_type": "string",
      "allow_empty": false,
      "active": true,
      "description": "Primary customer full name"
    },
    {
      "field_code": "birth_date",
      "field_name": "Birth Date",
      "sheet": "Sheet1",
      "cell": "C8",
      "value_type": "date",
      "allow_empty": true,
      "active": true,
      "description": "Customer birth date"
    },
    {
      "field_code": "amount",
      "field_name": "Amount",
      "sheet": "Sheet2",
      "cell": "F10",
      "value_type": "number",
      "allow_empty": false,
      "active": true,
      "description": "Declared amount"
    }
  ]
}
```

---

## 8. Mapping Rules

### Coordinate-Based Extraction

Each mapped field is defined strictly by:

- sheet name;
- cell address.

Example:

```text
Sheet1 + C7
```

The system must not infer field locations dynamically.

### Merged Cells

If a mapped cell is inside a merged range, behavior should follow the Excel library’s raw read behavior.

If needed, implementation may resolve merged cells to the top-left cell of the merged range.

This must be handled consistently.

---

## 9. Excel Reading Rules

### Supported Format

- `.xlsx` only

### Reading Mode

The system must read **raw values**.

Important:

- formulas must be read as formulas, e.g. `=SUM(A1:A3)`;
- formulas must **not** be read as calculated results.

### Multiple Sheets

Mappings may reference cells across multiple sheets.

### Missing Sheet or Cell

If a mapped sheet does not exist:

- mark the field invalid;
- log the error.

If a mapped cell is invalid or unreadable:

- mark the field invalid;
- log the error.

---

## 10. Validation Rules

Validation is performed **after extraction**, on the exact extracted value, with no auto-transformation.

### Supported Validation Types

- required / optional
- number
- date
- string

### Empty Value Rule

Property:

```json
"allow_empty": true | false
```

Behavior:

- if `allow_empty = false`, the field is invalid only when the value is truly empty:
  - `None`
  - `""`
- `"   "` is **not empty**

### Number Validation

Property:

```json
"value_type": "number"
```

Accepted:

- integer;
- decimal;
- negative values;
- comma as thousands separator;
- dot as decimal separator.

Examples of valid values:

- `123`
- `-123`
- `1234.56`
- `1,234.56`
- `-1,234.56`

Examples of invalid values:

- `1.234,56`
- `12 345`
- `abc`

No cleanup or conversion before validation.

### Date Validation

Property:

```json
"value_type": "date"
```

Accepted:

- native Excel date cell;
- text in formats:
  - `YYYY-MM-DD`
  - `DD.MM.YYYY`
  - `DD/MM/YYYY`
  - `MM/DD/YYYY`

Ambiguous slash dates must default to **US interpretation**:

- baseline = `MM/DD/YYYY`

No auto-reformatting before validation.

### String Validation

Property:

```json
"value_type": "string"
```

Behavior:

- accepted as-is;
- only `allow_empty` applies.

---

## 11. Manual Correction

### Correction Eligibility

Only fields that fail validation may be manually corrected.

Valid fields must not be editable.

### Correction Screen Must Show

For each invalid field:

- `field_code`
- `field_name`
- `sheet`
- `cell`
- original extracted value
- validation error
- editable corrected value input

### Revalidation

After correction submission:

- corrected values must be validated again;
- if any corrected value is still invalid, JSON generation remains blocked;
- only after all fields are valid may JSON be generated.

### Logging Corrections

Each correction must be logged with:

- `field_code`
- `original_value`
- `corrected_value`
- `corrected_at`

No user identity is required in MVP.

### Final Output Rule

The final JSON must contain the **corrected value**.

Original values must appear only in logs.

---

## 12. Processing Flow

### Mode

MVP supports **one file at a time**.

### Flow

1. User uploads `.xlsx` file.
2. User selects template.
3. System loads template mapping.
4. System reads mapped values from workbook.
5. System validates extracted values.
6. If validation fails:
   - JSON generation is blocked;
   - user is redirected to correction page.
7. User corrects invalid fields.
8. System revalidates corrected values.
9. If all fields are valid:
   - final JSON file is generated;
   - process is completed successfully.

### Exit Behavior

If the user leaves the processing page:

- temporary processing state is discarded;
- current unfinished process is not preserved;
- open resources must be closed.

---

## 13. Logging

### Storage

Log files must be stored in:

```text
/logs
```

### Minimum Logged Events

- upload started;
- upload completed;
- template selected;
- template version used;
- processing started;
- workbook opened;
- field read attempt;
- validation failures;
- manual corrections;
- JSON output created;
- processing completed;
- processing failed.

### Manual Correction Log Entry Must Include

- timestamp;
- source file name;
- template code;
- template version;
- field code;
- original value;
- corrected value.

### Example Log Entries

```text
2026-03-25 10:15:10 INFO Upload started: source=file1.xlsx
2026-03-25 10:15:12 INFO Upload completed: source=file1.xlsx
2026-03-25 10:15:13 INFO Template selected: template_code=customer_form, template_version=v1
2026-03-25 10:15:14 INFO Processing started: source=file1.xlsx
2026-03-25 10:15:14 INFO Workbook opened successfully
2026-03-25 10:15:14 INFO Read field: field_code=customer_name, sheet=Sheet1, cell=C7
2026-03-25 10:15:15 WARNING Validation failed: field_code=amount, rule=number, value=12 345
2026-03-25 10:15:40 INFO Manual correction: field_code=amount, original_value=12 345, corrected_value=12345, corrected_at=2026-03-25T10:15:40
2026-03-25 10:15:42 INFO Output created: outputs/file1.json
2026-03-25 10:15:42 INFO Processing completed: status=success
```

---

## 14. Output JSON

### Output Type

The final output must be a **simple business JSON**.

### Creation Rule

JSON must be created **only after all values pass validation**.

### Storage

Output files must be stored in:

```text
/outputs
```

### Naming

Suggested:

```text
{source_filename_without_extension}.json
```

Example:

```text
form_001.json
```

### Example Output

```json
{
  "customer_name": "John Smith",
  "birth_date": "03/25/2026",
  "amount": "1,234.56"
}
```

Rules:

- final JSON contains extracted or corrected values only;
- no validation metadata;
- no original-value history;
- no technical audit details.

---

## 15. UI Requirements

### Language

The full UI must be in **English**.

### Required Pages

#### 1. Template List Page

Functions:

- list templates;
- show code, version, description, default flag;
- create template;
- edit template;
- delete template.

#### 2. Template Editor Page

Functions:

- edit template metadata;
- add/edit/delete fields;
- set default template;
- configure:
  - field code
  - field name
  - sheet
  - cell
  - value type
  - allow empty
  - active
  - description
- test-read a cell value from uploaded Excel file.

#### 3. Processing Page

Functions:

- upload `.xlsx`;
- select template;
- preselect default template;
- start processing;
- show log summary.

#### 4. Validation / Correction Page

Functions:

- show invalid fields only;
- display original values and validation errors;
- allow corrected input;
- resubmit validation.

#### 5. Result Page

Functions:

- show success result;
- allow JSON download;
- optionally show JSON preview.

#### 6. Log View Page

Functions:

- show log file content or recent entries.

---

## 16. "Test Cell" Feature

### Purpose

Allow the user to verify that a mapping points to the expected Excel cell.

### Workflow

User must be able to:

1. choose a test `.xlsx` file;
2. enter or edit:
   - sheet;
   - cell;
   - type;
   - allow empty;
3. click **Test Cell**;
4. see the raw value read from the workbook.

### Result

The system must show:

- success / failure;
- raw extracted value;
- read error if sheet or cell is invalid.

This feature is required in MVP.

---

## 17. File Storage

### File-Based Storage Only

No database is required.

### Directories

Suggested structure:

```text
project/
├─ app/
├─ mappings/
├─ uploads/
├─ outputs/
└─ logs/
```

### Stored Artifacts

- template JSON files → `/mappings`
- uploaded Excel files → `/uploads`
- output JSON files → `/outputs`
- log files → `/logs`

### History

Separate history storage is not required.

Processing history and correction history must exist only in log files.

---

## 18. Non-Functional Requirements

### Usability

- simple local UI;
- clear validation messages;
- minimal steps for one-file processing.

### Reliability

- predictable extraction by coordinates;
- no hidden data changes.

### Maintainability

- mappings stored as JSON;
- clear project structure;
- version-separated templates.

### Performance

- acceptable for single-file local processing;
- no batch optimization required.

### Auditability

- all manual corrections must be traceable in logs.

---

## 19. Recommended Technical Stack

### Backend

- Python
- FastAPI

### Excel Processing

- openpyxl

### Frontend

- server-rendered HTML templates (e.g. Jinja2)
- simple CSS / JS

### Logging

- Python `logging`

### Validation

- app-level validation logic
- optional Pydantic models

---

## 20. Suggested Internal Models

### Template Model

```json
{
  "template_code": "string",
  "template_version": "string",
  "description": "string",
  "is_default": true,
  "fields": []
}
```

### Field Model

```json
{
  "field_code": "string",
  "field_name": "string",
  "sheet": "string",
  "cell": "string",
  "value_type": "string",
  "allow_empty": false,
  "active": true,
  "description": "string"
}
```

### Temporary Processing Model

Temporary state may include:

- source file name;
- selected template;
- extracted values;
- validation errors;
- corrected values before final JSON generation.

This temporary state does not need to persist after page exit.

---

## 21. Error Handling

The system must handle at minimum:

- uploaded file is not `.xlsx`;
- selected template file is missing or invalid;
- mapped sheet does not exist;
- mapped cell cannot be read;
- invalid number format;
- invalid date format;
- corrected value still invalid;
- output file cannot be written.

For each case:

- user sees readable UI message;
- technical details are written to logs.

---

## 22. Acceptance Criteria

### Template Management

- user can create, edit, delete templates;
- user can create multiple template versions;
- one template can be marked as default;
- templates are stored as JSON files.

### Mapping

- user can define fields by sheet + cell;
- user can define validation rules;
- user can test-read a cell from uploaded `.xlsx`.

### Processing

- user can upload one `.xlsx` file;
- user can select a template manually;
- default template is preselected;
- system extracts values across one or more sheets;
- formulas are read as formulas.

### Validation

- required validation works;
- number validation works for allowed formats;
- date validation works for allowed formats;
- `"   "` is not treated as empty;
- no auto-normalization occurs.

### Manual Correction

- only invalid fields are editable;
- corrected values are revalidated;
- corrections are logged with original and new values.

### Output

- final JSON is not created until all validation errors are resolved;
- final JSON contains corrected values where applicable;
- final JSON contains only business fields.

### Logging

- processing steps are logged;
- template version is logged;
- manual corrections are logged.

---

## 23. Suggested Project Structure

```text
project/
├─ app/
│  ├─ main.py
│  ├─ routes/
│  │  ├─ templates.py
│  │  ├─ processing.py
│  │  ├─ logs.py
│  │  └─ validation.py
│  ├─ services/
│  │  ├─ template_service.py
│  │  ├─ excel_service.py
│  │  ├─ validation_service.py
│  │  ├─ output_service.py
│  │  └─ logging_service.py
│  ├─ models/
│  │  └─ schemas.py
│  ├─ templates/
│  │  ├─ template_list.html
│  │  ├─ template_edit.html
│  │  ├─ process.html
│  │  ├─ correction.html
│  │  ├─ result.html
│  │  └─ logs.html
│  └─ static/
│     ├─ css/
│     └─ js/
├─ mappings/
├─ uploads/
├─ outputs/
├─ logs/
└─ requirements.txt
```

---

## 24. Future Enhancements

Out of scope for MVP, but possible later:

- automatic template detection;
- DB export;
- batch processing;
- authentication;
- run history UI;
- correction history UI;
- API integration;
- Docker packaging;
- role-based access;
- template diff / compare.

---

## 25. Summary

This MVP defines a local web application for processing stable `.xlsx` templates using configurable JSON mappings.

Core principles:

- strict coordinate-based extraction;
- no automatic data modification;
- validation before final output;
- manual correction only for invalid fields;
- logging of corrections and processing steps;
- simple business JSON result.
```
