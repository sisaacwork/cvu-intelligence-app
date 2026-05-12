"""Geography selection: list agglomerations / regions / countries / cities
that have buildings tall enough to include in the pipeline.

Used by the UI to populate the multi-select listbox.
"""

import mysql.connector


_LIST_QUERIES = {
    "agglomeration": """
        SELECT a.id, a.name_intl, COUNT(b.id) AS cnt
        FROM agglomerations a
        JOIN v2_cities ci ON ci.agglomeration_id = a.id
        JOIN ctbuh_building b ON b.city_id = ci.id
        WHERE b.deleted_at IS NULL
          AND b.structure_type = 'building'
          AND b.height_architecture >= %s
        GROUP BY a.id, a.name_intl
        HAVING cnt > 0
        ORDER BY cnt DESC
    """,
    "region": """
        SELECT r.id, r.name, COUNT(b.id) AS cnt
        FROM v2_regions r
        JOIN v2_countries co ON co.region_id = r.id
        JOIN v2_cities ci ON ci.country_id = co.id
        JOIN ctbuh_building b ON b.city_id = ci.id
        WHERE b.deleted_at IS NULL
          AND b.structure_type = 'building'
          AND b.height_architecture >= %s
        GROUP BY r.id, r.name
        HAVING cnt > 0
        ORDER BY cnt DESC
    """,
    "country": """
        SELECT co.id, co.name, COUNT(b.id) AS cnt
        FROM v2_countries co
        JOIN v2_cities ci ON ci.country_id = co.id
        JOIN ctbuh_building b ON b.city_id = ci.id
        WHERE b.deleted_at IS NULL
          AND b.structure_type = 'building'
          AND b.height_architecture >= %s
        GROUP BY co.id, co.name
        HAVING cnt > 0
        ORDER BY cnt DESC
    """,
    "city": """
        SELECT ci.id, ci.name, COUNT(b.id) AS cnt
        FROM v2_cities ci
        JOIN ctbuh_building b ON b.city_id = ci.id
        WHERE b.deleted_at IS NULL
          AND b.structure_type = 'building'
          AND b.height_architecture >= %s
        GROUP BY ci.id, ci.name
        HAVING cnt > 0
        ORDER BY cnt DESC
    """,
}


def list_geographies(mysql_cfg, geo_type, min_height=75):
    """Return [{'id', 'name', 'count'}, ...] sorted by building count desc.

    geo_type: one of 'agglomeration', 'region', 'country', 'city'.
    min_height: only count buildings >= this height.
    """
    if geo_type not in _LIST_QUERIES:
        raise ValueError(f"Unknown geo_type: {geo_type!r}")

    conn = mysql.connector.connect(
        host=mysql_cfg["host"],
        port=int(mysql_cfg["port"]),
        user=mysql_cfg["user"],
        password=mysql_cfg["password"],
        database=mysql_cfg["database"],
    )
    try:
        cur = conn.cursor()
        cur.execute(_LIST_QUERIES[geo_type], (min_height,))
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    return [{"id": r[0], "name": r[1], "count": r[2]} for r in rows]


def geo_where_clause(geo_type, ids):
    """SQL WHERE fragment + parameter list for the chosen geography type.

    geo_type: 'agglomeration', 'region', 'country', or 'city'
    ids: list of integer IDs
    Returns (clause_str, params_list).
    """
    placeholders = ",".join(["%s"] * len(ids))
    mapping = {
        "agglomeration": f"a.id IN ({placeholders})",
        "region":        f"ci.region_id IN ({placeholders})",
        "country":       f"ci.country_id IN ({placeholders})",
        "city":          f"ci.id IN ({placeholders})",
    }
    if geo_type not in mapping:
        raise ValueError(f"Unknown geo_type: {geo_type!r}")
    return mapping[geo_type], list(ids)
