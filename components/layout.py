"""Layout helpers — sidebar, topbar, wrappers."""
import streamlit as st
import base64
from datetime import date
from components.theme import COLORS, COMPANY_NAME, COMPANY_TAGLINE, LOGO_TRANSPARENT
from components.icons import render_icon, _ICONS
from urllib.parse import quote

# Grouped for the sidebar's visual section headers (see the nth-of-type
# CSS in this module's render_sidebar()) — NAV_ITEMS below is the same
# list flattened, so nothing that reads NAV_ITEMS/NAV_LABELS positionally
# elsewhere (app.py's routing keys off page *key*, not position — see its
# page_allowed()/_selected_key logic) needs to know about the grouping.
NAV_GROUPS = [
    ("الرئيسية", [
        ("📊", "لوحة التحكم",           "dashboard"),
    ]),
    ("الموارد البشرية", [
        ("👥", "الموظفون",               "employees"),
        ("📅", "الحضور والغياب",        "attendance"),
        ("⏱",  "الأوفر تايم",           "overtime"),
        ("⏱⏱", "أوفر تايم جماعي",      "bulk_overtime"),
    ]),
    ("الرواتب والمالية", [
        ("💰", "السلف",                  "advances"),
        ("➖", "الخصومات",               "discounts"),
        ("💼", "مسير الرواتب",          "payroll"),
        ("💵", "المصروفات والخزينة",    "expenses"),
        ("🌿", "توريدات الزرع",           "plant_deliveries"),
        ("🧾", "المحاسب القانوني",        "accountant_handover"),
    ]),
    ("التقارير", [
        ("📈", "التقارير",               "reports"),
    ]),
]

NAV_ITEMS  = [item for _, items in NAV_GROUPS for item in items]
NAV_LABELS = [label for icon, label, _ in NAV_ITEMS]

# 1-based position (within the flat radio option list) of the FIRST item
# of every group after the first — used purely to place a CSS section
# header above that item. Computed from NAV_GROUPS so it can never drift
# out of sync with the list above.
_GROUP_BOUNDARIES = []
_pos = 0
for _title, _items in NAV_GROUPS:
    _pos += 1
    if _title != NAV_GROUPS[0][0]:
        _GROUP_BOUNDARIES.append((_pos, _title))
    _pos += len(_items) - 1


@st.cache_resource(show_spinner=False)
def _logo_data_uri(path: str) -> str:
    """Read a logo file from disk and return it as a base64 data URI.
    Cached with cache_resource since the logo file never changes at
    runtime — avoids re-reading + re-encoding the image on every single
    rerun (the sidebar re-renders on every interaction)."""
    try:
        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
        ext = "png" if path.lower().endswith("png") else "jpeg"
        return f"data:image/{ext};base64,{encoded}"
    except Exception as e:
        print(f"[layout] Could not load logo from {path!r}: {e}")
        return ""


def apply_sidebar_collapse_css():
    """
    When the user hides the sidebar, collapse it to zero width by zeroing
    both flex-basis and width so the main content expands to fill the row.
    """
    collapsed = st.session_state.get('sidebar_collapsed', False)
    desktop_css = """
@media (min-width: 769px) {
  section[data-testid="stSidebar"] {
    flex: 0 0 0px !important;
    width: 0 !important;
    min-width: 0 !important;
    max-width: 0 !important;
    overflow: hidden !important;
    padding: 0 !important;
    border: none !important;
    box-shadow: none !important;
  }
  .st-key-sidebar_reopen_btn { display: block !important; }
}
""" if collapsed else ""
    mobile_transform = "translateX(110%)" if collapsed else "translateX(0)"
    st.markdown(f"""
<style>
{desktop_css}
@media (max-width: 768px) {{
  [data-testid="stAppViewContainer"] {{ overflow: visible !important; }}
  section[data-testid="stSidebar"] {{
    position: fixed !important;
    inset: 0 0 0 auto !important;
    z-index: 10000 !important;
    flex: 0 0 min(86vw, 290px) !important;
    width: min(86vw, 290px) !important;
    min-width: min(86vw, 290px) !important;
    max-width: min(86vw, 290px) !important;
    height: 100dvh !important;
    transform: {mobile_transform} !important;
    transition: transform 0.22s ease !important;
    box-shadow: 0 0 24px rgba(0,0,0,0.24) !important;
  }}
}}
</style>
""", unsafe_allow_html=True)


