"""Reusable card components for Odoo Mini HR Pro v2."""
import hashlib
from contextlib import contextmanager
import streamlit as st
from components.theme import COLORS
from components.icons import render_icon


def kpi_card(col, icon: str, label: str, value, color: str,
             sub_label: str = "", trend: str = None):
    """KPI card: white surface, subtle border, small tinted icon tile, strong
    neutral value. `color` only tints the icon tile (semantic use). Same call
    signature as before, so every existing caller works unchanged."""
    trend_html = ""
    if trend:
        trend_html = (
            f'<span style="background:{color}1A;color:{color};border-radius:6px;'
            f'padding:3px 8px;font-size:12px;font-weight:500;">{trend}</span>'
        )
    sub_html = (
        f'<div style="margin-top:2px;font-size:12px;color:{COLORS["text_muted"]};">{sub_label}</div>'
        if sub_label else ""
    )
    col.markdown(f"""
<div style="background:{COLORS['surface']};border-radius:12px;padding:12px 16px;
            border:1px solid {COLORS['border']};box-shadow:var(--shadow-sm);">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <div style="font-size:13px;color:{COLORS['text_muted']};font-weight:500;">{label}</div>
    <div style="background:{color}1A;color:{color};border-radius:8px;width:28px;height:28px;
                display:flex;align-items:center;justify-content:center;flex-shrink:0;">{render_icon(icon, size=15)}</div>
  </div>
  <div style="display:flex;align-items:baseline;gap:10px;margin-top:4px;">
    <div style="color:{COLORS['text']};font-size:24px;font-weight:600;line-height:1.2;font-variant-numeric:tabular-nums;">{value}</div>
    {trend_html}
  </div>
  {sub_html}
</div>
""", unsafe_allow_html=True)


def section_card(title: str, icon: str = "", color: str = None):
    """Section heading row: white card, subtle border, muted line icon + title.
    (`color` kept for call compatibility; the accent is no longer used here.)"""
    st.markdown(f"""
<div style="background:{COLORS['surface']};border-radius:12px;padding:10px 16px;margin-bottom:8px;
            border:1px solid {COLORS['border']};box-shadow:var(--shadow-sm);
            display:flex;align-items:center;gap:10px;">
  <span style="display:flex;color:{COLORS['text_muted']};">{render_icon(icon, size=18)}</span>
  <span style="font-size:15px;font-weight:600;color:{COLORS['text']};">{title}</span>
</div>
""", unsafe_allow_html=True)


@contextmanager
def card(title: str, icon: str = "", key: str = None):
    """Section card: header + everything rendered inside the `with` block share
    ONE white card (title no longer floats apart from its chart/list).
    Usage:  with card("منحنى الحضور", "📈"):  st.plotly_chart(...)
    Styling lives in components/theme.py (`st-key-card_*`)."""
    k = key or hashlib.md5(title.encode("utf-8")).hexdigest()[:8]
    with st.container(key=f"card_{k}"):
        st.markdown(f"""
<div style="display:flex;align-items:center;gap:10px;padding:12px 16px;direction:rtl;
            border-bottom:1px solid {COLORS['border']};">
  <span style="display:flex;color:{COLORS['text_muted']};">{render_icon(icon, size=18)}</span>
  <span style="font-size:15px;font-weight:600;color:{COLORS['text']};">{title}</span>
</div>
""", unsafe_allow_html=True)
        yield


def info_banner(message: str, icon: str = "ℹ️", color: str = None):
    """Styled info banner."""
    c = color or COLORS['info']
    st.markdown(f"""
<div style="
    background:{c}12;
    border:1px solid {c}44;
    border-radius:10px;
    padding:12px 18px;
    margin:8px 0;
    display:flex;align-items:flex-start;gap:10px;
    direction:rtl;
">
  <span style="flex-shrink:0;color:{c};">{render_icon(icon, size=20)}</span>
  <span style="font-size:13px;color:{COLORS['text']};line-height:1.7;">{message}</span>
</div>
""", unsafe_allow_html=True)


def status_badge(status: str) -> str:
    """Return HTML badge string for employee status."""
    cfg = {
        'Active':    (COLORS['success'], 'نشط'),
        'Inactive':  (COLORS['text_muted'], 'غير نشط'),
        'Suspended': (COLORS['danger'], 'موقوف'),
    }
    color, label = cfg.get(status, (COLORS['text_muted'], status))
    return (f'<span style="background:{color}20;color:{color};'
            f'border-radius:6px;padding:3px 10px;font-size:12px;'
            f'font-weight:500;white-space:nowrap;">{label}</span>')


