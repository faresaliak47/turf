"""
Master theme for TURF Landscape Co. — HR Pro
Brand design system derived from the TURF Landscape Co. logo
(indigo #635BFF + charcoal / neutral grays), modern enterprise look.
"""
import os
from core.config import BRAND_PRIMARY_COLOR, COMPANY_NAME, COMPANY_TAGLINE  # noqa: F401
# ^ Sourced from core.config (Phase 4A) so this Streamlit-only theme and
# desktop/theme.py (PySide6) can never drift apart on branding — same
# constants, two presentation layers. COMPANY_NAME/COMPANY_TAGLINE
# re-exported here unchanged so every existing `from components.theme
# import COMPANY_NAME` caller keeps working untouched.

_ASSETS_DIR        = os.path.join(os.path.dirname(__file__), "..", "assets")
LOGO_PATH          = os.path.join(_ASSETS_DIR, "turf_logo.jpg")              # white background — use on light surfaces (login)
LOGO_TRANSPARENT   = os.path.join(_ASSETS_DIR, "turf_logo_transparent.png")  # transparent — use on dark surfaces (sidebar)

# ── Single source of truth for every color in the app ────────────
# All UI (sidebar, buttons, cards, tables, forms, tabs, charts, metrics,
# exports) reads colors from this dict — no hardcoded hex anywhere else.
COLORS = {
    # ── Design tokens (single source of truth) ─────────────────────
    # Key names are unchanged so every existing page keeps working;
    # only the VALUES moved to the new indigo / charcoal identity.
    "primary":      "#635BFF",
    "primary_dark": "#4F47E6",   # hover / pressed shade of primary
    "primary_light":"#EFEEFF",   # very light primary tint (selected / unread bg)
    "secondary":    "#7B808A",
    "accent":       "#635BFF",   # no separate accent: primary is used sparingly

    "bg":           "#F5F7FA",
    "surface":      "#FFFFFF",

    "sidebar_bg":   "#25242B",
    "sidebar_item": "#635BFF",   # active nav item
    "sidebar_hover":"#302F37",

    "success":      "#22A06B",
    "warning":      "#F59E0B",
    "danger":       "#E5484D",
    "danger_dark":  "#CC3B40",   # hover / pressed shade of danger
    "info":         "#635BFF",

    "text":         "#17181C",
    "text_muted":   "#7B808A",
    "border":       "#E7E9EE",
    "shadow":       "rgba(23,24,28,0.06)",
}

MONTH_NAMES = [
    'يناير','فبراير','مارس','إبريل','مايو','يونيو',
    'يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر'
]


def inject_global_css():
    """Inject full global CSS — call once from app.py."""
    import streamlit as st
    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Cairo:wght@400;500;600&display=swap');

:root {{
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 16px;
    --radius-xl: 20px;
    --space-1: 4px;
    --space-2: 8px;
    --space-3: 12px;
    --space-4: 16px;
    --space-5: 20px;
    --space-6: 24px;
    --space-8: 32px;
    --shadow-sm: 0 1px 2px rgba(23,24,28,0.05), 0 1px 1px rgba(23,24,28,0.04);
    --shadow-md: 0 2px 8px rgba(23,24,28,0.05);
    --shadow-lg: 0 6px 20px rgba(23,24,28,0.07);
}}

/* Force our Arabic brand font everywhere EXCEPT Streamlit's own native
   Material-icon spans ([data-testid="stIconMaterial"]). Those spans'
   *text content* is literally the icon's ligature name (e.g.
   "keyboard_double_arrow_left") which only renders as an arrow glyph
   under Streamlit's own bundled icon font — forcing Cairo onto them
   like every other element used to make that raw name show up as
   plain giant text instead of an icon (this is exactly what caused
   the literal "double_arrow_left" text some users saw near the top of
   the sidebar). */
*:not([data-testid="stIconMaterial"]), *::before, *::after {{
    font-family: 'Inter', 'Cairo', 'Segoe UI', Arial, sans-serif !important;
    box-sizing: border-box;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}}

html, body, .stApp {{
    direction: rtl !important;
    background: {COLORS['bg']} !important;
    color: {COLORS['text']} !important;
    line-height: 1.6 !important;
    width: 100% !important;
    max-width: 100% !important;
    /* Do NOT set overflow-x:hidden here — it clips the flex layout and
       causes the sidebar to overlap instead of pushing the main content. */
}}

/* ── AppViewContainer: Streamlit renders this as position:absolute filling
   the viewport with display:flex flex-direction:row. We only need to ensure
   flex-wrap stays nowrap so sidebar + main never stack vertically. ── */
[data-testid="stAppViewContainer"] {{
    flex-wrap: nowrap !important;
    overflow: hidden !important;
}}

/* ── Main content area: must flex-grow to fill space left by the sidebar,
   and flex-shrink when the sidebar expands.  min-width:0 is required so the
   flex child can actually shrink below its content width. ── */
[data-testid="stAppViewContainer"] > [data-testid="stMain"],
.main {{
    flex: 1 1 0 !important;
    min-width: 0 !important;
    width: 100% !important;
    max-width: 100% !important;
    overflow-x: hidden !important;
}}

h1, h2, h3, h4, h5, h6 {{
    letter-spacing: -0.3px !important;
    font-weight: 600 !important;
}}
p, span, label, div {{
    letter-spacing: 0 !important;
}}
::selection {{
    background: {COLORS['primary']}33;
}}