def render_sidebar_reopen_button():
    """
    Floating button shown in the main area when the sidebar is hidden,
    so the user always has a way to bring it back. Call this once,
    early in app.py, right after apply_sidebar_collapse_css().
    """
    collapsed = st.session_state.get('sidebar_collapsed', False)
    if st.button("☰", key="sidebar_reopen_btn", help="فتح أو إغلاق القائمة"):
        st.session_state.sidebar_collapsed = not collapsed
        st.rerun()


def render_sidebar_brand():
    """Render the company identity at the very top of the sidebar."""
    logo_uri = _logo_data_uri(LOGO_TRANSPARENT)
    logo_html = (
        f'<img src="{logo_uri}" style="width:36px;height:36px;object-fit:contain;flex-shrink:0;" />'
        if logo_uri else
        f'<div style="width:36px;height:36px;border-radius:8px;background:{COLORS["primary"]};color:#fff;'
        f'display:flex;align-items:center;justify-content:center;font-weight:600;flex-shrink:0;">{COMPANY_NAME[:1]}</div>'
    )
    with st.sidebar:
        st.markdown(f"""
<div style="padding:12px 12px 8px;">
  <div style="display:flex;align-items:center;gap:8px;">
    {logo_html}
    <div dir="ltr" style="unicode-bidi:isolate;text-align:right;font-size:14px;font-weight:600;color:#fff;line-height:1.2;white-space:nowrap;flex:0 0 auto;">{COMPANY_NAME}</div>
  </div>
</div>
""", unsafe_allow_html=True)


def render_project_selector():
    """
    Renders the project selector at the top of the sidebar, above the main
    navigation. Lets the user switch between projects, and create a new one
    via an inline "إضافة مشروع جديد" option. The selection is written to
    st.session_state['current_project_id'] (see services/projects.py) and
    persisted for the logged-in user so it's remembered next time they log
    in. Call this once, early in app.py, before render_sidebar().
    """
    from services.projects import (
        list_projects, get_current_project_id, set_current_project, create_project,
    )

    ADD_NEW = "إضافة مشروع جديد"

    projects = list_projects()
    if not projects:
        return  # shouldn't happen after the first-run migration, but guard anyway

    labels_by_id = {p.id: p.name for p in projects}
    ids_by_label = {p.name: p.id for p in projects}

    current_id = get_current_project_id()
    if current_id not in labels_by_id:
        current_id = projects[0].id
    current_label = labels_by_id[current_id]

    options = list(ids_by_label.keys()) + [ADD_NEW]

    # A newly-created project's name needs to become the selectbox's
    # selected value. We can't just write st.session_state["project_selector_box"]
    # from inside the form-submit branch below, because by the time that
    # branch runs, the selectbox widget below has *already been
    # instantiated this same script run* — Streamlit raises
    # StreamlitAPIException for writes to a widget-bound key after
    # instantiation. Instead we stash the target name here, consume it
    # BEFORE the widget is created (so it only ever affects the *next*
    # run), and let the form branch just set the stash + rerun.
    pending_label = st.session_state.pop("_pending_project_selector_label", None)
    if pending_label in options:
        st.session_state["project_selector_box"] = pending_label

    with st.sidebar:
        st.markdown("""
<p style="font-size:9.5px;font-weight:700;color:rgba(255,255,255,0.4);
          padding:14px 20px 4px;margin:0;">
  المشروع الحالي
</p>""", unsafe_allow_html=True)

        select_kwargs = dict(
            key="project_selector_box",
            label_visibility="collapsed",
            format_func=lambda label: (
                label if label == ADD_NEW or len(label) <= 24 else label[:23] + "…"
            ),
        )
        if "project_selector_box" not in st.session_state:
            select_kwargs["index"] = options.index(current_label)

        choice = st.selectbox(
            "المشروع الحالي",
            options,
            **select_kwargs,
        )

        if choice == ADD_NEW:
            with st.form("add_project_form", clear_on_submit=True):
                new_name = st.text_input("اسم المشروع الجديد", placeholder="مثال: مشروع التجمع الخامس")
                submitted = st.form_submit_button("إنشاء والتبديل إليه", type="primary", use_container_width=True)
                if submitted:
                    if not new_name.strip():
                        st.error("يرجى إدخال اسم المشروع.")
                    else:
                        project = create_project(new_name)
                        set_current_project(project.id)
                        # Defer setting the selectbox's value to the next
                        # run (see pending_label handling above) — the
                        # widget with this key has already been
                        # instantiated in this run, so writing to it here
                        # directly would raise a StreamlitAPIException.
                        st.session_state["_pending_project_selector_label"] = project.name
                        st.rerun()
        elif ids_by_label[choice] != current_id:
            set_current_project(ids_by_label[choice])
            st.rerun()

        _render_delete_project_control(projects, current_id, labels_by_id)

        st.markdown("""
<div style="height:1px;background:rgba(255,255,255,0.08);margin:6px 16px 4px;"></div>
""", unsafe_allow_html=True)