def employee_card(col, code: str, name: str, job_title: str,
                  department: str, status: str, salary: float):
    """Professional employee profile card with hover effect."""
    salary = salary or 0  # DB column is nullable (Employee.salary has no
    # NOT NULL constraint), so a None here would otherwise crash the
    # ":,.0f" format below — same root cause as the Employees list's
    # total-salary sum.
    initials = "".join([w[0] for w in name.split()[:2]]) if name else "؟"
    avatar_colors = {
        'Active':    (COLORS['primary'], '#fff'),
        'Inactive':  (COLORS['text_muted'], '#fff'),
        'Suspended': (COLORS['danger'], '#fff'),
    }
    av_bg, av_fg = avatar_colors.get(status, (COLORS['primary'], '#fff'))
    badge = status_badge(status)

    col.markdown(f"""
<div class="fade-in-up emp-card" style="
    background:{COLORS['surface']};
    border-radius:12px;
    padding:20px;
    margin:6px 0;
    border:1px solid {COLORS['border']};
    box-shadow:0 1px 2px {COLORS['shadow']};
    cursor:default;
">
  <div style="display:flex;align-items:center;gap:14px;margin-bottom:14px;">
    <div style="
        background:{av_bg};
        color:{av_fg};border-radius:14px;
        width:52px;height:52px;
        display:flex;align-items:center;justify-content:center;
        font-size:19px;font-weight:600;flex-shrink:0;
        box-shadow:0 4px 12px {av_bg}44;
    ">{initials}</div>
    <div style="flex:1;min-width:0;">
      <div style="font-size:15px;font-weight:600;color:{COLORS['text']};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{name}</div>
      <div style="font-size:12px;color:{COLORS['text_muted']};margin-top:2px;">{job_title or '—'}</div>
    </div>
    {badge}
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
    <div style="background:{COLORS['bg']};border-radius:8px;padding:8px 10px;">
      <div style="font-size:10px;color:{COLORS['text_muted']};font-weight:600;margin-bottom:2px;">القسم</div>
      <div style="font-size:13px;font-weight:600;color:{COLORS['primary']};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{department or '—'}</div>
    </div>
    <div style="background:{COLORS['bg']};border-radius:8px;padding:8px 10px;">
      <div style="font-size:10px;color:{COLORS['text_muted']};font-weight:600;margin-bottom:2px;">الراتب</div>
      <div style="font-size:13px;font-weight:600;color:{COLORS['success']};">{salary:,.0f} ج.م</div>
    </div>
  </div>
  <div style="margin-top:10px;padding-top:10px;border-top:1px solid {COLORS['border']};font-size:11px;color:{COLORS['text_muted']};display:flex;align-items:center;gap:6px;">
    <span style="background:{COLORS['primary']}12;border-radius:4px;padding:2px 8px;font-weight:600;color:{COLORS['primary']};">#{code}</span>
  </div>
</div>
""", unsafe_allow_html=True)


def empty_state(message: str = "لا توجد بيانات", icon: str = "📭",
                hint: str = "أضف بيانات جديدة للبدء", flat: bool = False):
    """Quiet empty state placeholder. flat=True drops the border/background
    (use inside a card() so it is not boxed twice)."""
    box = "" if flat else (f"background:{COLORS['surface']};border-radius:12px;"
                           f"border:1px solid {COLORS['border']};")
    st.markdown(f"""
<div style="text-align:center;padding:22px 16px;{box}margin:4px 0;">
  <div style="margin-bottom:6px;color:{COLORS['text_muted']};opacity:0.6;display:flex;justify-content:center;">{render_icon(icon, size=30)}</div>
  <div style="font-size:16px;font-weight:600;color:{COLORS['text']};margin-bottom:6px;">{message}</div>
  <div style="font-size:13px;color:{COLORS['text_muted']};">{hint}</div>
</div>
""", unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "", icon: str = ""):
    """Top-of-page header: white card, subtle border, primary-tinted icon tile."""
    st.markdown(f"""
<div class="fade-in" style="
    background:{COLORS['surface']};
    border:1px solid {COLORS['border']};
    border-radius:16px;
    padding:12px 18px;
    margin-bottom:8px;
    box-shadow:0 1px 2px {COLORS['shadow']};
">
  <div style="display:flex;align-items:center;gap:16px;">
    <span style="display:flex;align-items:center;justify-content:center;width:44px;height:44px;border-radius:12px;background:{COLORS['primary_light']};color:{COLORS['primary']};">{render_icon(icon, size=22)}</span>
    <div>
      <div style="font-size:20px;font-weight:600;line-height:1.3;color:{COLORS['text']};">{title}</div>
      {'<div style="font-size:13px;color:'+COLORS['text_muted']+';margin-top:4px;">'+subtitle+'</div>' if subtitle else ''}
    </div>
  </div>
</div>
""", unsafe_allow_html=True)