/* ═══ HIDE STREAMLIT CHROME ═══ */
#MainMenu, footer, .stDeployButton {{visibility: hidden;}}
header[data-testid="stHeader"] {{background: transparent !important; min-height: 0; display:none;}}
[data-testid="stToolbar"] {{display:none;}}
[data-testid="stDecoration"] {{display:none;}}

/* ═══ SIDEBAR — custom hide/show toggle ═══
   The native Streamlit collapse arrow used to render as raw text like
   "double_arrow_left" on some browsers, so it's still hidden — but we
   now provide our own reliable button instead (see render_sidebar()
   in components/layout.py + .sidebar-toggle-btn / .sidebar-reopen-btn
   below), so the user always has a way to hide/show the menu. */
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapsedControl"],
[data-testid*="SidebarCollapse"],
[data-testid*="ollapsedControl"],
button[data-testid="baseButton-headerNoPadding"],
button[aria-label="Close sidebar"],
button[aria-label="Open sidebar"],
.st-emotion-cache-1cypcdb,
button[kind="header"] {{
    display: none !important;
}}

/* Our own hide-sidebar button, placed inline at the top of the sidebar */
.st-key-sidebar_hide_btn {{
    position: absolute !important;
    top: 12px !important;
    left: 10px !important;
    width: 30px !important;
    z-index: 999 !important;
}}
.st-key-sidebar_hide_btn button {{
    background: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    color: rgba(255,255,255,0.7) !important;
    width: 28px !important;
    height: 28px !important;
    padding: 0 !important;
    border-radius: 8px !important;
    font-size: 13px !important;
    min-height: 28px !important;
}}
.st-key-sidebar_hide_btn button:hover {{
    background: rgba(255,255,255,0.18) !important;
    color: #fff !important;
}}

/* Floating reopen button shown in the main area once the sidebar is hidden */
.st-key-sidebar_reopen_btn {{
    display: none !important;
    position: fixed !important;
    top: 18px !important;
    right: 18px !important;
    z-index: 9999 !important;
}}
.st-key-sidebar_reopen_btn button {{
    background: {COLORS['primary']} !important;
    color: #fff !important;
    border: none !important;
    border-radius: 10px !important;
    width: 42px !important;
    height: 42px !important;
    font-size: 17px !important;
    box-shadow: 0 2px 8px {COLORS['shadow']} !important;
}}
.st-key-sidebar_reopen_btn button:hover {{
    background: {COLORS['primary_light']} !important;
}}

/* ═══ SIDEBAR ═══
   Streamlit renders the sidebar as a Resizable flex child (re-resizable).
   We pin it to 265 px using flex-basis so it participates correctly in the
   row layout and the main content shifts accordingly. Setting position here
   would take the sidebar out of flow and cause it to overlay content. */
section[data-testid="stSidebar"] {{
    background: {COLORS['sidebar_bg']} !important;
    border-left: none !important;
    border-right: none !important;
    padding: 0 !important;
    /* Pin width via flex-basis so the browser's flex algorithm always
       allocates exactly 265 px to the sidebar column.
       flex-grow:0 / flex-shrink:0 prevent it from growing or shrinking. */
    flex: 0 0 265px !important;
    width: 265px !important;
    min-width: 265px !important;
    max-width: 265px !important;
    height: 100dvh !important;
    box-shadow: none !important;
    transition: flex-basis 0.25s ease, width 0.25s ease, min-width 0.25s ease !important;
    overflow: hidden !important;
    position: relative !important;
}}
/* Disable the drag-to-resize handle so the sidebar can't be dragged
   wider/narrower than our fixed 265px again. */
[data-testid="stSidebarResizeHandle"],
[data-testid*="ResizeHandle"],
[data-testid*="resizeHandle"] {{
    display: none !important;
    pointer-events: none !important;
}}
section[data-testid="stSidebar"] > div:first-child {{
    padding: 0 !important;
}}
section[data-testid="stSidebar"] * {{
    color: rgba(255,255,255,0.72) !important;
}}

/* ── Nav list ── */
section[data-testid="stSidebar"] .stRadio {{
    width: calc(100% + 32px) !important;
    margin-inline: -16px !important;
}}
section[data-testid="stSidebar"] .stRadio > div,
section[data-testid="stSidebar"] .stRadio :is([role="radiogroup"], [data-testid="stRadioGroup"]) {{
    width: 100% !important;
}}
section[data-testid="stSidebar"] .stRadio > div,
section[data-testid="stSidebar"] .stRadio :is([role="radiogroup"], [data-testid="stRadioGroup"]) {{
    gap: 2px !important;
    flex-direction: column !important;
    align-items: stretch !important;
}}
section[data-testid="stSidebar"] .stRadio :is([role="radiogroup"], [data-testid="stRadioGroup"]) {{
    display: flex !important;
    height: auto !important;
    min-height: 0 !important;
    justify-content: flex-start !important;
    overflow: visible !important;
}}
/* No dead space under the last nav item: Streamlit reserves a big
   bottom padding / min-height for the sidebar's user content. */
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"],
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{
    padding-top: 0 !important;
    padding-bottom: 16px !important;
}}
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{
    overflow-y: auto !important;
}}
/* Keep long project names inside the same sidebar column as the delete control. */
section[data-testid="stSidebar"] [data-testid="stSelectbox"] {{
    width: 100% !important;
    min-width: 0 !important;
    max-width: 100% !important;
    overflow: hidden !important;
}}
section[data-testid="stSidebar"] [data-testid="stSelectbox"] > div,
section[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] {{
    width: 100% !important;
    min-width: 0 !important;
    max-width: 100% !important;
    box-sizing: border-box !important;
}}
section[data-testid="stSidebar"] [data-testid="stSelectbox"] [class*="singleValue"] {{
    min-width: 0 !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
}}
section[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] {{
    direction: rtl !important;
    text-align: right !important;
}}
/* The sidebar's general white text rule is intentionally scoped to the
   dark navigation surface. The project picker itself is a light control,
   so give its selected value and search input a readable dark color. */
