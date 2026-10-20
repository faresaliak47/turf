"""User management page — admin only."""
import streamlit as st
from services.auth import (
    create_user, update_user, reset_password,
    set_user_active, delete_user, get_all_users, ROLE_LABELS,
)
from components.theme import COLORS
from components.layout import render_topbar

ROLE_OPTIONS = ['admin', 'hr', 'accountant', 'viewer']


def show():
    render_topbar("إدارة المستخدمين", "👤", "إدارة المستخدمين")

    tabs = st.tabs(["قائمة المستخدمين", "إضافة مستخدم"])

    # ── Tab 1: list ───────────────────────────────────────────────────────────
    with tabs[0]:
        users = get_all_users()
        if not users:
            st.info("لا يوجد مستخدمون.")
        else:
            for user in users:
                is_self = user.id == st.session_state.get('user_id')
                status_color = COLORS['success'] if user.is_active else COLORS['danger']
                status_label = "مفعّل" if user.is_active else "معطّل"

                with st.expander(
                    f"{user.full_name}  ·  @{user.username}  ·  {status_label}",
                    expanded=False,
                ):
                    col1, col2 = st.columns(2)
                    with col1:
                        new_name = st.text_input(
                            "الاسم الكامل",
                            value=user.full_name,
                            key=f"name_{user.id}",
                        )
                        new_role = st.selectbox(
                            "الصلاحية",
                            ROLE_OPTIONS,
                            index=ROLE_OPTIONS.index(user.role) if user.role in ROLE_OPTIONS else 3,
                            format_func=lambda r: ROLE_LABELS.get(r, r),
                            key=f"role_{user.id}",
                            disabled=is_self,  # prevent self-demotion
                        )
                        if st.button("حفظ التعديلات", key=f"save_{user.id}", use_container_width=True):
                            ok, msg = update_user(user.id, new_name, new_role)
                            if ok:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

                    with col2:
                        st.markdown("**إعادة تعيين كلمة المرور**")
                        new_pw  = st.text_input("كلمة المرور الجديدة", type="password", key=f"pw_{user.id}")
                        conf_pw = st.text_input("تأكيد كلمة المرور",  type="password", key=f"cpw_{user.id}")
                        if st.button("تغيير كلمة المرور", key=f"rpw_{user.id}", use_container_width=True):
                            if len(new_pw) < 8:
                                st.error("كلمة المرور يجب أن تكون 8 أحرف على الأقل.")
                            elif new_pw != conf_pw:
                                st.error("كلمتا المرور غير متطابقتين.")
                            else:
                                ok, msg = reset_password(user.id, new_pw)
                                if ok:
                                    st.success(msg)
                                else:
                                    st.error(msg)

                        st.markdown("---")
                        if not is_self:
                            toggle_label = "تعطيل المستخدم" if user.is_active else "تفعيل المستخدم"
                            toggle_type  = "secondary"
                            if st.button(toggle_label, key=f"toggle_{user.id}", use_container_width=True, type=toggle_type):
                                ok, msg = set_user_active(user.id, not user.is_active)
                                if ok:
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)

                            confirm_del = st.checkbox(
                                f"أؤكد حذف المستخدم «{user.full_name}» نهائياً — لا يمكن التراجع.",
                                key=f"confirm_del_{user.id}",
                            )
                            if st.button(
                                "حذف المستخدم نهائياً",
                                key=f"delete_{user.id}",
                                use_container_width=True,
                                type="secondary",
                                disabled=not confirm_del,
                            ):
                                ok, msg = delete_user(user.id, st.session_state.get('user_id'))
                                if ok:
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)
                        else:
                            st.caption("لا يمكنك تعطيل أو حذف حسابك الخاص.")

    # ── Tab 2: create ─────────────────────────────────────────────────────────
    with tabs[1]:
        st.markdown(f"""
<div style="background:{COLORS['surface']};border-radius:12px;padding:20px 24px;
            border:1px solid {COLORS['border']};margin-bottom:16px;">
  <div style="font-size:15px;font-weight:700;color:{COLORS['text']};margin-bottom:4px;">إضافة مستخدم جديد</div>
  <div style="font-size:12px;color:{COLORS['text_muted']};">أدخل بيانات المستخدم الجديد أدناه.</div>
</div>
""", unsafe_allow_html=True)

        with st.form("create_user_form"):
            c1, c2 = st.columns(2)
            with c1:
                new_full_name = st.text_input("الاسم الكامل *", placeholder="مثال: سارة محمود")
                new_username  = st.text_input("اسم المستخدم *", placeholder="مثال: sara.mahmoud")
            with c2:
                new_role_sel  = st.selectbox(
                    "الصلاحية",
                    ROLE_OPTIONS,
                    format_func=lambda r: ROLE_LABELS.get(r, r),
                )
                _spacer = st.empty()

            new_pw_a = st.text_input("كلمة المرور *",      type="password", placeholder="8 أحرف على الأقل")
            new_pw_b = st.text_input("تأكيد كلمة المرور *", type="password", placeholder="أعد إدخال كلمة المرور")
            submitted = st.form_submit_button("إنشاء المستخدم", type="primary", use_container_width=True)

            if submitted:
                errors = []
                if not new_full_name.strip():
                    errors.append("الاسم الكامل مطلوب.")
                if not new_username.strip():
                    errors.append("اسم المستخدم مطلوب.")
                if len(new_pw_a) < 8:
                    errors.append("كلمة المرور يجب أن تكون 8 أحرف على الأقل.")
                if new_pw_a != new_pw_b:
                    errors.append("كلمتا المرور غير متطابقتين.")

                if errors:
                    for err in errors:
                        st.error(err)
                else:
                    ok, msg = create_user(
                        username=new_username.strip(),
                        password=new_pw_a,
                        full_name=new_full_name.strip(),
                        role=new_role_sel,
                    )
                    if ok:
                        st.success(f"{msg}")
                        st.rerun()
                    else:
                        st.error(f"{msg}")
