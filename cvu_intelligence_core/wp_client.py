"""Thin HTTP client for WordPress integration.

Holds a base URL + (username, app password) credential pair and exposes
two methods: verify() to confirm auth works, and publish() to POST a
payload to /mds/v1/intelligence/publish.

Credentials are never written to disk by this class; the Streamlit app
keeps them in st.session_state for the duration of the browser session.
Task #12 will flesh out error handling, retries, and richer response
parsing — for now this is the contract Task #11's UI will call against.
"""

import requests
from urllib.parse import urljoin


class WPClientError(Exception):
    """Raised when a WordPress API call returns an error response."""


class WPClient:
    def __init__(self, base_url, username, app_password, timeout=60):
        if not base_url.endswith("/"):
            base_url = base_url + "/"
        self.base_url = base_url
        self.auth = (username, app_password)
        self.timeout = timeout
        self.session = requests.Session()

    def _url(self, path):
        # urljoin treats absolute paths as anchored to the host root, which is
        # what we want for "/wp-json/..." against "https://example.com/".
        if path.startswith("/"):
            path = path.lstrip("/")
        return urljoin(self.base_url, path)

    def verify(self):
        """Return the authenticated user's dict, or raise WPClientError."""
        r = self.session.get(
            self._url("wp-json/wp/v2/users/me"),
            auth=self.auth, timeout=self.timeout,
        )
        if r.status_code != 200:
            raise WPClientError(f"verify failed: {r.status_code} {r.text[:200]}")
        return r.json()

    def publish(self, payload):
        """POST payload to /mds/v1/intelligence/publish. Returns response JSON."""
        r = self.session.post(
            self._url("wp-json/mds/v1/intelligence/publish"),
            auth=self.auth, json=payload, timeout=self.timeout,
        )
        if r.status_code not in (200, 201):
            raise WPClientError(
                f"publish failed: {r.status_code} {r.text[:500]}"
            )
        return r.json()

    def list_reports(self, status="any", per_page=20):
        """Read the intelligence_report CPT collection for the history UI."""
        params = {"status": status, "per_page": per_page, "_fields": "id,date,status,title,link,slug"}
        r = self.session.get(
            self._url("wp-json/wp/v2/intelligence_report"),
            auth=self.auth, params=params, timeout=self.timeout,
        )
        if r.status_code != 200:
            raise WPClientError(f"list_reports failed: {r.status_code} {r.text[:200]}")
        return r.json()