section[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] * {{
    color: {COLORS['text']} !important;
    -webkit-text-fill-color: {COLORS['text']} !important;
}}
/* Hide the radio group's own widget label ("القائمة الرئيسية") — target
   it explicitly by Streamlit's stable testid so it can never be
   re-shown by the broader option-styling rule below, regardless of
   CSS declaration order. */
section[data-testid="stSidebar"] .stRadio > label,
section[data-testid="stSidebar"] .stRadio [data-testid="stWidgetLabel"] {{
    display: none !important;
}}
/* Style only the actual selectable options (inside the radio group),
   never the widget's own label above — scoping to stRadioGroup keeps
   this from re-showing the hidden label rule above. */
section[data-testid="stSidebar"] .stRadio :is([role="radiogroup"], [data-testid="stRadioGroup"]) label {{
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    box-sizing: border-box !important;
    width: auto !important;
    min-height: 34px !important;
    padding: 0 20px !important;
    margin: 5px 12px !important;
    align-self: flex-start !important;
    border-radius: 8px !important;
    cursor: pointer !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    color: rgba(255,255,255,0.72) !important;
    border-right: none !important;
    transition: background 0.18s ease, color 0.18s ease, box-shadow 0.18s ease,
                border-color 0.18s ease, transform 0.18s ease !important;
    background: transparent !important;
    gap: 10px !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
}}
section[data-testid="stSidebar"] .stRadio :is([role="radiogroup"], [data-testid="stRadioGroup"]) label:hover {{
    background: {COLORS['sidebar_hover']} !important;
    color: #fff !important;
}}
@media (max-height: 700px) {{
    section[data-testid="stSidebar"] .stRadio :is([role="radiogroup"], [data-testid="stRadioGroup"]) {{
        height: auto !important;
    }}
    section[data-testid="stSidebar"] .stRadio :is([role="radiogroup"], [data-testid="stRadioGroup"]) label {{
        min-height: 32px !important;
        margin-top: 3px !important;
        margin-bottom: 3px !important;
    }}
}}
section[data-testid="stSidebar"] .stRadio [data-testid="stMarkdownContainer"] {{
    flex: 0 0 auto !important;
    width: auto !important;
    max-width: none !important;
    white-space: nowrap !important;
}}
section[data-testid="stSidebar"] .stRadio [data-testid="stMarkdownContainer"] p {{
    font-size: 14px !important;
    color: inherit !important;
    margin: 0 !important;
    width: auto !important;
    text-align: right !important;
    white-space: nowrap !important;
}}
/* Hide radio circle bullets entirely — multiple redundant selectors
   because Streamlit/BaseWeb have changed this markup more than once.
   `role="radio"` and the bare `input[type=radio]` are the most stable
   anchors; the rest are extra safety nets for older/newer versions. */
section[data-testid="stSidebar"] .stRadio input[type="radio"] {{
    display: none !important;
}}
section[data-testid="stSidebar"] .stRadio [role="radio"] {{
    display: none !important;
}}
section[data-testid="stSidebar"] .stRadio label svg {{
    display: none !important;
}}
section[data-testid="stSidebar"] .stRadio div[data-baseweb="radio"] {{
    display: none !important;
}}
/* Highlight the currently selected nav item (modern browsers) */
section[data-testid="stSidebar"] .stRadio label:has(input:checked) {{
    background: {COLORS['primary']} !important;
    color: #fff !important;
    border-radius: 9px !important;
    box-shadow: 0 3px 10px rgba(99, 91, 255, 0.22) !important;
}}

/* ═══ RESPONSIVE — collapse sidebar on narrow screens ═══ */
@media (max-width: 768px) {{
    /* The desktop sidebar is collapsed on phones. Keep a floating menu
       control available so users can open the off-canvas navigation. */
    .st-key-sidebar_reopen_btn {{
        display: block !important;
        top: 10px !important;
        right: 10px !important;
        z-index: 10002 !important;
    }}

    section[data-testid="stSidebar"] {{
        flex: 0 0 0px !important;
        width: 0 !important;
        min-width: 0 !important;
        overflow: hidden !important;
        box-shadow: none !important;
    }}
    .main .block-container,
    [data-testid="stMainBlockContainer"] {{
        padding: 1rem 0.9rem 1.75rem !important;
        max-width: 100% !important;
        width: 100% !important;
    }}

    /* Topbar / page-header: stack title and the date/avatar cluster so
       neither gets squeezed on narrow screens */
    [data-testid="stMarkdownContainer"] div[style*="justify-content:space-between"] {{
        flex-wrap: wrap !important;
        row-gap: 10px !important;
    }}

    /* ── Stack columns vertically on mobile (Dashboard KPI cards,
       Attendance/Overtime entry inputs & buttons) ──────────────── */
    [data-testid="stHorizontalBlock"] {{
        flex-direction: column !important;
    }}
    [data-testid="stHorizontalBlock"] > [data-testid="column"] {{
        width: 100% !important;
        flex: 1 1 100% !important;
        min-width: 100% !important;
    }}

    /* Full-width inputs and stacked, full-width buttons on mobile */
    .stTextInput, .stNumberInput, .stTextArea, .stSelectbox,
    .stDateInput, .stMultiSelect, .stButton, [data-testid="stForm"] {{
        width: 100% !important;
    }}
    .stButton > button {{
        width: 100% !important;
    }}
    .kpi-hover {{
        margin: 7px 0 !important;
    }}
    [data-testid="stForm"] {{
        padding: 20px 18px 16px !important;
    }}

    /* ── Tables / Reports / Matrix: keep the desktop table layout
       intact and only allow horizontal scrolling on mobile — do
       NOT shrink or restructure the table itself. ───────────────── */
    .stDataFrame {{
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
        max-width: 100% !important;
    }}
    .stDataFrame > div {{
        overflow-x: auto !important;
    }}
    .stDataFrame table {{
        width: max-content !important;
        min-width: 100% !important;
    }}

    /* This grid (bulk-overtime employee selection) is a real row-aligned
       table built from st.columns, not a stacked input form — keep its
       desktop row layout and just allow horizontal scroll on mobile. */
    .st-key-bulk_ot_emp_table {{
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
    }}
    .st-key-bulk_ot_emp_table [data-testid="stHorizontalBlock"] {{
        flex-direction: row !important;
        min-width: 560px !important;
    }}
    .st-key-bulk_ot_emp_table [data-testid="stHorizontalBlock"] > [data-testid="column"] {{
        width: auto !important;
        min-width: unset !important;
        flex: initial !important;
    }}
}}

