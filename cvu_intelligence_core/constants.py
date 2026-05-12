"""Shared constants for the CVU Intelligence pipeline.

Mirrors the constants in cvu_intelligence_generator.py so both the
desktop tool and the Streamlit app draw from a single source of truth.
"""

STATUS_MAP = {
    "COM": "Complete",
    "UCT": "Topped Out",
    "STO": "Topped Out",
    "UC":  "Under Construction",
    "PRO": "Proposed",
    "REN": "Renovated",
    "UREN": "Renovated",
    "DEM": "Demolished",
    "UDEM": "Demolished",
    "CAN": "Cancelled",
    "NC":  "Never Completed",
    "OH":  "On Hold",
    "VIS": "Vision",
}

TEAM_CATEGORIES = {
    2: "Developer",
    3: "Architect",
    4: "Structural Engineer",
    7: "Contractor",
}

# Status -> colour mapping for map markers (mirrors intelligence.js).
MAP_STATUS_COLORS = {
    "Complete":           "#34C684",
    "Under Construction": "#516BFF",
    "Proposed":           "#FF9F18",
    "Topped Out":         "#54D9E7",
    "On Hold":            "#C63AD2",
    "Cancelled":          "#FA3F26",
    "Vision":             "#FFB84D",
    "Demolished":         "#A0A0A0",
    "Renovated":          "#50E3C2",
    "Never Completed":    "#FF6B9D",
}
