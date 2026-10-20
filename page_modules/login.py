"""Login page for TURF Landscape Co. — HR Pro authentication."""
import streamlit as st
import base64
from services.auth import login
from components.theme import COLORS, COMPANY_NAME, COMPANY_TAGLINE, LOGO_PATH
from components.icons import render_icon


def _logo_data_uri() -> str:
    try:
        with open(LOGO_PATH, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    except Exception as e:
        print(f"[login] Could not load logo: {e}")
        return ""


def show_login():
    """Render the login page — no default credentials shown."""
    _, col, _ = st.columns([1, 2, 1])
    with col:
        logo_uri = _logo_data_uri()
        logo_html = (
            f'<img src="{logo_uri}" style="width:84px;height:auto;margin:0 auto 14px;display:block;'
            f'border-radius:14px;" />'
            if logo_uri else
            f'''<div style="background:{COLORS['primary']};
              border-radius:16px;width:60px;height:60px;
              display:flex;align-items:center;justify-content:center;
              color:#fff;margin:0 auto 16px;
              box-shadow:var(--shadow-md);">{render_icon('💼', size=26)}</div>'''
        )

        # Single merged card: logo, brand, heading and form all live in one
        # visual container — no separate header box stacked on top of the
        # form's own card, so nothing pushes the password field down.
        st.markdown(f"""
<div style="text-align:center;padding:36px 0 6px;">
  {logo_html}
  <div style="font-size:21px;font-weight:600;color:{COLORS['text']};letter-spacing:-0.2px;">{COMPANY_NAME}</div>
  <div style="font-size:12.5px;color:{COLORS['text_muted']};margin-top:3px;">{COMPANY_TAGLINE}</div>
</div>
""", unsafe_allow_html=True)

        with st.form("login_form"):
            st.markdown(
                f"""<div style="display:flex;align-items:center;justify-content:center;gap:8px;
                            margin-bottom:18px;color:{COLORS['primary']};">
                    <span style="display:flex;">{render_icon('🔐', size=19)}</span>
                    <span style="font-size:15.5px;font-weight:700;color:{COLORS['text']};">تسجيل الدخول</span>
                </div>""",
                unsafe_allow_html=True,
            )

            username  = st.text_input("اسم المستخدم", placeholder="أدخل اسم المستخدم")
            password  = st.text_input("كلمة المرور", type="password", placeholder="أدخل كلمة المرور")
            submitted = st.form_submit_button("دخول", type="primary", use_container_width=True)

            if submitted:
                if not username.strip() or not password:
                    st.error("يرجى إدخال اسم المستخدم وكلمة المرور.")
                elif login(username.strip(), password):
                    st.success(f"أهلاً {st.session_state.get('full_name', username)}!")
                    st.rerun()
                else:
                    st.error("اسم المستخدم أو كلمة المرور غير صحيحة.")
