from app.reference_controls import REPORTED_TOTALS, compare, read_controls, summarize_history


def test_user_reported_controls_reconcile_totals():
    controls, totals = read_controls()
    assert len(controls) == 52
    assert totals == REPORTED_TOTALS
    assert controls["28"]["polling_tables"] == 7118
    assert controls["28"]["polling_places"] == 1070


def test_exterior_never_counts_as_local_table():
    records = [
        {"province_code": "01", "municipality_code": "001", "district": "01", "section": "001", "is_exterior": False},
        {"province_code": "01", "municipality_code": "001", "district": "01", "section": "001", "is_exterior": False},
        {"province_code": "01", "municipality_code": "999", "district": "09", "section": "000", "is_exterior": True},
    ]
    summary = summarize_history(records)
    assert summary["01"] == {"municipalities": 1, "districts": 1, "sections": 1, "polling_tables": 2}
    controls, _ = read_controls()
    mismatches = compare(controls, summary)
    assert any(m["province_code"] == "01" and m["field"] == "polling_tables" for m in mismatches)