def _render_delete_project_control(projects: list, current_id: int, labels_by_id: dict):
    """
    Delete-project control, shown under the project selector.

    Always targets the CURRENTLY SELECTED project (by its project_id —
    never by name), requires an explicit confirmation checkbox before
    the button is enabled (same "confirm before destructive action"
    pattern used elsewhere in the app, e.g. reports.py's import), and
    relies entirely on services.projects.delete_project() to perform the
    delete — which also permanently removes every employee (and their
    attendance/overtime/advances/payroll), expense, and received-fund
    record scoped to that project. It never touches any project other
    than the one selected.
    """
    from services.projects import delete_project

    if len(projects) <= 1:
        return  # nothing to delete down to — always keep at least one project

    with st.sidebar:
        with st.expander("حذف المشروع الحالي", expanded=False):
            project_name = labels_by_id.get(current_id, "")
            st.markdown(
                f"<div style='font-size:12px;color:#c94b4b;line-height:1.7;'>"
                f"سيتم حذف المشروع <b>{project_name}</b> نهائياً، "
                f"مع كل بياناته المرتبطة به (الموظفون وحضورهم/أوفر تايمهم/سلفهم/رواتبهم، "
                f"والمصروفات، والأموال الواردة). هذا الإجراء لا يمكن التراجع عنه."
                f"</div>",
                unsafe_allow_html=True,
            )
            confirm = st.checkbox(
                "أؤكد أنني أرغب في حذف هذا المشروع نهائياً",
                key="delete_project_confirm_checkbox",
            )
            do_delete = st.button(
                "حذف المشروع",
                type="primary",
                use_container_width=True,
                disabled=not confirm,
                key="delete_project_button",
            )
            if do_delete and confirm:
                success, message = delete_project(current_id)
                if success:
                    st.session_state.pop("delete_project_confirm_checkbox", None)
                    remaining = [p for p in projects if p.id != current_id]
                    if remaining:
                        from services.projects import set_current_project
                        set_current_project(remaining[0].id)
                        st.session_state["_pending_project_selector_label"] = remaining[0].name
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)



_NAV_ICON_ALIAS = {"⏱⏱": "⏱", "👤": "👥"}
_EXTRA_ICON_PATHS = {"➖": '<line x1="5" y1="12" x2="19" y2="12"/>'}

