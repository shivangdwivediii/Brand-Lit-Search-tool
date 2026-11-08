"""Validated .xlsx input and cell-level source hyperlinks (no Excel formulas)."""

from io import BytesIO
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

import pandas as pd
from defusedxml.common import DefusedXmlException
from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.utils.exceptions import InvalidFileException

from .models import EXTRA_COLUMNS, FIELDS, UNVERIFIED, ResearchResult, safe_url

MAX_ROWS = 200
MAX_BYTES = 10 * 1024 * 1024
MAX_COLUMNS = 50
MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class InputError(ValueError):
    pass


def normalized(value: object) -> str:
    return " ".join(str(value).strip().casefold().replace("_", " ").split())


def validate_frame(frame: pd.DataFrame) -> tuple[str, list[str]]:
    if frame.empty:
        raise InputError("The worksheet has no data rows.")
    if len(frame) > MAX_ROWS or len(frame.columns) > MAX_COLUMNS:
        raise InputError(f"Use at most {MAX_ROWS} rows and {MAX_COLUMNS} columns per workbook.")
    headers = list(frame.columns)
    if any(not isinstance(h, str) or not h.strip() for h in headers):
        raise InputError("Every column must have a non-empty text header in the first row.")
    lookup = {normalized(h): h for h in headers}
    if len(lookup) != len(headers):
        raise InputError("Column headers must be unique (ignoring case and surrounding spaces).")
    if "brand" not in lookup or not ({"parent company", "category"} & lookup.keys()):
        raise InputError("Include Brand and either Parent Company or Category columns.")
    reserved = {normalized(h) for h in [*FIELDS.values(), *EXTRA_COLUMNS]}
    if reserved & lookup.keys():
        raise InputError(
            "Input contains research output headers. Upload the original input workbook."
        )
    brand = lookup["brand"]
    if not any(str(v).strip() for v in frame[brand].fillna("")):
        raise InputError("Enter at least one brand name.")
    for col in [brand, *[lookup[k] for k in ("parent company", "category") if k in lookup]]:
        if any(len(str(v)) > 300 for v in frame[col].fillna("")):
            raise InputError("Brand names and research context must be at most 300 characters.")
    return brand, [lookup[k] for k in ("parent company", "category") if k in lookup]


def read_input(data: bytes) -> pd.DataFrame:
    if len(data) > MAX_BYTES:
        raise InputError("Upload an .xlsx file no larger than 10 MB.")
    try:
        with ZipFile(BytesIO(data)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 50 * 1024 * 1024:
                raise InputError("The expanded workbook exceeds the 50 MB safety limit.")
        workbook = load_workbook(BytesIO(data), read_only=True, data_only=False, keep_links=False)
        try:
            sheet = workbook.worksheets[0]
            if sheet.max_column > MAX_COLUMNS or sheet.max_row > MAX_ROWS + 1:
                raise InputError(
                    f"Use at most {MAX_ROWS} rows and {MAX_COLUMNS} columns; remove unused formatted rows."
                )
            rows = []
            for row in sheet.iter_rows():
                if any(cell.data_type == "f" for cell in row):
                    raise InputError(
                        "Formula cells are not accepted. Paste their values into a new workbook."
                    )
                rows.append([cell.value for cell in row])
        finally:
            workbook.close()
    except (
        BadZipFile,
        InvalidFileException,
        KeyError,
        OSError,
        ValueError,
        IndexError,
        ParseError,
        DefusedXmlException,
    ) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError("Could not read this workbook. Use an unencrypted .xlsx file.") from None
    if not rows:
        raise InputError("The worksheet is empty.")
    frame = pd.DataFrame(
        [r for r in rows[1:] if any(v is not None for v in r)], columns=rows[0], dtype=object
    )
    validate_frame(frame)
    return frame


def write_literal(sheet, row: int, col: int, value: object):
    """Preserve text such as '=1+1' literally, without formula injection."""
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

    if value is None or (not isinstance(value, (str, list, dict)) and pd.isna(value)):
        value = None
    if isinstance(value, str):
        value = ILLEGAL_CHARACTERS_RE.sub("", value)[:32767]
    cell = sheet.cell(row, col, value)
    if isinstance(value, str):
        cell.data_type = "s"
    return cell


def polish(sheet):
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor="185A50")
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    sheet.row_dimensions[1].height = 32
    for column in sheet.columns:
        size = min(65, max(18, max(len(str(cell.value or "")) for cell in column) + 2))
        sheet.column_dimensions[get_column_letter(column[0].column)].width = size
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")


def results_frame(frame: pd.DataFrame, results: list[ResearchResult]) -> pd.DataFrame:
    if len(frame) != len(results):
        raise ValueError("One research result is required per input row.")
    output = frame.copy(deep=True).reset_index(drop=True)
    for key, label in FIELDS.items():
        output[label] = [
            r.facts[key].value
            if r.facts[key].evidence and r.facts[key].value is not None
            else UNVERIFIED
            for r in results
        ]
    output[EXTRA_COLUMNS[0]] = [r.status for r in results]
    output[EXTRA_COLUMNS[1]] = [("Demo / " if r.demo else "Live / ") + r.mode for r in results]
    output[EXTRA_COLUMNS[2]] = [r.researched_at for r in results]
    output[EXTRA_COLUMNS[3]] = [
        "; ".join(r.notes + (["Cached evidence reused"] if r.cache_hit else [])) for r in results
    ]
    return output


