# CVU Intelligence App

Streamlit-based generator for CVU Intelligence Reports. Pulls building data
from the CTBUH MySQL and GHSL data from the Aiven Postgres, then publishes
draft posts to the WordPress site at `verticalurbanism.org` via the
`/mds/v1/intelligence/publish` REST route.

Pairs with the WordPress side in `CVU_Production/public/wp-content/themes/
mds-multiple-theme/intelligence/intelligence-admin.php` (the
`intelligence_report` CPT, ACF schema, and publish REST route).

## Architecture

```
[Staff browser]
     └─► [Streamlit app]
              ├─ MySQL (CTBUH) ─ pulls buildings + project teams
              ├─ Postgres (Aiven GHSL) ─ pulls population / emissions / GDP / HDI
              └─ POST /mds/v1/intelligence/publish ─► WordPress
                                                       └─ Creates a draft
                                                          intelligence_report
                                                          CPT post
```

The Streamlit app does NOT render the report itself. WordPress's
`single-intelligence_report.php` template renders from ACF data, so the
chart/table/map markup lives there.

## Local setup

```bash
git clone <this-repo> cvu-intelligence-app
cd cvu-intelligence-app
python -m venv .venv
source .venv/bin/activate
pip install -e .

cp .env.example .env
# edit .env and fill in passwords

streamlit run app.py
```

The app opens at `http://localhost:8501`.

## Authentication

Staff log in with their WordPress username and a WordPress Application
Password. Credentials are held in `st.session_state` for the browser
session only — never written to disk by the app.

Generate an app password at: `https://verticalurbanism.org/wp-admin/profile.php`
(scroll to "Application Passwords").

## Repository layout

```
cvu-intelligence-app/
├── app.py                              # Streamlit entry point
├── cvu_intelligence_core/              # Pure data + WP client (importable package)
│   ├── __init__.py
│   ├── constants.py
│   ├── helpers.py
│   ├── geo.py                          # List agglomerations/regions/countries/cities
│   ├── mysql_pull.py                   # CTBUH buildings + teams
│   ├── ghsl_pull.py                    # Aiven GHSL pull + aggregate
│   ├── boundary.py                     # geoBoundaries config for Leaflet
│   ├── payload.py                      # Tuples → WP publish payload
│   └── wp_client.py                    # POST /mds/v1/intelligence/publish
├── .env.example
├── requirements.txt
└── pyproject.toml
```

## Deployment (later)

Streamlit Community Cloud, Render, or Fly will work. The repo is
structured for `streamlit run app.py` from the root, which is what
Streamlit Cloud's autodetect uses.

## Related

- WordPress receiver: `CVU_Production/public/wp-content/themes/mds-multiple-theme/intelligence/intelligence-admin.php`
- Desktop tkinter sibling (kept in sync manually): `~/Desktop/cvu_intelligence_generator.py`