# Sidebar icons are chosen per PAGE KEY (not per emoji) so every item gets its own,
# meaningful icon. Before: السلف = a bare ring, الخصومات = a bare dash, both overtime
# items shared one clock, and user-management reused the employees icon.
_NAV_KEY_ICONS = {
    "dashboard":       '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    "employees":       '<circle cx="9" cy="8" r="3"/><path d="M4 20c0-3 2-5 5-5s5 2 5 5"/><circle cx="17" cy="9" r="2.3"/><path d="M15.2 20c0-2.4 1-4 3.3-4.2"/>',
    "attendance":      '<rect x="3" y="5" width="18" height="16" rx="2"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="8" y1="3" x2="8" y2="7"/><line x1="16" y1="3" x2="16" y2="7"/><polyline points="9,15.5 11,17.5 15,13"/>',
    "overtime":        '<circle cx="12" cy="12" r="9"/><polyline points="12,7 12,12 16,14"/>',
    "bulk_overtime":   '<circle cx="10.5" cy="13.5" r="7.5"/><polyline points="10.5,9 10.5,13.5 13.5,15"/><line x1="19" y1="3" x2="19" y2="9"/><line x1="16" y1="6" x2="22" y2="6"/>',
    "advances":        '<path d="M3 7a2 2 0 0 1 2-2h12v3"/><path d="M3 7v11a2 2 0 0 0 2 2h14a1 1 0 0 0 1-1V9a1 1 0 0 0-1-1H5a2 2 0 0 1-2-1"/><circle cx="16" cy="14" r="1.2"/>',
    "discounts":       '<line x1="19" y1="5" x2="5" y2="19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/>',
    "payroll":         '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2Z"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="9" y1="12" x2="15" y2="12"/>',
    "expenses":        '<rect x="3" y="7" width="18" height="10" rx="2"/><circle cx="12" cy="12" r="2.5"/><line x1="6.5" y1="12" x2="6.5" y2="12.01"/><line x1="17.5" y1="12" x2="17.5" y2="12.01"/>',
    "plant_deliveries": '<path d="M12 21v-8"/><path d="M12 13C5 13 4 8 4 4c5 0 8 2 8 9Z"/><path d="M12 16c0-5 3-8 8-8 0 5-2 8-8 8Z"/>',
    "reports":         '<polyline points="4,17 10,11 14,15 20,7"/><polyline points="14,7 20,7 20,13"/>',
    "user_management": '<path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z"/><circle cx="12" cy="10" r="2"/><path d="M8.5 16c.6-1.6 2-2.5 3.5-2.5s2.9.9 3.5 2.5"/>',
}


def _nav_icon_css(all_items: list) -> str:
    """Line icon before each nav label (CSS mask, inherits text color).
    Purely cosmetic: keyed by list position like the group headers, never
    touches which item is selected."""
    rules = []
    for i, (icon, _label, _key) in enumerate(all_items, start=1):
        icon = _NAV_ICON_ALIAS.get(icon, icon)
        path = _NAV_KEY_ICONS.get(_key) or _EXTRA_ICON_PATHS.get(icon) or _ICONS.get(icon)
        if not path:
            continue
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
               'stroke="black" stroke-width="1.8" stroke-linecap="round" '
               f'stroke-linejoin="round">{path}</svg>')
        uri = "url(\"data:image/svg+xml," + quote(svg) + "\")"
        rules.append(f"""
section[data-testid="stSidebar"] .stRadio :is([role="radiogroup"], [data-testid="stRadioGroup"]) label:nth-of-type({i})::after {{
    content: "";
    order: -1;
    width: 20px; height: 20px; flex: 0 0 20px; align-self: center;
    background: currentColor;
    -webkit-mask: {uri} center / contain no-repeat;
    mask: {uri} center / contain no-repeat;
}}""")
    return "".join(rules)