/* ═══ MAIN CONTENT ═══ */
.main .block-container {{
    padding: 0.6rem 1.5rem 1rem !important;
    max-width: 100% !important;
    width: 100% !important;
    background: {COLORS['bg']};
}}
/* Streamlit newer versions use stMainBlockContainer */
[data-testid="stMainBlockContainer"] {{
    max-width: 100% !important;
    width: 100% !important;
    padding: 0.6rem 1.5rem 1rem !important;
}}
/* Vertical rhythm — tighter on desktop so more dashboard content fits
   above the fold without losing readability */
[data-testid="stMain"] [data-testid="stVerticalBlock"] {{
    gap: 0.85rem !important;
}}
[data-testid="stVerticalBlock"] > div {{
    margin-bottom: 0;
}}
/* Column padding — gutters come from the flex gap, so cards line up
   with the top bar's edges */
[data-testid="column"] {{ padding: 0 !important; }}
[data-testid="stHorizontalBlock"] {{
    gap: 14px;
    align-items: stretch !important;
    margin-bottom: 8px !important;
}}
/* Desktop-first: on wide screens, give the dashboard/report grids a
   touch more breathing room between major row blocks while keeping
   everything inside one continuous, full-width canvas. */
@media (min-width: 1400px) {{
    .main .block-container,
    [data-testid="stMainBlockContainer"] {{
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }}
}}

/* ═══ BUTTONS ═══ */
.stButton > button, [data-testid="stFormSubmitButton"] > button,
[data-testid="stDownloadButton"] > button {{
    border-radius: 8px !important;
    font-weight: 500 !important;
    font-size: 14px !important;
    min-height: 40px !important;
    padding: 0 16px !important;
    transition: background-color 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease !important;
    letter-spacing: 0 !important;
    box-shadow: none !important;
}}
/* Primary */
.stButton > button[kind="primary"],
[data-testid="stFormSubmitButton"] > button[kind="primary"] {{
    background: {COLORS['primary']} !important;
    color: #fff !important;
    border: 1px solid {COLORS['primary']} !important;
}}
.stButton > button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] > button[kind="primary"]:hover {{
    background: {COLORS['primary_dark']} !important;
    border-color: {COLORS['primary_dark']} !important;
}}
.stButton > button[kind="primary"]:active,
[data-testid="stFormSubmitButton"] > button[kind="primary"]:active {{
    background: {COLORS['primary_dark']} !important;
    box-shadow: inset 0 1px 2px rgba(0,0,0,0.15) !important;
}}
/* Secondary */
.stButton > button[kind="secondary"],
[data-testid="stFormSubmitButton"] > button[kind="secondary"] {{
    background: {COLORS['surface']} !important;
    color: {COLORS['text']} !important;
    border: 1px solid {COLORS['border']} !important;
}}
.stButton > button[kind="secondary"]:hover,
[data-testid="stFormSubmitButton"] > button[kind="secondary"]:hover {{
    background: {COLORS['bg']} !important;
    border-color: {COLORS['text_muted']} !important;
}}
.stButton > button[kind="secondary"]:active {{
    background: {COLORS['border']} !important;
}}
/* Danger variant — destructive buttons. Hook: give the button a key that
   contains "_del_", "delete" or starts with "del_" / "danger" (no page logic changes). */
[class*="_del_"] .stButton > button,
[class*="delete"] .stButton > button,
[class*="st-key-del_"] .stButton > button,
[class*="st-key-danger"] .stButton > button {{
    background: {COLORS['danger']} !important;
    color: #fff !important;
    border: 1px solid {COLORS['danger']} !important;
}}
[class*="_del_"] .stButton > button:hover,
[class*="delete"] .stButton > button:hover,
[class*="st-key-del_"] .stButton > button:hover,
[class*="st-key-danger"] .stButton > button:hover {{
    background: {COLORS['danger_dark']} !important;
    border-color: {COLORS['danger_dark']} !important;
}}
[class*="_del_"] .stButton > button:focus-visible,
[class*="delete"] .stButton > button:focus-visible,
[class*="st-key-del_"] .stButton > button:focus-visible,
[class*="st-key-danger"] .stButton > button:focus-visible {{
    box-shadow: 0 0 0 3px rgba(229,72,77,0.25) !important;
}}
/* Focus + disabled (all buttons) */
.stButton > button:focus-visible,
[data-testid="stFormSubmitButton"] > button:focus-visible {{
    outline: none !important;
    box-shadow: 0 0 0 3px rgba(99,91,255,0.25) !important;
}}
.stButton > button:disabled,
[data-testid="stFormSubmitButton"] > button:disabled {{
    opacity: 0.5 !important;
    cursor: not-allowed !important;
}}

