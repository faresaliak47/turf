"""User settings page — opened from the top-bar user menu (not in the sidebar)."""
import streamlit as st

from components.cards import section_card
from components.layout import render_topbar, _plain_role


def show():
    render_topbar("إعدادات المستخدم", "👤", "إعدادات المستخدم")

    full_name = st.session_state.get("full_name", "")
    username = st.session_state.get("username", "")
    role = _plain_role(st.session_state.get("user_role", "viewer"))
    user_id = st.session_state.get("user_id")

    section_card("بيانات الحساب", "👤")
    c1, c2, c3 = st.columns(3)
    c1.text_input("الاسم", value=full_name, disabled=True)
    c2.text_input("اسم المستخدم", value=username, disabled=True)
    c3.text_input("الصلاحية", value=role, disabled=True)

    st.markdown("<div style='margin-top:5px;'></div>", unsafe_allow_html=True)
    section_card("تغيير كلمة المرور", "🔒")
    with st.form("user_change_password_form", clear_on_submit=True):
        new_pw = st.text_input("كلمة المرور الجديدة", type="password", placeholder="8 أحرف على الأقل")
        conf_pw = st.text_input("تأكيد كلمة المرور", type="password")
        saved = st.form_submit_button("تغيير كلمة المرور", type="primary")
        if saved:
            if len(new_pw) < 8:
                st.error("كلمة المرور يجب أن تكون 8 أحرف على الأقل.")
            elif new_pw != conf_pw:
                st.error("كلمتا المرور غير متطابقتين.")
            else:
                from services.auth import reset_password
                ok, msg = reset_password(user_id, new_pw)
                (st.success if ok else st.error)(msg)
