"""Build the geoBoundaries overlay config for the Leaflet map.

Returns a list of {iso3, adm_levels, filter_names} dicts that the
WordPress template's JavaScript turns into geoJSON overlay layers.
"""

# Common name overrides for countries whose pycountry name doesn't match
# the MySQL v2_countries name.
_ISO3_OVERRIDES = {
    "South Korea": "KOR",
    "North Korea": "PRK",
    "Russia":      "RUS",
    "Iran":        "IRN",
    "Syria":       "SYR",
    "Vietnam":     "VNM",
    "Taiwan":      "TWN",
    "Macau":       "MAC",
    "Hong Kong":   "HKG",
    "Ivory Coast": "CIV",
    "Brunei":      "BRN",
    "Bolivia":     "BOL",
    "Venezuela":   "VEN",
    "Tanzania":    "TZA",
    "Laos":        "LAO",
    "Moldova":     "MDA",
    "Palestine":   "PSE",
    "Czech Republic":        "CZE",
    "DR Congo":              "COD",
    "Republic of the Congo": "COG",
}


def _name_to_iso3(name, pycountry_mod):
    if name in _ISO3_OVERRIDES:
        return _ISO3_OVERRIDES[name]
    try:
        results = pycountry_mod.countries.search_fuzzy(name)
        return results[0].alpha_3 if results else None
    except LookupError:
        return None


def build_boundary_config(country_city_map, geo_type, geo_names, log=print):
    """ADM-level strategy:
        region        → ADM0 (whole countries)
        country       → ADM1 (states/provinces)
        city / agglom → ADM2 then ADM1, filtered by city names
    """
    try:
        import pycountry  # noqa: F401 — imported lazily so the module loads without it
    except ImportError:
        log("  Warning: pycountry not installed — skipping boundary overlay.")
        return []
    import pycountry  # actual reference after the guard

    configs = []
    for country_name, cities in country_city_map.items():
        iso3 = _name_to_iso3(country_name, pycountry)
        if not iso3:
            log(f"  Warning: No ISO3 code found for '{country_name}'")
            continue

        if geo_type == "region":
            configs.append({"iso3": iso3, "adm_levels": ["ADM0"], "filter_names": None})
        elif geo_type == "country":
            configs.append({"iso3": iso3, "adm_levels": ["ADM1", "ADM0"], "filter_names": None})
        elif geo_type in ("city", "agglomeration"):
            configs.append({
                "iso3":         iso3,
                "adm_levels":   ["ADM2", "ADM1"],
                "filter_names": cities,
            })

    log(f"  Boundary config: {len(configs)} entries for geo_type={geo_type}")
    return configs