/* ═══ DIALOGS (st.dialog) ═══ */
div[data-testid="stDialog"] div[role="dialog"] {{
    background: {COLORS['surface']} !important;
    border: 1px solid {COLORS['border']} !important;
    border-radius: var(--radius-lg) !important;
    box-shadow: var(--shadow-lg) !important;
}}
div[data-testid="stDialog"] div[role="dialog"] h1,
div[data-testid="stDialog"] div[role="dialog"] h2,
div[data-testid="stDialog"] div[role="dialog"] h3 {{
    font-size: 17px !important;
    font-weight: 600 !important;
    color: {COLORS['text']} !important;
    letter-spacing: 0 !important;
}}
div[data-testid="stDialog"] > div {{
    background: rgba(23,24,28,0.45) !important;
}}

/* ═══ INPUTS ═══ */
.stTextInput input, .stNumberInput input, .stTextArea textarea,
.stSelectbox select, [data-baseweb="input"] input {{
    border-radius: 8px !important;
    border: 1px solid {COLORS['border']} !important;
    padding: 8px 12px !important;
    background: {COLORS['surface']} !important;
    color: {COLORS['text']} !important;
    -webkit-text-fill-color: {COLORS['text']} !important;
    font-size: 14px !important;
    min-height: 40px !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}}
.stTextInput input::placeholder, .stTextArea textarea::placeholder {{
    color: {COLORS['text_muted']} !important;
    -webkit-text-fill-color: {COLORS['text_muted']} !important;
    opacity: 0.8 !important;
}}
.stTextInput input:hover, .stNumberInput input:hover, .stTextArea textarea:hover {{
    border-color: {COLORS['text_muted']} !important;
}}
.stTextInput input:focus, .stNumberInput input:focus,
.stTextArea textarea:focus {{
    border-color: {COLORS['primary']} !important;
    box-shadow: 0 0 0 3px rgba(99,91,255,0.15) !important;
    outline: none !important;
}}
.stTextInput input:disabled, .stNumberInput input:disabled, .stTextArea textarea:disabled {{
    background: {COLORS['bg']} !important;
    color: {COLORS['text_muted']} !important;
    -webkit-text-fill-color: {COLORS['text_muted']} !important;
    cursor: not-allowed !important;
}}
.stTextInput label, .stNumberInput label, .stTextArea label,
.stSelectbox label, .stDateInput label, .stMultiSelect label {{
    font-weight: 500 !important;
    font-size: 13px !important;
    color: {COLORS['text']} !important;
    margin-bottom: 6px !important;
}}
/* Helper / caption text under inputs */
.stTextInput [data-testid="stWidgetLabelHelp"],
[data-testid="stCaptionContainer"] {{
    color: {COLORS['text_muted']} !important;
}}
/* Consistent breathing room above every labelled widget */
.stTextInput, .stNumberInput, .stTextArea, .stSelectbox,
.stDateInput, .stMultiSelect, .stCheckbox, .stSlider,
.stRadio, .stTimeInput {{
    margin-bottom: 10px !important;
}}

/* ═══ SELECT / DROPDOWN — STRUCTURE-AGNOSTIC VISIBILITY FIX ═══
   The previous version of this fix guessed at BaseWeb's internal DOM
   (specific nesting depth, class names containing "singleValue" etc.).
   That's fragile: in a production build those class names are usually
   minified/hashed with no readable substring left, and the exact
   nesting can differ by Streamlit version — which is exactly why
   the selected employee name could end up not just unreadable, but
   completely blank, with no text visible in the box at all.

   This version makes no assumption about internal structure:
   - [data-baseweb="select"] itself (the one attribute Streamlit always
     sets, regardless of version) gets ALL the visual chrome — border,
     background, sizing. This is the only element styled with an
     opaque background.
   - Literally everything nested inside it — input, span, div,
     whatever tag/class BaseWeb happens to use — is forced to a
     transparent background and the correct, visible text color. That
     guarantees no inner wrapper can ever paint an opaque layer over
     the real text, and no text node can end up invisible because we
     missed its specific class name.                                  */

[data-baseweb="select"] {{
    border-radius: 8px !important;
    border: 1px solid {COLORS['border']} !important;
    background: {COLORS['surface']} !important;
    min-height: 40px !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}}
[data-baseweb="select"]:hover {{
    border-color: {COLORS['text_muted']} !important;
}}
[data-baseweb="select"]:focus-within {{
    border-color: {COLORS['primary']} !important;
    box-shadow: 0 0 0 3px rgba(99,91,255,0.15) !important;
}}

/* Every descendant: no opaque backgrounds, no invisible text, no
   dimmed opacity — whatever tag/class it turns out to be. */
[data-baseweb="select"] * {{
    background: transparent !important;
    color: {COLORS['text']} !important;
    -webkit-text-fill-color: {COLORS['text']} !important;
    opacity: 1 !important;
    border: none !important;
}}

