import csv
from datetime import datetime, timezone

from goldthread.review import REVIEW_COLUMNS, export_review, import_review

NOW = lambda: datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)  # noqa: E731


def read_sheet(path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return reader.fieldnames, list(reader)


def write_sheet(path, columns, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def row_for(rows, fragment):
    return next(r for r in rows if fragment in r["quote"])


def test_export_bom_header_and_rows(extracted, tmp_path):
    path = tmp_path / "review" / "sheet.csv"
    n = export_review(extracted, path)
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    columns, rows = read_sheet(path)
    assert columns == REVIEW_COLUMNS and n == len(rows) == len(extracted.records()) == 8
    assert row_for(rows, "1700 C")["quote_check"] == "quote not found in passage"
    assert row_for(rows, "TR-123")["quote_check"] == "ok"


def test_import_verified_sets_reviewer_and_time(extracted, tmp_path):
    path = tmp_path / "sheet.csv"
    export_review(extracted, path)
    columns, rows = read_sheet(path)
    row_for(rows, "TR-123")["decision"] = "verified"
    write_sheet(path, columns, rows)
    report = import_review(extracted, path, "alice", now=NOW)
    rec = extracted.record(row_for(rows, "TR-123")["id"])
    assert report.applied == 1 and (rec.status, rec.reviewed_by, rec.reviewed_at) == (
        "verified", "alice", "2026-11-21T12:00:00Z")


def test_import_rejected(extracted, tmp_path):
    path = tmp_path / "sheet.csv"
    export_review(extracted, path)
    columns, rows = read_sheet(path)
    row_for(rows, "1700 C")["decision"] = "rejected"
    write_sheet(path, columns, rows)
    import_review(extracted, path, "alice", now=NOW)
    assert extracted.record(row_for(rows, "1700 C")["id"]).status == "rejected"


def test_import_corrected_fields(extracted, tmp_path):
    path = tmp_path / "sheet.csv"
    export_review(extracted, path)
    columns, rows = read_sheet(path)
    row = row_for(rows, "TR-123")
    row["decision"], row["corrected_fields_json"] = "corrected", '{"title": "Fuel performance report"}'
    write_sheet(path, columns, rows)
    report = import_review(extracted, path, "bob", now=NOW)
    rec = extracted.record(row["id"])
    assert report.applied == 1 and rec.status == "corrected" and rec.fields["title"] == "Fuel performance report"


def test_import_excel_bom_reordered_columns_and_edited_quote(extracted, tmp_path):  # Review Focus 2
    path = tmp_path / "sheet.csv"
    export_review(extracted, path)
    columns, rows = read_sheet(path)
    row = row_for(rows, "TR-123")
    row["decision"], row["corrected_quote"] = "corrected", "Fuel performance is proven in report TR-999."
    write_sheet(path, list(reversed(columns)), rows)  # Excel-style save: BOM, different column order
    report = import_review(extracted, path, "carol", now=NOW)
    rec = extracted.record(row["id"])
    assert report.reverified_failed == [row["id"]] and report.applied == 0
    assert rec.status == "draft" and rec.flags[0].startswith("quote_failed")


def test_import_verified_with_failing_quote_stays_draft(extracted, tmp_path):
    path = tmp_path / "sheet.csv"
    export_review(extracted, path)
    columns, rows = read_sheet(path)
    row_for(rows, "1700 C")["decision"] = "verified"
    write_sheet(path, columns, rows)
    report = import_review(extracted, path, "alice", now=NOW)
    assert report.reverified_failed == [row_for(rows, "1700 C")["id"]]
    assert extracted.record(row_for(rows, "1700 C")["id"]).status == "draft"


def test_import_unknown_id_and_bad_json_reported(extracted, tmp_path):
    path = tmp_path / "sheet.csv"
    export_review(extracted, path)
    columns, rows = read_sheet(path)
    rows[0]["id"], rows[0]["decision"] = "NOPE-1", "verified"
    rows[1]["decision"], rows[1]["corrected_fields_json"] = "corrected", "{bad"
    rows[2]["decision"] = "maybe"
    write_sheet(path, columns, rows)
    report = import_review(extracted, path, "alice", now=NOW)
    assert report.rejected_rows == ["row 2: unknown id NOPE-1", "row 3: invalid corrected_fields_json",
                                    "row 4: unknown decision 'maybe'"]
