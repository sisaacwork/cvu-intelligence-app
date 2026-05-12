"""GHSL (Global Human Settlement Layer) data extraction from Postgres.

Pulls emissions, socioeconomic, hazard, and population time series for
the urban centres that match a selected geography, then aggregates them
into a single dict matching the shape consumed by the WP template's
chart aggregations.
"""

import psycopg2

from .mysql_pull import get_ghsl_search_names


def _find_ucdb_ids(pg_cur, search_names, log=print):
    """For each name, find matching ucdb rows in general_characteristics.

    Tries an exact-ish ILIKE first, falls back to first-word match.
    Returns deduplicated list of (ucdb_id, name, population, urban_area).
    """
    seen = set()
    matches = []
    for name in search_names:
        pg_cur.execute("""
            SELECT ucdb_id, name, "GC_POP_TOT_2025", "GC_UCA_KM2_2025"
            FROM general_characteristics
            WHERE name ILIKE %s
            LIMIT 3
        """, (f"%{name}%",))
        rows = pg_cur.fetchall()
        if not rows:
            first_word = name.split("–")[0].split("-")[0].strip()
            if first_word != name:
                pg_cur.execute("""
                    SELECT ucdb_id, name, "GC_POP_TOT_2025", "GC_UCA_KM2_2025"
                    FROM general_characteristics
                    WHERE name ILIKE %s
                    LIMIT 3
                """, (f"%{first_word}%",))
                rows = pg_cur.fetchall()
        for r in rows:
            if r[0] not in seen:
                seen.add(r[0])
                matches.append(r)
    return matches


def _pull_one(pg_cur, ucdb_id):
    """Pull emissions, socioeconomic, hazard, and population for one ucdb_id."""
    pg_cur.execute("""
        SELECT
            "EM_CO2_TOT_1975", "EM_CO2_TOT_1990", "EM_CO2_TOT_2000",
            "EM_CO2_TOT_2005", "EM_CO2_TOT_2010", "EM_CO2_TOT_2015",
            "EM_CO2_TOT_2020", "EM_CO2_TOT_2022",
            "EM_CO2_ENE_2022", "EM_CO2_TRA_2022",
            "EM_CO2_IND_2022", "EM_CO2_RES_2022",
            "EM_PM2_TOT_2020"
        FROM emissions WHERE "ID_UC_G0" = %s
    """, (ucdb_id,))
    em = pg_cur.fetchone()

    pg_cur.execute("""
        SELECT
            "SC_SEC_GDP_1990", "SC_SEC_GDP_1995", "SC_SEC_GDP_2000",
            "SC_SEC_GDP_2005", "SC_SEC_GDP_2010", "SC_SEC_GDP_2015",
            "SC_SEC_GDP_2020",
            "SC_SEC_HDI_1990", "SC_SEC_HDI_2000", "SC_SEC_HDI_2010",
            "SC_SEC_HDI_2020"
        FROM socioeconomic WHERE "ID_UC_G0" = %s
    """, (ucdb_id,))
    se = pg_cur.fetchone()

    pg_cur.execute("""
        SELECT
            "HZ_CEV_TEV_2015", "HZ_CON_TOT_2020",
            "HZ_CEV_FLO_2015", "HZ_CEV_EAR_2015", "HZ_CEV_TCY_2015"
        FROM hazard_risk WHERE "ID_UC_G0" = %s
    """, (ucdb_id,))
    hr = pg_cur.fetchone()

    pg_cur.execute("""
        SELECT
            "GH_POP_TOT_1975", "GH_POP_TOT_1990", "GH_POP_TOT_1995",
            "GH_POP_TOT_2000", "GH_POP_TOT_2005", "GH_POP_TOT_2010",
            "GH_POP_TOT_2015", "GH_POP_TOT_2020"
        FROM ghsl WHERE "ID_UC_G0" = %s
    """, (ucdb_id,))
    pop_ts = pg_cur.fetchone()

    return {"em": em, "se": se, "hr": hr, "pop_ts": pop_ts}


