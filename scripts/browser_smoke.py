"""Exercise the running app with real Chromium, without any provider API calls.

Run: python -m scripts.browser_smoke --base-url http://127.0.0.1:8501
"""

import argparse
import shutil
from pathlib import Path

from openpyxl import load_workbook
from playwright.sync_api import expect, sync_playwright

from brand_research.excel import example_workbook, read_input
from brand_research.models import NOT_ACQUIRED, UNVERIFIED


def check_download(path: Path, expected_context: str):
    book = load_workbook(path)
    assert book.sheetnames == ["Brand Research", "Research Log", "Read Me"]
    sheet = book["Brand Research"]
    expected = read_input(example_workbook(expected_context))
    assert [sheet.cell(1, c).value for c in (1, 2)] == list(expected.columns)
    for row, values in enumerate(expected.itertuples(index=False, name=None), 2):
        assert [sheet.cell(row, c).value for c in (1, 2)] == list(values)
    for row in (2, 3):
        for col in range(3, 8):
            cell = sheet.cell(row, col)
            assert cell.hyperlink and cell.hyperlink.target.startswith("https://")
            assert ".example/" in cell.hyperlink.target
            assert "FICTIONAL DEMO" in cell.comment.text
    assert sheet["F3"].value == NOT_ACQUIRED
    for col in range(3, 8):
        assert sheet.cell(4, col).value == UNVERIFIED
        assert sheet.cell(4, col).hyperlink is None
    assert book["Research Log"].max_row > 20
    book.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8501")
    parser.add_argument("--output-dir", type=Path, default=Path("work/browser-smoke"))
    parser.add_argument("--executable-path", default=shutil.which("chromium"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, executable_path=args.executable_path, args=["--no-sandbox"]
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.base_url, wait_until="networkidle")
        expect(page.get_by_role("heading", name="Every brand has a beginning.")).to_be_visible()
        page.screenshot(path=str(args.output_dir / "desktop-initial.png"))

        def research_download(filename, context):
            start = page.get_by_role("button", name="Start research", exact=True)
            download_button = page.get_by_role(
                "button", name="↓ Download researched Excel workbook", exact=True
            )
            start.click()
            expect(download_button).to_be_visible()
            with page.expect_download() as download:
                download_button.click()
            target = args.output_dir / filename
            download.value.save_as(target)
            check_download(target, context)
            assert page.get_by_test_id("stException").count() == 0
            print(f"PASS research/download/hyperlinks: {filename}")

        research_download("demo-default.xlsx", "Parent Company")
        page.screenshot(path=str(args.output_dir / "desktop-results.png"))
        page.get_by_role("tab", name="Evidence & activity", exact=True).click()
        expect(page.get_by_text("Inspect a brand", exact=True)).to_be_visible()
        print("PASS evidence tab")

        for context, name in [("Parent Company", "parent-company"), ("Category", "category")]:
            # Fresh sessions ensure the wait cannot see an old run's download button.
            page.close()
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(args.base_url, wait_until="networkidle")
            page.get_by_text("Upload Excel", exact=True).click()
            start = page.get_by_role("button", name="Start research", exact=True)
            expect(start).to_be_disabled()
            input_path = args.output_dir / f"input-{name}.xlsx"
            input_path.write_bytes(example_workbook(context))
            page.locator('input[type="file"]').set_input_files(str(input_path))
            expect(
                page.get_by_text("3 input rows · 2 original columns retained", exact=True)
            ).to_be_visible()
            expect(start).to_be_enabled()
            research_download(f"uploaded-{name}-results.xlsx", context)

        # The supplied environment has no keys. A real source is uploaded at this point,
        # so this verifies credential gating, rather than the fictional-input guard.
        page.get_by_text("Live research", exact=True).click()
        expect(start).to_be_disabled()
        expect(
            page.get_by_text("Live research needs SERPAPI_API_KEY and OPENAI_API_KEY", exact=False)
        ).to_be_visible()
        assert page.get_by_test_id("stException").count() == 0
        print("PASS live credential gate")

        mobile = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True)
        mobile.goto(args.base_url, wait_until="networkidle")
        expect(mobile.get_by_role("heading", name="Every brand has a beginning.")).to_be_visible()
        mobile.screenshot(path=str(args.output_dir / "mobile-initial.png"))
        assert mobile.get_by_test_id("stException").count() == 0
        print("PASS mobile layout")
        assert not errors, errors
        browser.close()
        print("PASS no browser JavaScript or Streamlit exceptions")


if __name__ == "__main__":
    main()