def _render_nav_group_css(extra_items: list):
    """
    Purely-cosmetic section headers above each logical group of nav items
    (e.g. "الموارد البشرية" above "الموظفون"), rendered via CSS ::before
    on the specific radio option position — never touches which item is
    selected or how, so it can't affect routing/navigation logic at all.

    Uses the flex-wrap trick: each targeted <label> gets flex-wrap so its
    ::before (given flex-basis:100% + order:-1) drops onto its own line
    above the icon+text, instead of squeezing into the same row.
    """
    rules = []
    for position, title in _GROUP_BOUNDARIES:
        rules.append(f"""
section[data-testid="stSidebar"] .stRadio :is([role="radiogroup"], [data-testid="stRadioGroup"]) label:nth-of-type({position}) {{
    flex-wrap: wrap !important;
    margin-top: 10px !important;
}}
section[data-testid="stSidebar"] .stRadio :is([role="radiogroup"], [data-testid="stRadioGroup"]) label:nth-of-type({position})::before {{
    content: "{title}";
    flex: 1 0 100%;
    order: -1;
    font-size: 11px;
    font-weight: 500;
    color: rgba(255,255,255,0.4);
    padding: 0 4px 7px;
    margin-bottom: 4px;
    background: linear-gradient(rgba(255,255,255,0.32), rgba(255,255,255,0.32)) right bottom / calc(100% + 70px) 1px no-repeat;
    pointer-events: none;
}}
section[data-testid="stSidebar"] .stRadio :is([role="radiogroup"], [data-testid="stRadioGroup"]) label:nth-of-type({position}):has(input:checked) {{
    background: linear-gradient(to bottom, transparent 0 25px, {COLORS['primary']} 25px 100%) !important;
    box-shadow: none !important;
}}""")

    # The "extra_items" group (e.g. "إدارة المستخدمين") is only present
    # for some roles, so its header position/existence is computed here
    # at render time rather than baked into the static boundary list above.
    if extra_items:
        position = len(NAV_ITEMS) + 1
        rules.append(f"""
section[data-testid="stSidebar"] .stRadio :is([role="radiogroup"], [data-testid="stRadioGroup"]) label:nth-of-type({position}) {{
    flex-wrap: wrap !important;
    margin-top: 10px !important;
}}
section[data-testid="stSidebar"] .stRadio :is([role="radiogroup"], [data-testid="stRadioGroup"]) label:nth-of-type({position})::before {{
    content: "الإدارة";
    flex: 1 0 100%;
    order: -1;
    font-size: 11px;
    font-weight: 500;
    color: rgba(255,255,255,0.4);
    padding: 0 4px 7px;
    margin-bottom: 4px;
    background: linear-gradient(rgba(255,255,255,0.32), rgba(255,255,255,0.32)) right bottom / calc(100% + 70px) 1px no-repeat;
    pointer-events: none;
}}
section[data-testid="stSidebar"] .stRadio :is([role="radiogroup"], [data-testid="stRadioGroup"]) label:nth-of-type({position}):has(input:checked) {{
    background: linear-gradient(to bottom, transparent 0 25px, {COLORS['primary']} 25px 100%) !important;
    box-shadow: none !important;
}}""")

    rules.append(_nav_icon_css(NAV_ITEMS + list(extra_items or [])))
    st.markdown(f"<style>{''.join(rules)}</style>", unsafe_allow_html=True)


def render_sidebar(extra_items: list = None) -> str:
    """Render the sidebar and return the selected page label."""
    extra_items = extra_items or []
    all_items  = NAV_ITEMS + extra_items
    all_labels = [label for icon, label, _ in all_items]

    # ── Figure out which item should be pre-selected ──────────
    # Priority: an already-chosen radio value in session_state,
    # then the page key stored in the URL (?_page=...), so that a
    # browser reconnect (e.g. caused by split-screen / tab being
    # backgrounded) restores the same page instead of bouncing
    # back to the first item in the list.
    default_index = 0
    radio_key = "main_nav_radio"

    # Programmatic navigation (e.g. clicking a reminder in the bell): applied
    # here, before the radio widget is instantiated, so Streamlit allows it.
    _pending_nav = st.session_state.pop("_pending_nav_label", None)
    if _pending_nav in all_labels:
        st.session_state[radio_key] = _pending_nav

    current_value = st.session_state.get(radio_key)
    if current_value in all_labels:
        default_index = all_labels.index(current_value)
    else:
        page_param = st.query_params.get("_page", "")
        keys = [item[2] for item in all_items]
        if page_param in keys:
            default_index = keys.index(page_param)

    with st.sidebar:
        # ── Hide-sidebar button (top-left corner of the sidebar) ──
        if st.button("⟨", key="sidebar_hide_btn", help="إخفاء القائمة"):
            st.session_state.sidebar_collapsed = True
            st.rerun()

        _render_nav_group_css(extra_items)

        selected = st.radio(
            "القائمة الرئيسية",
            all_labels,
            index=default_index,
            key=radio_key,
            label_visibility="collapsed",
        )

    return selected


