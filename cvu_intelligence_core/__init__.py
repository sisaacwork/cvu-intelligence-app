"""CVU Intelligence Core.

Pure data-fetching, transformation, and WordPress-publishing utilities
for the CVU Intelligence pipeline. Used by both the Streamlit app in
this repo and (eventually) the legacy tkinter desktop tool.

No UI code lives here. UI shells should import from this package and
provide their own logging/progress callbacks via the `log` argument.
"""

from .constants import STATUS_MAP, TEAM_CATEGORIES
from .helpers import get_function, get_status, fmt
from .geo import list_geographies
from .mysql_pull import pull_mysql_data
from .ghsl_pull import pull_ghsl_data
from .boundary import build_boundary_config
from .payload import buildings_to_dicts, teams_to_dicts, build_publish_payload
from .wp_client import WPClient

__all__ = [
    "STATUS_MAP",
    "TEAM_CATEGORIES",
    "get_function",
    "get_status",
    "fmt",
    "list_geographies",
    "pull_mysql_data",
    "pull_ghsl_data",
    "build_boundary_config",
    "buildings_to_dicts",
    "teams_to_dicts",
    "build_publish_payload",
    "WPClient",
]
