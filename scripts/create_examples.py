from pathlib import Path

from brand_research.excel import example_workbook


def main():
    root = Path(__file__).resolve().parents[1] / "examples"
    root.mkdir(exist_ok=True)
    for context, filename in [
        ("Parent Company", "brand_parent_company.xlsx"),
        ("Category", "brand_category.xlsx"),
    ]:
        (root / filename).write_bytes(example_workbook(context))
        print(f"Created examples/{filename}")


if __name__ == "__main__":
    main()