def _initials(name: str) -> str:
    parts = (name or "").split()
    if not parts:
        return "م"
    return (parts[0][0] + parts[-1][0]) if len(parts) > 1 else parts[0][0]


def _plain_role(role: str) -> str:
    """Role label without its leading emoji (ROLE_LABELS keeps emojis for
    the legacy UI; the redesigned UI shows text only)."""
    try:
        from services.auth import ROLE_LABELS
        label = ROLE_LABELS.get(role, role or "")
    except Exception:
        label = role or ""
    return label.split(" ", 1)[1] if " " in label else label


def _go_to(page_key: str, project_id: int = None, project_name: str = None):
    """Queue navigation to a page (and optionally switch project); applied on
    the next run by render_sidebar / render_project_selector."""
    if page_key in ("user_settings", "notification_settings"):
        # Not in the sidebar: routed by app.py through _page_override.
        st.session_state["_page_override"] = page_key
        st.rerun()
    label = next((lbl for _i, lbl, key in NAV_ITEMS if key == page_key), None)
    if project_id:
        from services.projects import set_current_project
        set_current_project(project_id)
        if project_name:
            st.session_state["_pending_project_selector_label"] = project_name
    if label:
        st.session_state["_pending_nav_label"] = label
    st.rerun()


def _notification_api():
    """Optional hook to the notifications module (services/notification_service.py).
    Expected functions: list_notifications(limit) -> list[dict with keys
    project_name, message, created_at, is_read], mark_all_read().
    Returns None until that module exists, so the bell simply shows an empty state."""
    try:
        from services import notification_service as ns
        return ns
    except Exception:
        return None


_BELL_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="black" '
             'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
             '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/>'
             '<path d="M13.7 21a2 2 0 0 1-3.4 0"/></svg>')
_BELL_URI = "data:image/svg+xml," + quote(_BELL_SVG)


