from io import BytesIO
from zipfile import ZipFile

import pandas as pd
import pytest
from openpyxl import Workbook, load_workbook

from brand_research.demo import demo_research
from brand_research.excel import InputError, example_workbook, export_workbook, read_input
from brand_research.models import FIELDS, NOT_ACQUIRED, UNVERIFIED


@pytest.mark.parametrize("context", ["Parent Company", "Category"])
def test_original_columns_and_exact_cell_hyperlinks(context):
    frame = read_input(example_workbook(context))
    results = [demo_research(row["Brand"], row[context]) for _, row in frame.iterrows()]
    data = export_workbook(frame, results)
    book = load_workbook(BytesIO(data))
    sheet = book["Brand Research"]
    assert book.sheetnames == ["Brand Research", "Research Log", "Read Me"]
    assert [sheet.cell(1, i).value for i in (1, 2)] == list(frame.columns)
    assert [[sheet.cell(r, c).value for c in (1, 2)] for r in range(2, 5)] == frame.values.tolist()
    expected = ["history", "history", "history", "aurora-acquisition", "aurora-acquisition"]
    for col, suffix in enumerate(expected, 3):
        cell = sheet.cell(2, col)
        assert cell.hyperlink.target == next(
            s.url for s in results[0].sources if s.url.endswith(suffix)
        )
        assert "FICTIONAL DEMO" in cell.comment.text
        assert "Quote:" in cell.comment.text
    assert sheet.cell(3, 6).value == NOT_ACQUIRED
    for col in range(3, 8):
        assert sheet.cell(4, col).value == UNVERIFIED
        assert sheet.cell(4, col).hyperlink is None
    assert book["Research Log"].max_row > 15
    with ZipFile(BytesIO(data)) as archive:
        links = archive.read("xl/worksheets/_rels/sheet1.xml.rels").decode()
        assert "aurora-acquisition" in links
        assert 'TargetMode="External"' in links


def test_export_preserves_literal_input_without_executable_formulas():
    frame = pd.DataFrame({"Brand": ['=WEBSERVICE("bad")'], "Category": ["@SUM(1)"]})
    data = export_workbook(frame, [demo_research("Unknown")])
    sheet = load_workbook(BytesIO(data))["Brand Research"]
    assert sheet["A2"].value == frame.iloc[0, 0]
    assert sheet["A2"].data_type == "s"
    assert sheet["B2"].data_type == "s"


@pytest.mark.parametrize(
    "headers", [["Brand", "Other"], ["Brand", " brand ", "Category"], ["Brand", None, "Category"]]
)
def test_invalid_headers(headers):
    book = Workbook()
    book.active.append(headers)
    book.active.append(["X"] * len(headers))
    data = BytesIO()
    book.save(data)
    with pytest.raises(InputError):
        read_input(data.getvalue())


def test_formula_input_rejected():
    book = Workbook()
    book.active.append(["Brand", "Category"])
    book.active.append(["=1+1", "Tea"])
    data = BytesIO()
    book.save(data)
    with pytest.raises(InputError, match="Formula"):
        read_input(data.getvalue())


def test_invalid_file_and_result_count():
    with pytest.raises(InputError):
        read_input(b"not excel")
    with pytest.raises(ValueError):
        export_workbook(pd.DataFrame({"Brand": ["x"], "Category": ["y"]}), [])


def test_all_demo_facts_have_individual_support():
    result = demo_research("Aurora Tea")
    for key in FIELDS:
        fact = result.facts[key]
        assert str(fact.value) in fact.evidence[0].quote
