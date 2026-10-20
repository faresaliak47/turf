"""First-run setup wizard — shown when no users exist."""
import streamlit as st
from services.auth import create_user, login
from components.theme import COLORS
from components.icons import render_icon


def show_setup_wizard():
    """Render the first-run admin setup wizard."""
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown(f"""
<div style="text-align:center;padding:32px 0 24px;">
  <div style="background:{COLORS['primary']};color:#fff;
              border-radius:16px;width:60px;height:60px;
              display:flex;align-items:center;justify-content:center;
              margin:0 auto 16px;box-shadow:var(--shadow-md);">{render_icon('⚙️', size=26)}</div>
  <div style="font-size:22px;font-weight:600;color:{COLORS['text']};letter-spacing:-0.2px;">HR Pro</div>
  <div style="font-size:13px;color:{COLORS['text_muted']};margin-top:4px;">الإعداد الأولي للنظام</div>
</div>
""", unsafe_allow_html=True)

        st.markdown(f"""
<div style="background:{COLORS['surface']};border-radius:16px;padding:20px 24px 8px;
            border:1px solid {COLORS['border']};box-shadow:var(--shadow-sm);
            margin-bottom:16px;">
  <div style="font-size:15px;font-weight:700;color:{COLORS['text']};text-align:center;margin-bottom:8px;">
    مرحباً بك! إنشاء حساب المدير
  </div>
  <div style="font-size:12px;color:{COLORS['text_muted']};text-align:center;margin-bottom:8px;">
    لا يوجد أي مستخدم بعد. أنشئ حساب المدير للبدء.
  </div>
</div>
""", unsafe_allow_html=True)

        with st.form("setup_form"):
            full_name = st.text_input("الاسم الكامل *", placeholder="مثال: محمد أحمد")
            username  = st.text_input("اسم المستخدم *", placeholder="مثال: admin")
            password  = st.text_input("كلمة المرور *", type="password", placeholder="8 أحرف على الأقل")
            confirm   = st.text_input("تأكيد كلمة المرور *", type="password", placeholder="أعد إدخال كلمة المرور")
            submitted = st.form_submit_button("إنشاء الحساب والدخول", type="primary", use_container_width=True)

            if submitted:
                errors = []
                if not full_name.strip():
                    errors.append("الاسم الكامل مطلوب.")
                if not username.strip():
                    errors.append("اسم المستخدم مطلوب.")
                if len(password) < 8:
                    errors.append("كلمة المرور يجب أن تكون 8 أحرف على الأقل.")
                if password != confirm:
                    errors.append("كلمتا المرور غير متطابقتين.")

                if errors:
                    for err in errors:
                        st.error(err)
                else:
                    ok, msg = create_user(
                        username=username.strip(),
                        password=password,
                        full_name=full_name.strip(),
                        role='admin',
                    )
                    if ok:
                        login(username.strip(), password)
                        st.success("تم إنشاء الحساب بنجاح! جاري الدخول…")
                        st.rerun()
                    else:
                        st.error(f"{msg}")