def _topbar_css(initials: str, unread: int) -> str:
    badge = ""
    if unread > 0:
        txt = "9+" if unread > 9 else str(unread)
        badge = f"""
.st-key-tb_bell button::after {{
    content: "{txt}";
    position: absolute; top: 2px; inset-inline-end: 2px;
    min-width: 16px; height: 16px; padding: 0 4px;
    border-radius: 8px; background: {COLORS['danger']}; color: #fff;
    font-size: 10px; font-weight: 600; line-height: 16px; text-align: center;
    border: 2px solid {COLORS['surface']}; box-sizing: content-box;
}}"""
    return f"""<style>
.st-key-topbar {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 12px;
    padding: 8px 16px;
    margin-bottom: 8px;
    box-shadow: 0 1px 2px {COLORS['shadow']};
}}
/* Everything inside the bar sits on one centered row with no extra gaps */
.st-key-topbar [data-testid="stHorizontalBlock"] {{
    align-items: center !important;
    gap: 12px !important;
}}
.st-key-topbar [data-testid="stVerticalBlock"] {{ gap: 0 !important; }}
.st-key-topbar [data-testid="stVerticalBlock"] > div {{ margin-bottom: 0 !important; }}
.st-key-topbar [data-testid="column"] {{ padding: 0 !important; }}
.st-key-topbar_title .tb-crumb {{ font-size: 12px; color: {COLORS['text_muted']}; line-height: 1.4; text-align: right; }}
.st-key-topbar_title .tb-crumb .tb-sep {{ opacity: .5; margin: 0 2px; }}
.st-key-topbar_title .tb-crumb .tb-date {{ margin-inline-start: 8px; padding-inline-start: 10px; border-inline-start: 1px solid {COLORS['border']}; }}
.st-key-topbar_title .tb-title {{ font-size: 20px; font-weight: 600; color: {COLORS['text']}; line-height: 1.35; text-align: right; }}
/* Column sizing (flex): title takes the free space, bell+user keep their
   natural width. RTL order: title (right) | bell + user (left). */
.st-key-topbar [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap !important; }}
.st-key-topbar [data-testid="stHorizontalBlock"] > div {{ min-width: 0 !important; }}
.st-key-topbar [data-testid="stHorizontalBlock"] > div:nth-child(1) {{ flex: 1 1 0 !important; width: auto !important; }}
.st-key-topbar [data-testid="stHorizontalBlock"] > div:nth-child(2) {{ flex: 0 0 auto !important; width: auto !important; }}
@media (max-width: 768px) {{
    .st-key-topbar [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap !important; }}
    .st-key-topbar [data-testid="stHorizontalBlock"] > div {{
        flex: 0 0 auto !important; width: 100% !important;
    }}
}}
/* Bell + user menu: one tight group */
.st-key-tb_actions {{
    flex-direction: row !important;
    align-items: center !important;
    justify-content: flex-start !important;
    gap: 2px !important;
}}
.st-key-tb_actions > div {{ width: auto !important; flex: 0 0 auto !important; }}
.st-key-tb_bell button, .st-key-tb_user button {{
    position: relative;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: {COLORS['text']} !important;
    min-height: 40px !important;
    width: auto !important;
}}
.st-key-tb_bell button:hover, .st-key-tb_user button:hover {{
    background: {COLORS['bg']} !important;
}}
/* Bell: draw the icon ourselves (no dependency on the Material icon font) */
.st-key-tb_bell button {{
    width: 44px !important; padding: 0 !important; justify-content: center !important;
}}
.st-key-tb_bell button p, .st-key-tb_bell button span, .st-key-tb_bell button svg,
.st-key-tb_bell button [data-testid="stIconMaterial"] {{
    display: none !important;
}}
.st-key-tb_bell button::before {{
    content: ""; display: block; width: 22px; height: 22px;
    background: {COLORS['text']};
    -webkit-mask: url("{_BELL_URI}") center / contain no-repeat;
    mask: url("{_BELL_URI}") center / contain no-repeat;
}}
.st-key-tb_user button::before {{
    content: "{initials}";
    display: inline-flex; align-items: center; justify-content: center;
    width: 36px; height: 36px; border-radius: 50%;
    background: {COLORS['primary']}; color: #fff;
    font-size: 13px; font-weight: 600; margin-inline-end: 10px;
}}
{badge}
[data-testid="stPopoverBody"] {{
    border-radius: 12px !important;
    border: 1px solid {COLORS['border']} !important;
    box-shadow: 0 8px 24px {COLORS['shadow']} !important;
    padding: 18px !important;
    min-width: 300px;
}}
/* Give the account identity and its actions clear, even spacing. Streamlit
   renders popovers outside the topbar container, so style their own stack. */
[data-testid="stPopoverBody"] [data-testid="stVerticalBlock"] {{
    gap: 10px !important;
}}
[data-testid="stPopoverBody"] [data-testid="stMarkdownContainer"] p {{
    margin: 0 !important;
    line-height: 1.6 !important;
}}
[data-testid="stPopoverBody"] [data-testid="stDivider"] {{
    margin: 4px 0 !important;
}}
[data-testid="stPopoverBody"] .stButton > button {{
    min-height: 44px !important;
    padding: 9px 14px !important;
    border-radius: 10px !important;
    line-height: 1.4 !important;
}}
[data-testid="stPopoverBody"] .stButton > button p {{
    margin: 0 !important;
}}
.notif-item {{ padding: 10px 12px; border-radius: 8px; margin-bottom: 4px; }}
.notif-item.unread {{ background: {COLORS['primary_light']}; }}
.notif-title {{ font-size: 13px; font-weight: 600; color: {COLORS['text']}; }}
.notif-text  {{ font-size: 12px; color: {COLORS['text_muted']}; margin-top: 2px; }}
.notif-time  {{ font-size: 11px; color: {COLORS['text_muted']}; margin-top: 4px; }}
</style>"""