/* Placeholder text (no employee chosen yet) gets the muted color —
   applied after the wildcard above so it wins for this specific case. */
[data-baseweb="select"] div[class*="placeholder"] {{
    color: {COLORS['text_muted']} !important;
    -webkit-text-fill-color: {COLORS['text_muted']} !important;
}}

/* The real type-to-search <input> still needs a working caret and
   needs its OWN raw text (the in-progress search query) to never
   visually double up with the selected-value text next to it — paint
   its glyphs via text-shadow instead of color, since text-shadow
   can't be hijacked by `-webkit-text-fill-color` games on any browser. */
[data-baseweb="select"] input {{
    color: transparent !important;
    -webkit-text-fill-color: transparent !important;
    text-shadow: 0 0 0 {COLORS['text']} !important;
    caret-color: {COLORS['text']} !important;
}}

/* ── Multi-select tags (selected employee chips) ── */
[data-baseweb="tag"] {{
    background: {COLORS['primary']}18 !important;
    border: 1px solid {COLORS['primary']}44 !important;
    border-radius: 6px !important;
}}
[data-baseweb="tag"] span,
[data-baseweb="tag"] [data-baseweb="tag-text"] {{
    color: {COLORS['primary_dark']} !important;
    font-weight: 600 !important;
    font-size: 13px !important;
}}
[data-baseweb="tag"] button,
[data-baseweb="tag"] [data-baseweb="icon"] {{
    color: {COLORS['primary']} !important;
}}
[data-baseweb="tag"]:hover {{
    background: {COLORS['primary']}28 !important;
}}

/* ── Dropdown popover menu ── */
[data-baseweb="popover"],
[data-baseweb="menu"],
[data-baseweb="menu"] ul,
ul[data-baseweb="menu"] {{
    background: #ffffff !important;
    border: 1px solid {COLORS['border']} !important;
    border-radius: 10px !important;
    box-shadow: 0 8px 28px {COLORS['shadow']} !important;
    padding: 4px !important;
}}

/* ── Every option row inside the popover ── */
[data-baseweb="menu"] li,
[data-baseweb="menu"] [role="option"],
[role="listbox"] [role="option"],
[role="option"] {{
    color: {COLORS['text']} !important;
    background: #ffffff !important;
    border-radius: 7px !important;
    padding: 9px 14px !important;
    font-size: 13.5px !important;
    font-weight: 500 !important;
    transition: background 0.15s, color 0.15s !important;
}}

/* ── Option hover ── */
[data-baseweb="menu"] li:hover,
[data-baseweb="menu"] [role="option"]:hover,
[role="listbox"] [role="option"]:hover,
[role="option"]:hover {{
    background: {COLORS['primary']}12 !important;
    color: {COLORS['primary_dark']} !important;
}}

/* ── Option focused (keyboard navigation) ── */
[data-baseweb="menu"] li:focus,
[data-baseweb="menu"] [role="option"]:focus,
[role="option"]:focus,
[data-baseweb="menu"] li[data-highlighted],
[role="option"][data-highlighted] {{
    background: {COLORS['primary']}18 !important;
    color: {COLORS['primary_dark']} !important;
    outline: none !important;
}}

/* ── Currently selected option (the checkmarked one) ── */
[aria-selected="true"][role="option"],
[data-baseweb="menu"] li[aria-selected="true"],
[role="listbox"] [aria-selected="true"] {{
    background: {COLORS['primary']}16 !important;
    color: {COLORS['primary']} !important;
    font-weight: 700 !important;
}}
[aria-selected="true"][role="option"]:hover,
[data-baseweb="menu"] li[aria-selected="true"]:hover {{
    background: {COLORS['primary']}24 !important;
    color: {COLORS['primary_dark']} !important;
}}

/* ── Any text node inside an option (Arabic names) ── */
[role="option"] span,
[role="option"] p,
[role="option"] div,
[data-baseweb="menu"] li span,
[data-baseweb="menu"] li div,
[data-baseweb="menu"] li p {{
    color: inherit !important;
}}

/* ── Dropdown chevron / indicator icons ── */
[data-baseweb="select"] [data-baseweb="icon"],
[data-baseweb="select"] svg {{
    color: {COLORS['text_muted']} !important;
    fill:  {COLORS['text_muted']} !important;
}}

/* ── Date input calendar picker ── */
.stDateInput input {{
    border-radius: 8px !important;
    border: 1px solid {COLORS['border']} !important;
    background: #ffffff !important;
    color: {COLORS['text']} !important;
}}

/* ── Dark-mode guard: force white background + dark text on all
   select controls so system dark-mode can't flip them ── */
@media (prefers-color-scheme: dark) {{
    [data-baseweb="select"] > div,
    [data-baseweb="select"] > div > div,
    [data-baseweb="select"] > div > div > div {{
        background: #ffffff !important;
        color: {COLORS['text']} !important;
    }}
    [data-baseweb="popover"],
    [data-baseweb="menu"],
    [data-baseweb="menu"] ul {{
        background: #ffffff !important;
    }}
    [data-baseweb="menu"] li,
    [role="option"] {{
        background: #ffffff !important;
        color: {COLORS['text']} !important;
    }}
    [data-baseweb="tag"] span,
    [data-baseweb="tag"] [data-baseweb="tag-text"] {{
        color: {COLORS['primary_dark']} !important;
    }}
}}

/* Checkbox / radio accent */
/* Checkbox / radio accent */
input[type="checkbox"], input[type="radio"] {{
    accent-color: {COLORS['primary']} !important;
}}
[data-testid="stCheckbox"] label p {{
    font-size: 14px !important;
}}