def success_toast(message: str):
    st.markdown(f"""
<div class="fade-in-up" style="
    background:{COLORS['success']}12;
    border:1px solid {COLORS['success']}55;
    border-radius:10px;padding:12px 18px;
    display:flex;align-items:center;gap:10px;
    margin:8px 0;
">
  <span style="color:{COLORS['success']};">{render_icon('✅', size=18)}</span>
  <span style="font-size:14px;font-weight:600;color:{COLORS['success']};">{message}</span>
</div>
""", unsafe_allow_html=True)


def danger_toast(message: str):
    st.markdown(f"""
<div class="fade-in-up" style="
    background:{COLORS['danger']}12;
    border:1px solid {COLORS['danger']}55;
    border-radius:10px;padding:12px 18px;
    display:flex;align-items:center;gap:10px;
    margin:8px 0;
">
  <span style="color:{COLORS['danger']};">{render_icon('❌', size=18)}</span>
  <span style="font-size:14px;font-weight:600;color:{COLORS['danger']};">{message}</span>
</div>
""", unsafe_allow_html=True)


def warning_toast(message: str):
    st.markdown(f"""
<div class="fade-in-up" style="
    background:{COLORS['warning']}12;
    border:1px solid {COLORS['warning']}55;
    border-radius:10px;padding:12px 18px;
    display:flex;align-items:center;gap:10px;
    margin:8px 0;
">
  <span style="color:{COLORS['warning']};">{render_icon('⚠️', size=18)}</span>
  <span style="font-size:14px;font-weight:600;color:{COLORS['warning']};">{message}</span>
</div>
""", unsafe_allow_html=True)


def stat_pills(stats: list):
    """
    Render a horizontal row of stat pills.
    stats: list of (icon, label, value, color) tuples
    """
    pills_html = ""
    for icon, label, value, color in stats:
        pills_html += f"""
<div style="background:{COLORS['surface']};border:1px solid {COLORS['border']};border-radius:12px;
            padding:7px 14px;display:flex;align-items:center;gap:10px;
            box-shadow:var(--shadow-sm);flex:1 1 auto;min-width:150px;">
  <div style="background:{color}14;color:{color};border-radius:9px;width:32px;height:32px;
              display:flex;align-items:center;justify-content:center;flex-shrink:0;">{render_icon(icon, size=16)}</div>
  <div style="min-width:0;">
    <div style="font-size:10.5px;color:{COLORS['text_muted']};font-weight:600;white-space:nowrap;">{label}</div>
    <div style="font-size:14.5px;font-weight:600;color:{COLORS['text']};white-space:nowrap;">{value}</div>
  </div>
</div>"""

    st.markdown(f"""
<div style="display:flex;gap:10px;flex-wrap:wrap;margin:2px 0;">
  {pills_html}
</div>
""", unsafe_allow_html=True)


def confirm_delete_section(item_name: str = "هذا العنصر") -> bool:
    """Render a styled confirmation checkbox before delete."""
    confirmed = st.checkbox(f"تأكيد حذف: {item_name}")
    return confirmed


def data_card(title: str, content_html: str, icon: str = "", color: str = None):
    """Generic white data card with title."""
    c = color or COLORS['primary']
    st.markdown(f"""
<div class="fade-in" style="
    background:{COLORS['surface']};
    border-radius:14px;
    padding:20px;
    margin-bottom:16px;
    border:1px solid {COLORS['border']};
    box-shadow:0 2px 14px {COLORS['shadow']};
">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid {COLORS['border']};">
    <span style="display:flex;color:{c};">{render_icon(icon, size=18)}</span>
    <span style="font-size:15px;font-weight:600;color:{COLORS['text']};">{title}</span>
  </div>
  {content_html}
</div>
""", unsafe_allow_html=True)