def render_topbar(page_title: str, page_icon: str = "", breadcrumb: str = ""):
    """One white bar: page title + breadcrumb + date (right) | bell + user menu (left).
    In the app's RTL layout the first column sits on the right."""
    full_name = st.session_state.get('full_name', 'مستخدم')
    username  = st.session_state.get('username', '')
    role      = _plain_role(st.session_state.get('user_role', 'viewer'))
    initials  = _initials(full_name).replace('"', '')

    ns = _notification_api()
    try:
        items = ns.list_notifications(limit=15) if ns else []
    except Exception:
        items = []
    unread = sum(1 for n in items if not n.get('is_read'))

    st.markdown(_topbar_css(initials, unread), unsafe_allow_html=True)

    # ── Page title + breadcrumb + date (all inside the one white bar) ──
    today = date.today()
    day_names   = ['الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت', 'الأحد']
    month_names = ['يناير','فبراير','مارس','إبريل','مايو','يونيو',
                   'يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر']
    date_str = f"{day_names[today.weekday()]}، {today.day} {month_names[today.month-1]} {today.year}"
    # "الرئيسية › الرئيسية" looked like a bug: only add the 2nd level when it differs
    if breadcrumb and breadcrumb.strip() not in ("الرئيسية", page_title):
        crumb_path = f'الرئيسية <span class="tb-sep">›</span> {breadcrumb}'
    else:
        crumb_path = "الرئيسية"
    crumb = f'<div class="tb-crumb">{crumb_path}<span class="tb-date">{date_str}</span></div>'

    with st.container(key="topbar"):
        # RTL: first column is on the right -> title | bell + user
        c_title, c_actions = st.columns([1, 1])
        with c_title:
            with st.container(key="topbar_title"):
                st.markdown(f'{crumb}<div class="tb-title">{page_title}</div>', unsafe_allow_html=True)
        with c_actions:
            with st.container(key="tb_actions"):
                with st.container(key="tb_bell"):
                    with st.popover("الإشعارات"):
                        st.markdown("**الإشعارات**")
                        if not items:
                            st.caption("لا توجد إشعارات")
                        for n in items:
                            cls = "notif-item" + ("" if n.get('is_read') else " unread")
                            st.markdown(
                                f'<div class="{cls}"><div class="notif-title">{n.get("project_name","")}</div>'
                                f'<div class="notif-text">{n.get("message","")}</div>'
                                f'<div class="notif-time">{n.get("created_at","")}</div></div>',
                                unsafe_allow_html=True)
                            if st.button("فتح شاشة الحضور", key=f"notif_open_{n['id']}",
                                         use_container_width=True):
                                ns.mark_read(n['id'])
                                name = n.get('project_name')
                                try:
                                    from services.projects import list_projects
                                    name = next((p.name for p in list_projects() if p.id == n['project_id']), name)
                                except Exception:
                                    pass
                                _go_to("attendance", n.get('project_id'), name)
                        if items and unread and st.button("تعليم الكل كمقروء", key="tb_mark_all",
                                                          use_container_width=True):
                            ns.mark_all_read()
                            st.rerun()
                        try:
                            from services.auth import can_access as _can_n
                            _show_notif_settings = _can_n("attendance")
                        except Exception:
                            _show_notif_settings = False
                        if _show_notif_settings:
                            st.divider()
                            if st.button("إعدادات الإشعارات", key="tb_notif_settings",
                                         use_container_width=True):
                                _go_to("notification_settings")
                with st.container(key="tb_user"):
                    with st.popover(full_name):
                        st.markdown(
                            f'<div style="font-weight:600;font-size:14px;"><bdi>{full_name}</bdi></div>'
                            f'<div style="font-size:12px;color:{COLORS["text_muted"]};margin-top:2px;">{role}'
                            f'{" · <bdi>" + username + "</bdi>" if username else ""}</div>',
                            unsafe_allow_html=True)
                        st.divider()
                        if st.button("إعدادات المستخدم", key="tb_settings",
                                     use_container_width=True):
                            _go_to("user_settings")
                        if st.button("تسجيل الخروج", key="tb_logout", use_container_width=True):
                            from services.auth import logout
                            st.query_params.clear()
                            logout()
                            st.rerun()
