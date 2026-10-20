"""Settings page — currently: daily attendance reminder configuration."""
import streamlit as st
from datetime import datetime

from components.cards import section_card, success_toast, warning_toast
from components.layout import render_topbar
from services.reminder_rules import WEEKDAY_NAMES_AR, parse_time


def show():
    render_topbar("الإعدادات", "⚙️", "الإعدادات")

    # Same permission that guards the attendance screen (admin / hr).
    from services.auth import can_access
    if not can_access("attendance"):
        st.warning("ليس لديك صلاحية الوصول لهذا القسم.")
        return

    from services import notification_service as ns

    section_card("تذكير الحضور اليومي", "🔔")
    st.caption("يصل إشعار منفصل لكل مشروع نشط في الوقت المحدد، في أيام العمل المختارة فقط.")

    s = ns.get_settings()
    with st.form("reminder_settings_form"):
        enabled = st.toggle("تفعيل تذكير الحضور اليومي", value=s["enabled"])
        c1, c2 = st.columns([1, 2])
        t = c1.time_input("وقت التذكير", value=parse_time(s["time"]), step=300)
        days = c2.multiselect(
            "أيام العمل",
            options=list(WEEKDAY_NAMES_AR.keys()),
            default=s["working_days"],
            format_func=lambda d: WEEKDAY_NAMES_AR[d],
        )
        saved = st.form_submit_button("حفظ الإعدادات", type="primary")
        if saved:
            if enabled and not days:
                warning_toast("اختر يوم عمل واحداً على الأقل.")
            else:
                ns.save_settings(enabled, t.strftime("%H:%M"), days)
                success_toast("تم حفظ الإعدادات.")

    st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)
    if st.button("إرسال إشعار تجريبي"):
        ok = ns.show_toast(ns.TOAST_TITLE, "هذا إشعار تجريبي من HR Pro")
        if ok:
            success_toast("تم إرسال الإشعار التجريبي.")
        else:
            warning_toast("إشعارات سطح المكتب متاحة على ويندوز فقط. الإشعارات داخل البرنامج تعمل دائماً.")