def export_workbook(
    frame: pd.DataFrame, results: list[ResearchResult], usage: dict | None = None
) -> bytes:
    output = results_frame(frame, results)
    book = Workbook()
    sheet = book.active
    sheet.title = "Brand Research"
    for col, label in enumerate(output.columns, 1):
        write_literal(sheet, 1, col, label)
    for row_no, row in enumerate(output.itertuples(index=False, name=None), 2):
        for col, value in enumerate(row, 1):
            write_literal(sheet, row_no, col, value)

    log = book.create_sheet("Research Log")
    headers = [
        "Input row",
        "Brand",
        "Context",
        "Timestamp (UTC)",
        "Mode",
        "Event",
        "Field",
        "Value",
        "Status",
        "Source URL",
        "Source title",
        "Source tier",
        "Evidence quote",
        "Query",
        "Message",
    ]
    log.append(headers)

    def append_log(result, row_no, **details):
        data = {
            "Input row": row_no,
            "Brand": result.brand,
            "Context": result.context,
            "Timestamp (UTC)": result.researched_at,
            "Mode": ("DEMO / " if result.demo else "Live / ") + result.mode,
            **details,
        }
        line = log.max_row + 1
        for col, header in enumerate(headers, 1):
            cell = write_literal(log, line, col, data.get(header))
            if header == "Source URL" and data.get(header) and safe_url(data[header]):
                cell.hyperlink = data[header]
                cell.style = "Hyperlink"

    for row_no, result in enumerate(results, 2):
        sources = {s.id: s for s in result.sources}
        for index, (key, label) in enumerate(FIELDS.items(), len(frame.columns) + 1):
            fact = result.facts[key]
            valid = [
                e
                for e in fact.evidence
                if e.source_id in sources and safe_url(sources[e.source_id].url)
            ]
            cell = sheet.cell(row_no, index)
            if fact.value is not None and valid:
                cell.hyperlink = sources[valid[0].source_id].url
                cell.style = "Hyperlink"
                prefix = (
                    "FICTIONAL DEMO — NOT VERIFIED\n"
                    if result.demo
                    else "Validated against public Google search excerpts; review the source.\n"
                )
                cell.comment = Comment(
                    prefix
                    + "\n\n".join(f"{sources[e.source_id].url}\nQuote: {e.quote}" for e in valid),
                    "Brand Research",
                )
            else:
                cell.value = UNVERIFIED
            for evidence in valid or [None]:
                source = sources[evidence.source_id] if evidence else None
                append_log(
                    result,
                    row_no,
                    Event="field",
                    Field=label,
                    Value=cell.value,
                    Status=("Demo" if result.demo else "Verified")
                    if valid and fact.value is not None
                    else UNVERIFIED,
                    **{
                        "Source URL": source.url if source else "",
                        "Source title": source.title if source else "",
                        "Source tier": source.kind if source else "",
                        "Evidence quote": evidence.quote if evidence else "",
                        "Query": source.query if source else "",
                    },
                )
        for source in result.sources:
            append_log(
                result,
                row_no,
                Event="source",
                **{
                    "Source URL": source.url,
                    "Source title": source.title,
                    "Source tier": source.kind,
                    "Evidence quote": source.snippet,
                    "Query": source.query,
                },
            )
        for event in result.events:
            append_log(result, row_no, **event)
        for note in result.notes:
            append_log(result, row_no, Event="note", Message=note)
        if result.cache_hit:
            append_log(
                result,
                row_no,
                Event="cache",
                Message="Reused session cache; original evidence timestamp retained.",
            )

    about = book.create_sheet("Read Me")
    about.append(["Item", "Details"])
    for item, detail in {
        "Data mode": "FICTIONAL DEMO: all source pages and facts are test fixtures, not real research."
        if any(r.demo for r in results)
        else "Live Google search through SerpApi; OpenAI extracts evidence-backed facts.",
        "Source links": "Each supported research cell links to its own evidence page. Comments and Research Log contain quoted evidence and all supporting sources. Input columns are preserved as values.",
        "Verified meaning": "Automated checks confirm a cited URL, verbatim search excerpt and value support. This is not human verification or a full-page/paywall review. Google excerpts may be incomplete or stale.",
        "Not acquired": "Requires explicit independent/never-acquired evidence plus an acquisition search and independent corroboration. Absence of acquisition results is insufficient.",
        "Latest acquisition": "Latest completed controlling acquisition found as of the research timestamp, including controlling owner transactions; excludes investments, licensing and pending deals. Later events can be missed.",
        "Unknowns": "Unable to verify means evidence is missing, ambiguous, conflicting, incomplete, or an API limit/error prevented verification. It is never evidence of no acquisition.",
        "Access": "Only SerpApi-provided public Google excerpts are processed. The app does not fetch or scrape source pages, protected content, or LinkedIn profiles.",
        "API usage": str(usage or {}),
        "Time": "All workbook timestamps are UTC. Cached results retain their original timestamp.",
    }.items():
        about.append([item, detail])
    for ws in book:
        polish(ws)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def example_workbook(context: str = "Parent Company") -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "Brands"
    sheet.append(["Brand", context])
    sheet.append(
        ["Aurora Tea", "Northstar Consumer Group" if context == "Parent Company" else "Tea"]
    )
    sheet.append(
        ["Harbor Soap", "Harbor Works" if context == "Parent Company" else "Personal care"]
    )
    sheet.append(["Mystery Brand", "Unknown"])
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()