/* ═══ TABS ═══ */
.stTabs [data-baseweb="tab-list"] {{
    background: transparent !important;
    padding: 0 !important;
    gap: 4px !important;
    border-bottom: 1px solid {COLORS['border']} !important;
    box-shadow: none !important;
    margin-bottom: 20px !important;
}}
.stTabs [data-baseweb="tab"] {{
    border-radius: 8px 8px 0 0 !important;
    font-weight: 500 !important;
    font-size: 14px !important;
    padding: 10px 16px !important;
    color: {COLORS['text_muted']} !important;
    background: transparent !important;
    border: none !important;
    transition: color 0.15s, background-color 0.15s !important;
}}
.stTabs [data-baseweb="tab"]:hover {{
    background: {COLORS['bg']} !important;
    color: {COLORS['text']} !important;
}}
.stTabs [aria-selected="true"] {{
    background: transparent !important;
    color: {COLORS['primary']} !important;
    box-shadow: none !important;
}}
.stTabs [aria-selected="true"]:hover {{
    color: {COLORS['primary']} !important;
}}
.stTabs [data-baseweb="tab-highlight"] {{
    background-color: {COLORS['primary']} !important;
    height: 2px !important;
}}
.stTabs [data-baseweb="tab-border"] {{
    display: none !important;
}}
.stTabs [data-baseweb="tab-panel"] {{
    padding: 0 !important;
}}

/* ═══ DATAFRAME / TABLES ═══ */
.stDataFrame {{
    border-radius: var(--radius-md) !important;
    overflow: hidden !important;
    box-shadow: var(--shadow-sm) !important;
    border: 1px solid {COLORS['border']} !important;
    margin-top: 6px;
}}
.stDataFrame table {{
    font-size: 13.5px !important;
    font-variant-numeric: tabular-nums;
}}
.stDataFrame thead tr th {{
    background: {COLORS['bg']} !important;
    font-weight: 500 !important;
    color: {COLORS['text_muted']} !important;
    font-size: 12.5px !important;
    padding-top: 12px !important;
    padding-bottom: 12px !important;
    border-bottom: 1px solid {COLORS['border']} !important;
    position: sticky !important;
    top: 0 !important;
    z-index: 2 !important;
}}
.stDataFrame tbody tr td {{
    padding-top: 12px !important;
    padding-bottom: 12px !important;
    border-bottom: 1px solid {COLORS['border']} !important;
    color: {COLORS['text']} !important;
}}
.stDataFrame tbody tr:last-child td {{
    border-bottom: none !important;
}}
.stDataFrame tbody tr:hover {{
    background: {COLORS['primary_light']} !important;
}}

/* ═══ METRICS ═══ */
[data-testid="metric-container"] {{
    background: {COLORS['surface']} !important;
    border-radius: var(--radius-md) !important;
    padding: 10px 16px !important;
    border: 1px solid {COLORS['border']} !important;
    box-shadow: var(--shadow-sm) !important;
}}
[data-testid="metric-container"] [data-testid="stMetricLabel"] {{
    font-size: 13px !important;
    color: {COLORS['text_muted']} !important;
    font-weight: 500 !important;
}}
[data-testid="metric-container"] [data-testid="stMetricValue"] {{
    font-size: 24px !important;
    font-weight: 600 !important;
    color: {COLORS['text']} !important;
    font-variant-numeric: tabular-nums;
    margin-top: 4px !important;
}}
[data-testid="stMetricDelta"] svg {{
    display: inline !important;
}}

/* ═══ ALERTS ═══ */
.stAlert {{
    border-radius: 8px !important;
    border: none !important;
    font-size: 14px !important;
}}

/* ═══ FORMS ═══ */
[data-testid="stForm"] {{
    background: {COLORS['surface']} !important;
    border-radius: var(--radius-lg) !important;
    padding: 16px !important;
    border: 1px solid {COLORS['border']} !important;
    box-shadow: var(--shadow-sm) !important;
}}
[data-testid="stForm"] [data-testid="stVerticalBlock"] > div {{
    margin-bottom: 0;
}}
[data-testid="stForm"] [data-testid="stHorizontalBlock"] {{
    gap: 12px;
    margin-bottom: 0;
}}
[data-testid="stForm"] [data-testid="stFormSubmitButton"] {{
    margin-top: 4px !important;
}}
/* Calculated read-only metrics inside a form read as derived values */
[data-testid="stForm"] [data-testid="metric-container"] {{
    background: {COLORS['bg']} !important;
    box-shadow: none !important;
    border: 1px solid {COLORS['border']} !important;
}}

/* ═══ EXPANDER ═══ */
.streamlit-expanderHeader {{
    background: {COLORS['surface']} !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    border: 1px solid {COLORS['border']} !important;
    transition: background-color 0.15s, border-color 0.15s !important;
}}
.streamlit-expanderHeader:hover {{
    border-color: {COLORS['text_muted']} !important;
    background: {COLORS['bg']} !important;
}}

