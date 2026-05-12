"""Transform raw MySQL/GHSL output into the JSON payload shape that
WordPress (POST /mds/v1/intelligence/publish) expects.

The desktop tool returns building rows as raw 20-tuples; WordPress
consumes objects keyed by name. All conversion lives here so the WP
contract stays decoupled from the column order in the CTBUH MySQL.

WordPress publish-route contract (mirrors intelligence-admin.php):
    {
      "tier":       "brief" | "report",
      "geo_type":   "agglomeration" | "region" | "country" | "city",
      "geo_name":   "Chicago–Milwaukee Agglomeration",
      "geo_ids":    [12, 47],
      "min_height": 75,
      "buildings":  [ { id, name, city, height, floors, completed,
                        material, status_code, status, function,
                        gfa, apartments, hotel_rooms, elevators,
                        parking, lat, lng }, ... ],
      "teams":      { "Developer": [{name, count, buildings: [...]}], ... },
      "ghsl":       { population, urban_area, co2_*, gdp_*, hdi_*, ... },
      "boundary":   [ { iso3, adm_levels, filter_names }, ... ]
    }
"""

from .helpers import get_function, get_status


def _safe_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_int(v):
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def building_to_dict(b):
    """Convert one raw MySQL row (20-tuple) to the WP payload dict."""
    return {
        "id":          b[0],
        "name":        b[1] or "",
        "city":        b[2] or "",
        "height":      _safe_float(b[3]),
        "floors":      _safe_int(b[4]),
        "completed":   _safe_int(b[5]),
        "material":    b[6] or "",
        "status_code": b[7] or "",
        "status":      get_status(b[7]),
        "function":    get_function(b),
        "gfa":         _safe_int(b[13]),
        "apartments":  _safe_int(b[14]),
        "hotel_rooms": _safe_int(b[15]),
        "elevators":   _safe_int(b[16]),
        "parking":     _safe_int(b[17]),
        "lat":         _safe_float(b[18]),
        "lng":         _safe_float(b[19]),
    }


def buildings_to_dicts(buildings):
    """Map a list of raw rows to WP payload dicts."""
    return [building_to_dict(b) for b in buildings]


def teams_to_dicts(teams, team_builds):
    """Combine the (name, count) lists and the per-company building dicts
    into one structure WordPress can render directly.

    teams       — {category: [(co_name, count), ...]}
    team_builds — {category: {co_name: [(bid, bname, ht, year), ...]}}

    Output:
      {
        "Developer": [
          {"name": "Magellan...", "count": 21,
           "buildings": [{"id": 12, "name": "Vista Tower", "height": 363, "year": 2020}, ...]},
          ...
        ],
        ...
      }
    """
    out = {}
    for cat_name, firms in teams.items():
        cb = team_builds.get(cat_name, {})
        out[cat_name] = []
        for co_name, count in firms:
            blds = cb.get(co_name, [])
            out[cat_name].append({
                "name":  co_name,
                "count": int(count),
                "buildings": [
                    {
                        "id":     bid,
                        "name":   bname or "",
                        "height": _safe_float(bht),
                        "year":   _safe_int(byr),
                    }
                    for (bid, bname, bht, byr) in blds
                ],
            })
    return out


def build_publish_payload(*, tier, geo_type, geo_name, geo_ids, min_height,
                          buildings, teams, team_builds, ghsl, boundary):
    """Assemble the final dict POSTed to /mds/v1/intelligence/publish."""
    if tier not in ("brief", "report"):
        raise ValueError(f"tier must be 'brief' or 'report', got {tier!r}")
    return {
        "tier":       tier,
        "geo_type":   geo_type,
        "geo_name":   geo_name,
        "geo_ids":    list(geo_ids),
        "min_height": int(min_height),
        "buildings":  buildings_to_dicts(buildings),
        "teams":      teams_to_dicts(teams, team_builds) if teams else {},
        "ghsl":       ghsl or {},
        "boundary":   boundary or [],
    }
