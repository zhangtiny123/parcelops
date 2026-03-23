from __future__ import annotations

from csv import DictReader, Sniffer, excel
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile


PREVIEW_ROW_LIMIT = 10
XLSX_MAIN_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
XLSX_REL_NS = {
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "sheet": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


@dataclass(frozen=True)
class FilePreview:
    columns: list[str]
    rows: list[dict[str, str]]


def load_file_preview(
    file_path: Path, file_type: str, row_limit: int = PREVIEW_ROW_LIMIT
) -> FilePreview:
    if file_type == "csv":
        return _load_csv_preview(file_path, row_limit)
    if file_type == "xlsx":
        return _load_xlsx_preview(file_path, row_limit)
    raise ValueError(f"Unsupported preview file type: {file_type}")


def _load_csv_preview(file_path: Path, row_limit: int) -> FilePreview:
    raw_text = file_path.read_text(encoding="utf-8-sig")
    sample = raw_text[:4096]
    try:
        dialect = Sniffer().sniff(sample)
    except Exception:
        dialect = excel

    reader = DictReader(StringIO(raw_text), dialect=dialect)
    columns = list(reader.fieldnames or [])
    rows: list[dict[str, str]] = []
    for row in reader:
        rows.append({column: _stringify_cell(row.get(column)) for column in columns})
        if len(rows) >= row_limit:
            break

    return FilePreview(columns=columns, rows=rows)


def _load_xlsx_preview(file_path: Path, row_limit: int) -> FilePreview:
    with ZipFile(file_path) as workbook:
        shared_strings = _read_shared_strings(workbook)
        sheet_path = _resolve_first_sheet_path(workbook)
        rows = _read_sheet_rows(workbook, sheet_path, shared_strings)

    if not rows:
        return FilePreview(columns=[], rows=[])

    header_row = rows[0]
    max_header_index = max(header_row.keys()) if header_row else -1
    columns = [
        _stringify_cell(header_row.get(index)) for index in range(max_header_index + 1)
    ]

    preview_rows: list[dict[str, str]] = []
    for row in rows[1 : row_limit + 1]:
        preview_rows.append(
            {
                columns[index]: _stringify_cell(row.get(index))
                for index in range(len(columns))
                if columns[index]
            }
        )

    return FilePreview(
        columns=[column for column in columns if column], rows=preview_rows
    )


def _read_shared_strings(workbook: ZipFile) -> list[str]:
    shared_strings_path = "xl/sharedStrings.xml"
    if shared_strings_path not in workbook.namelist():
        return []

    root = ET.fromstring(workbook.read(shared_strings_path))
    strings: list[str] = []
    for item in root.findall("main:si", XLSX_MAIN_NS):
        strings.append(
            "".join(node.text or "" for node in item.findall(".//main:t", XLSX_MAIN_NS))
        )
    return strings


def _resolve_first_sheet_path(workbook: ZipFile) -> str:
    workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
    sheet = workbook_root.find("main:sheets/main:sheet", XLSX_MAIN_NS)
    if sheet is None:
        raise ValueError("Workbook does not contain any sheets.")

    relationship_id = sheet.attrib.get(
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    )
    if relationship_id is None:
        raise ValueError("Workbook sheet is missing a relationship id.")

    rels_root = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    for relationship in rels_root.findall("rel:Relationship", XLSX_REL_NS):
        if relationship.attrib.get("Id") == relationship_id:
            target = relationship.attrib["Target"]
            normalized_target = target.lstrip("/")
            if normalized_target.startswith("xl/"):
                return normalized_target
            return f"xl/{normalized_target}"

    raise ValueError("Workbook sheet relationship could not be resolved.")


def _read_sheet_rows(
    workbook: ZipFile,
    sheet_path: str,
    shared_strings: list[str],
) -> list[dict[int, str]]:
    root = ET.fromstring(workbook.read(sheet_path))
    rows: list[dict[int, str]] = []
    for row in root.findall(".//main:sheetData/main:row", XLSX_MAIN_NS):
        row_values: dict[int, str] = {}
        for cell in row.findall("main:c", XLSX_MAIN_NS):
            column_index = _column_index_from_cell_reference(cell.attrib.get("r", ""))
            row_values[column_index] = _read_cell_value(cell, shared_strings)
        if row_values:
            rows.append(row_values)

    return rows


def _read_cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(
            node.text or "" for node in cell.findall(".//main:t", XLSX_MAIN_NS)
        )

    value = cell.findtext("main:v", default="", namespaces=XLSX_MAIN_NS)
    if value == "":
        return ""
    if cell_type == "s":
        index = int(value)
        return shared_strings[index] if index < len(shared_strings) else ""
    if cell_type == "b":
        return "true" if value == "1" else "false"
    return value


def _column_index_from_cell_reference(reference: str) -> int:
    column_letters = "".join(
        character for character in reference if character.isalpha()
    )
    if not column_letters:
        return 0

    index = 0
    for letter in column_letters:
        index = (index * 26) + (ord(letter.upper()) - 64)
    return index - 1


def _stringify_cell(value: object) -> str:
    if value is None:
        return ""
    return str(value)
