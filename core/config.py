"""
core/config.py — Small, static application configuration constants.

Kept deliberately minimal: this is NOT a settings/env-var framework, just
the few app-wide constants that both the Streamlit UI and the PySide6
desktop UI need to agree on (branding, cache TTLs) so they aren't
hard-coded differently in two places.
"""

APP_NAME = "TURF HR Pro"
APP_VERSION = "3.0.0"

# Brand color, referenced by components/theme.py (Streamlit) and
# desktop/theme.py (PySide6) so both UIs use the exact same TURF green.
BRAND_PRIMARY_COLOR = "#106454"

# Company name/tagline — single source of truth. components/theme.py
# re-exports these for the Streamlit UI; services/excel_export.py reads
# them from here directly (Phase 4A fix — see excel_export.py's
# docstring: importing from components.theme would transitively import
# Streamlit/Plotly via components/__init__.py, breaking the Step 17
# requirement that services be importable without Streamlit).
COMPANY_NAME = "TURF Landscape Co."
COMPANY_TAGLINE = "Create Scenic Views"

# Cache TTLs (seconds). Centralized here so payroll_service / dashboard
# don't disagree on freshness windows; explicit .clear() calls after
# writes are what actually guarantee freshness (see
# services/payroll_service.clear_payroll_cache()) — these TTLs are only a
# safety net.
PAYROLL_CACHE_TTL = 20
PROJECT_LIST_CACHE_TTL = 30
DASHBOARD_CACHE_TTL = 20