/* ═══ ANIMATIONS ═══ */
@keyframes fadeInUp {{
    from {{ opacity: 0; transform: translateY(20px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
}}
@keyframes fadeIn {{
    from {{ opacity: 0; }}
    to   {{ opacity: 1; }}
}}
@keyframes slideInRight {{
    from {{ opacity: 0; transform: translateX(20px); }}
    to   {{ opacity: 1; transform: translateX(0); }}
}}
@keyframes pulse-glow {{
    0%, 100% {{ box-shadow: 0 0 0 0 rgba(99,91,255,0.25); }}
    50%       {{ box-shadow: 0 0 0 6px rgba(99,91,255,0); }}
}}

.fade-in-up  {{ animation: fadeInUp  0.45s ease both; }}
.fade-in     {{ animation: fadeIn    0.3s ease both; }}
.slide-in    {{ animation: slideInRight 0.4s ease both; }}

/* ═══ SCROLLBAR ═══ */
::-webkit-scrollbar {{ width: 6px; height: 6px; }}
::-webkit-scrollbar-track {{ background: {COLORS['bg']}; border-radius: 3px; }}
::-webkit-scrollbar-thumb {{
    background: {COLORS['primary']}55;
    border-radius: 3px;
}}
::-webkit-scrollbar-thumb:hover {{ background: {COLORS['primary']}; }}

/* ═══ FILE UPLOADER ═══ */
[data-testid="stFileUploaderDropzone"] {{
    border-radius: 12px !important;
    border: 2px dashed {COLORS['primary']}55 !important;
    background: {COLORS['primary']}05 !important;
    transition: all 0.2s !important;
}}
[data-testid="stFileUploaderDropzone"]:hover {{
    border-color: {COLORS['primary']} !important;
    background: {COLORS['primary']}10 !important;
}}

/* ═══ DATE INPUT ═══ */
.stDateInput input {{
    border-radius: 8px !important;
    border: 1px solid {COLORS['border']} !important;
}}

/* ═══ SPINNER ═══ */
.stSpinner > div {{
    border-top-color: {COLORS['primary']} !important;
}}

/* ═══ DOWNLOAD BUTTON ═══ */
[data-testid="stDownloadButton"] > button {{
    background: {COLORS['success']} !important;
    color: #fff !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
}}

/* ═══ PROGRESS BAR ═══ */
.stProgress > div > div > div {{
    background: {COLORS['primary']} !important;
    border-radius: 4px !important;
}}

/* ═══ SIDEBAR DIVIDER ═══ */
.sidebar-divider {{
    height: 1px;
    background: rgba(255,255,255,0.08);
    margin: 8px 16px;
}}

/* ═══ KPI CARD HOVER ═══ */
.kpi-hover:hover {{
    transform: none !important;
    box-shadow: var(--shadow-lg) !important;
}}

/* Card hover effect */
.emp-card:hover {{
    transform: none !important;
    box-shadow: 0 8px 28px {COLORS['shadow']} !important;
    border-color: {COLORS['primary']}44 !important;
}}

/* Section separator */
.section-sep {{
    height: 1px;
    background: {COLORS['border']};
    margin: 20px 0;
}}

/* ═══ POLISH LAYER — RTL / bidi / cards / sidebar / popovers ═══ */

/* Every markdown block reads RTL and is right-aligned (fixes text hugging the left edge) */
[data-testid="stMarkdownContainer"],
[data-testid="stCaptionContainer"] {{ direction: rtl; text-align: right; }}

/* Latin/numeric fragments (names, e-mails, dates, "Co.") keep their own order inside Arabic text */
bdi, .ltr {{ unicode-bidi: isolate; }}
.ltr {{ direction: ltr; display: inline-block; }}

/* Breathing room between the big blocks of a page */
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] {{ gap: 0.9rem !important; }}
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > div {{
    margin-bottom: 8px !important;
}}

/* Card = st.container(key="card_...") : header + body inside ONE white card */
[data-testid="stMain"] [class*="st-key-card_"][data-testid="stVerticalBlock"] {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-sm);
    padding: 0 0 14px !important;
    gap: 0.5rem !important;
    overflow: hidden;
}}
[class*="st-key-card_"] > div:not(:first-child) {{ padding: 0 16px; }}

/* Sidebar: "delete project" is a destructive action, not a nav item */
section[data-testid="stSidebar"] [data-testid="stExpander"] {{
    margin: 10px 16px 6px;
    border: 1px solid rgba(229,72,77,0.35) !important;
    border-radius: 8px !important;
    background: rgba(229,72,77,0.08) !important;
}}
section[data-testid="stSidebar"] [data-testid="stExpander"] details {{
    border: none !important;
    background: transparent !important;
}}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary,
section[data-testid="stSidebar"] [data-testid="stExpander"] summary * {{
    color: #FF8A8E !important;
    font-size: 13px !important;
    font-weight: 500 !important;
}}
/* RTL: a collapsed section's arrow should point left */
section[data-testid="stSidebar"] [data-testid="stExpander"] details:not([open]) summary svg,
section[data-testid="stSidebar"] [data-testid="stExpander"] details:not([open]) summary [data-testid="stIconMaterial"] {{
    transform: scaleX(-1);
}}

/* Plotly inside an RTL page mis-measures/clips axis text (names cut to 1 letter, tick labels
   cut). Keep the chart's own box LTR; Arabic glyphs still shape/read correctly. */
[data-testid="stPlotlyChart"], .js-plotly-plot, .js-plotly-plot .plotly {{ direction: ltr !important; }}

/* Popovers (user menu / notifications): RTL, tighter spacing, no dead space */
[data-testid="stPopoverBody"] {{ direction: rtl; text-align: right; }}
[data-testid="stPopoverBody"] [data-testid="stVerticalBlock"] {{ gap: 0.4rem !important; }}
[data-testid="stPopoverBody"] hr {{ margin: 6px 0 !important; }}
</style>
""", unsafe_allow_html=True)
