"""MySQL data extraction for the CVU Intelligence pipeline.

Ports pull_mysql_data from cvu_intelligence_generator.py with no
behavioural changes. Returns raw tuples — the payload module transforms
them into the dict shape WordPress expects.
"""

import mysql.connector

from .geo import geo_where_clause
from .constants import TEAM_CATEGORIES


def pull_mysql_data(cfg, geo_type, geo_ids, log=print, min_height=75):
    """Pull buildings + project teams + country/city mapping for the geography.

    Returns (buildings, teams, team_builds, country_city_map):
      buildings        — list of 20-tuples (raw CTBUH columns).
      teams            — {category_name: [(company_name, count), ...]}
      team_builds      — {category_name: {company_name: [(bid, bname, ht, year), ...]}}
      country_city_map — {country_name: [city1, city2, ...]} for boundary lookup.
    """
    log("Connecting to MySQL...")
    conn = mysql.connector.connect(
        host=cfg["host"],
        port=int(cfg["port"]),
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
    )
    cur = conn.cursor()

    geo_clause, geo_params = geo_where_clause(geo_type, geo_ids)

    # --- buildings ---
    log("Querying buildings...")
    sql = f"""
    SELECT
        b.id,
        b.name_intl,
        ci.name AS city,
        b.height_architecture,
        b.floors_above,
        b.completed,
        b.material_displayed,
        b.status,
        b.main_use_01,
        b.main_use_02,
        b.main_use_03,
        b.main_use_04,
        b.main_use_05,
        b.gross_floor_area,
        b.apartments,
        b.hotel_rooms,
        b.elevators,
        b.parking,
        b.latitude,
        b.longitude
    FROM ctbuh_building b
    JOIN v2_cities ci ON b.city_id = ci.id
    LEFT JOIN agglomerations a ON ci.agglomeration_id = a.id
    WHERE {geo_clause}
      AND b.deleted_at IS NULL
      AND b.structure_type = 'building'
      AND b.height_architecture >= %s
      AND b.status NOT IN ('VIS')
    ORDER BY b.height_architecture DESC
    """
    cur.execute(sql, geo_params + [min_height])
    buildings = cur.fetchall()
    log(f"  Found {len(buildings)} buildings.")

    bids = [str(r[0]) for r in buildings]

    teams = {}
    team_builds = {}
    if bids:
        log("Querying project teams...")
        for cat_id, cat_name in TEAM_CATEGORIES.items():
            sql_team = f"""
            SELECT co.name, COUNT(DISTINCT bcn.building_id) AS cnt
            FROM ctbuh_building_company_new bcn
            JOIN ctbuh_company co ON bcn.company_id = co.id
            WHERE bcn.building_id IN ({','.join(bids)})
              AND bcn.category_id = %s
            GROUP BY co.name
            ORDER BY cnt DESC
            """
            cur.execute(sql_team, (cat_id,))
            teams[cat_name] = [(row[0], row[1]) for row in cur.fetchall()]

            company_buildings = {}
            for co_name, _ in teams[cat_name]:
                sql_cb = f"""
                SELECT DISTINCT bcn.building_id, b.name_intl,
                       b.height_architecture, b.completed
                FROM ctbuh_building_company_new bcn
                JOIN ctbuh_company co ON bcn.company_id = co.id
                JOIN ctbuh_building b ON bcn.building_id = b.id
                WHERE bcn.building_id IN ({','.join(bids)})
                  AND bcn.category_id = %s
                  AND co.name = %s
                ORDER BY b.name_intl
                """
                cur.execute(sql_cb, (cat_id, co_name))
                company_buildings[co_name] = [
                    (r[0], r[1], r[2], r[3]) for r in cur.fetchall()
                ]
            team_builds[cat_name] = company_buildings
            log(f"  {cat_name}: {len(teams[cat_name])} firms")

    log("Querying distinct countries and cities...")
    sql_geo = f"""
    SELECT DISTINCT co.name AS country, ci.name AS city
    FROM ctbuh_building b
    JOIN v2_cities ci ON b.city_id = ci.id
    JOIN v2_countries co ON ci.country_id = co.id
    LEFT JOIN agglomerations a ON ci.agglomeration_id = a.id
    WHERE {geo_clause}
      AND b.deleted_at IS NULL
      AND b.structure_type = 'building'
      AND b.height_architecture >= %s
    """
    cur.execute(sql_geo, geo_params + [min_height])
    country_city_rows = cur.fetchall()
    country_city_map = {}
    for country, city in country_city_rows:
        country_city_map.setdefault(country, []).append(city)
    log(f"  {len(country_city_map)} distinct countries, "
        f"{len(country_city_rows)} country-city pairs.")

    cur.close()
    conn.close()
    log("MySQL done.")
    return buildings, teams, team_builds, country_city_map


def get_ghsl_search_names(mysql_cfg, geo_type, geo_ids, log=print):
    """Return list of agglomeration name_intl values to look up in GHSL.

    For country/region selections we need to query MySQL to enumerate the
    agglomerations contained within. For agglomeration/city, the caller
    already has names.
    """
    conn = mysql.connector.connect(
        host=mysql_cfg["host"], port=int(mysql_cfg["port"]),
        user=mysql_cfg["user"], password=mysql_cfg["password"],
        database=mysql_cfg["database"],
    )
    try:
        cur = conn.cursor()
        placeholders = ",".join(["%s"] * len(geo_ids))

        if geo_type == "country":
            cur.execute(f"""
                SELECT DISTINCT a.name_intl
                FROM agglomerations a
                JOIN v2_cities ci ON ci.agglomeration_id = a.id
                WHERE ci.country_id IN ({placeholders})
                ORDER BY a.name_intl
            """, geo_ids)
        elif geo_type == "region":
            cur.execute(f"""
                SELECT DISTINCT a.name_intl
                FROM agglomerations a
                JOIN v2_cities ci ON ci.agglomeration_id = a.id
                JOIN v2_countries co ON ci.country_id = co.id
                WHERE co.region_id IN ({placeholders})
                ORDER BY a.name_intl
            """, geo_ids)
        else:
            return []

        names = [r[0] for r in cur.fetchall()]
        cur.close()
    finally:
        conn.close()
    return names
