from app.reference_import import HISTORY_HEADERS, parse_census, parse_history


def history_fixture():
    rows = [HISTORY_HEADERS]
    for province in range(1, 53):
        cc = (province - 1) % 19 + 1
        for municipality, district, section, label, name in ((1, 1, 1, "A", "MUNICIPIO DE PRUEBA"), (999, 9, 0, "U", f"CERA{province:02d}")):
            code = f"{cc:02d}{province:02d}{municipality:03d}{district:02d}{section:03d}{label}"
            rows.append((code, 2023, 7, cc, f"CCAA DE PRUEBA {cc}", province, f"PROVINCIA DE PRUEBA {province}", municipality, name, district, section, label, 100))
    return rows


def census_fixture():
    rows = [[None] * 5 for _ in range(9)]
    rows[1][0] = "Elecciones a Cortes Generales 2026"
    rows[3][0] = "Censo de consulta"
    rows[8] = ["Total general", None, 5200, 520, 5720]
    for province in range(1, 53):
        rows.append((f"{province:02d}", f"PROVINCIA DE PRUEBA {province}", 100, 10, 110))
    return rows


def test_historical_exterior_is_not_municipality():
    records, communities, provinces, municipalities, exterior = parse_history(history_fixture())
    assert len(records) == 104
    assert len(communities) == 19 and len(provinces) == 52
    assert len(municipalities) == 52 and len(exterior) == 52
    assert sum(r["is_exterior"] for r in records) == 52
    assert "01999" not in municipalities


def test_history_rejects_duplicate_identity():
    rows = history_fixture()
    rows.append(rows[1])
    try:
        parse_history(rows)
        assert False, "duplicado aceptado"
    except ValueError as exc:
        assert "duplicada" in str(exc)


def test_census_is_consultation_and_totals_reconcile():
    records, totals = parse_census(census_fixture())
    assert len(records) == 52 and totals == {"residents_spain": 5200, "residents_abroad": 520, "total": 5720, "status": "consulta"}
    bad = census_fixture()
    bad[-1] = ("52", "PROVINCIA DE PRUEBA 52", 100, 10, 111)
    try:
        parse_census(bad)
        assert False, "total inconsistente aceptado"
    except ValueError as exc:
        assert "inconsistentes" in str(exc)
