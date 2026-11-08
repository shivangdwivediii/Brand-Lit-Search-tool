from datetime import datetime
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import pytest
from openpyxl import Workbook, load_workbook

from brand_research.engine import ResearchEngine
from brand_research.excel import MAX_BYTES, InputError, export_workbook, read_input


def workbook_bytes(headers, rows):
    book = Workbook()
    book.active.append(headers)
    for row in rows:
        book.active.append(row)
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def test_both_context_columns_extra_values_and_header_spelling_preserved():
    headers = [" Brand ", "Parent Company", " CATEGORY ", "Code", "Recorded", "Numeric"]
    rows = [
        ["Aurora Tea", "Northstar Consumer Group", "Tea", "001", datetime(2026, 1, 1), 42],
        [None, "Unknown", "Tea", "002", None, 0],
    ]
    frame = read_input(workbook_bytes(headers, rows))
    assert list(frame.columns) == headers
    results = ResearchEngine().run(frame, "Fast", demo=True)
    assert "Parent Company: Northstar Consumer Group" in results[0].context
    assert "CATEGORY: Tea" in results[0].context
    output = load_workbook(BytesIO(export_workbook(frame, results)))["Brand Research"]
    for row, values in enumerate(rows, 2):
        assert [output.cell(row, c).value for c in range(1, 7)] == values


@pytest.mark.parametrize(
    "case", ["empty", "blank_brands", "rows", "columns", "reserved", "long_context"]
)
def test_actionable_input_validation(case):
    headers, rows = ["Brand", "Category"], [["Example", "Tea"]]
    if case == "empty":
        rows = []
    elif case == "blank_brands":
        rows = [[None, "Tea"], [" ", "Soap"]]
    elif case == "rows":
        rows *= 201
    elif case == "columns":
        headers += [f"Extra{i}" for i in range(49)]
        rows = [["Example", "Tea", *(["x"] * 49)]]
    elif case == "reserved":
        headers += ["Research status"]
        rows = [["Example", "Tea", "Old"]]
    else:
        rows = [["Example", "X" * 301]]
    with pytest.raises(InputError):
        read_input(workbook_bytes(headers, rows))


def test_upload_size_limit():
    with pytest.raises(InputError, match="10 MB"):
        read_input(b"x" * (MAX_BYTES + 1))


def test_xml_entity_workbook_is_rejected_as_input_error():
    original = workbook_bytes(["Brand", "Category"], [["Example", "Tea"]])
    output = BytesIO()
    with ZipFile(BytesIO(original)) as src, ZipFile(output, "w", ZIP_DEFLATED) as target:
        for name in src.namelist():
            data = src.read(name)
            if name == "xl/worksheets/sheet1.xml":
                data = b'<!DOCTYPE worksheet [<!ENTITY malicious "content">]>' + data.replace(
                    b"Example", b"&malicious;"
                )
            target.writestr(name, data)
    with pytest.raises(InputError):
        read_input(output.getvalue())


def test_empty_workbook():
    book = Workbook()
    output = BytesIO()
    book.save(output)
    with pytest.raises(InputError):
        read_input(output.getvalue())


def test_blank_rows_ignored_but_duplicate_data_rows_retained():
    frame = read_input(
        workbook_bytes(
            ["Brand", "Category"], [["Aurora Tea", "Tea"], [None, None], ["Aurora Tea", "Tea"]]
        )
    )
    assert len(frame) == 2
    assert frame["Brand"].tolist() == ["Aurora Tea", "Aurora Tea"]
    pd.testing.assert_frame_equal(
        frame,
        pd.DataFrame(
            {"Brand": ["Aurora Tea", "Aurora Tea"], "Category": ["Tea", "Tea"]}, dtype=object
        ),
    )