def _safe_float(v):
    """GHSL stores some values as '-' or other non-numeric text; coerce safely."""
    if v is None:
        return 0.0
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def _aggregate(gc_matches, raw_list, log=print):
    """Combine multiple GHSL records: sum scalars, population-weighted-avg ratios."""
    n = len(gc_matches)
    if n == 0:
        return None

    sf = _safe_float

    total_pop = sum(sf(r[2]) for r in gc_matches)
    total_area = sum(sf(r[3]) for r in gc_matches)

    ghsl = {
        "name":      f"{n} urban centres",
        "ucdb_id":   gc_matches[0][0] if n == 1 else "aggregate",
        "population": total_pop,
        "urban_area": total_area,
    }

    def fsum(vals):
        return sum(sf(v) for v in vals)

    def wavg(vals, pops):
        pairs = [(sf(v), sf(p)) for v, p in zip(vals, pops) if sf(v) != 0 and sf(p) != 0]
        if not pairs:
            return 0
        total_w = sum(p for _, p in pairs)
        if total_w == 0:
            return sum(v for v, _ in pairs) / len(pairs)
        return sum(v * p for v, p in pairs) / total_w

    pops = [sf(r[2]) for r in gc_matches]

    em_rows = [d["em"] for d in raw_list if d["em"]]
    if em_rows:
        ghsl["co2_years"]   = [1975, 1990, 2000, 2005, 2010, 2015, 2020, 2022]
        ghsl["co2_values"]  = [fsum(r[i] for r in em_rows) for i in range(8)]
        ghsl["co2_sectors"] = {
            "Energy":      fsum(r[8]  for r in em_rows),
            "Transport":   fsum(r[9]  for r in em_rows),
            "Industrial":  fsum(r[10] for r in em_rows),
            "Residential": fsum(r[11] for r in em_rows),
        }
        pm_vals = [r[12] for r in em_rows]
        pm_pops = [pops[i] for i, d in enumerate(raw_list) if d["em"]]
        ghsl["pm25"] = wavg(pm_vals, pm_pops) if any(v for v in pm_vals) else None

    se_rows = [d["se"] for d in raw_list if d["se"]]
    if se_rows:
        ghsl["gdp_years"]  = [1990, 1995, 2000, 2005, 2010, 2015, 2020]
        ghsl["gdp_values"] = [fsum(r[i] for r in se_rows) for i in range(7)]
        ghsl["hdi_years"]  = [1990, 2000, 2010, 2020]
        se_pops = [pops[i] for i, d in enumerate(raw_list) if d["se"]]
        ghsl["hdi_values"] = [
            wavg([r[7 + j] for r in se_rows], se_pops) for j in range(4)
        ]

    hr_rows = [d["hr"] for d in raw_list if d["hr"]]
    if hr_rows:
        hr_pops = [pops[i] for i, d in enumerate(raw_list) if d["hr"]]
        ghsl["hazard"] = {
            "climate_events":  wavg([r[0] for r in hr_rows], hr_pops),
            "conflict_events": wavg([r[1] for r in hr_rows], hr_pops),
            "flood_risk":      wavg([r[2] for r in hr_rows], hr_pops),
            "earthquake_risk": wavg([r[3] for r in hr_rows], hr_pops),
            "cyclone_risk":    wavg([r[4] for r in hr_rows], hr_pops),
        }

    pop_rows = [d["pop_ts"] for d in raw_list if d.get("pop_ts")]
    if pop_rows:
        ghsl["pop_ts_years"]  = [1975, 1990, 1995, 2000, 2005, 2010, 2015, 2020]
        ghsl["pop_ts_values"] = [fsum(r[i] for r in pop_rows) for i in range(8)]
        ghsl["pop_by_year"]   = dict(zip(ghsl["pop_ts_years"], ghsl["pop_ts_values"]))

    return ghsl


def pull_ghsl_data(pg_cfg, geo_type, geo_ids, geo_names, mysql_cfg, log=print):
    """Pull GHSL data, aggregating across all relevant urban centres.

    For agglomeration / city: search GHSL by the selected names directly.
    For country: find all agglomerations in those countries (via MySQL),
                 then look up each in GHSL and aggregate.
    For region:  find all agglomerations in those regions (via MySQL chain),
                 then look up each in GHSL and aggregate.
    """
    if geo_type in ("country", "region"):
        search_names = get_ghsl_search_names(mysql_cfg, geo_type, geo_ids, log)
        log(f"  Found {len(search_names)} agglomerations to look up in GHSL.")
    else:
        search_names = list(geo_names)

    if not search_names:
        log("  WARNING: No names to search in GHSL.")
        return None

    log("Connecting to Postgres (GHSL)...")
    conn = psycopg2.connect(
        host=pg_cfg["host"], port=int(pg_cfg["port"]),
        user=pg_cfg["user"], password=pg_cfg["password"],
        database=pg_cfg["database"], sslmode="require",
    )
    try:
        cur = conn.cursor()
        gc_matches = _find_ucdb_ids(cur, search_names, log)
        if not gc_matches:
            log("  No GHSL matches found.")
            return None
        log(f"  Matched {len(gc_matches)} urban centres in GHSL.")

        raw_list = []
        for match in gc_matches:
            raw_list.append(_pull_one(cur, match[0]))

        cur.close()
    finally:
        conn.close()

    return _aggregate(gc_matches, raw_list, log)
