"""Discounts page — HR can deduct an amount, half a day, or a number of
hours from one or several employees at once. Each employee's deduction is
priced off their OWN daily/hourly rate (services/rates.py), and the total
feeds straight into services/payroll_service.py's net-salary calculation."""
import streamlit as st
import pandas as pd
from datetime import date
from database.db import get_db
from database.models import Employee, Discount
from components.cards import section_card, empty_state, info_banner, success_toast, danger_toast, warning_toast, stat_pills
from components.layout import render_topbar
from components.theme import COLORS
from services.projects import get_current_project_id
from services import discount_service
from services.discount_service import (
    DISCOUNT_TYPE_LABELS, compute_discount_amount,
    parse_smart_discount_text, process_smart_discount,
)


def show():
    render_topbar("إدارة الخصومات", "➖", "الخصومات")
    tab1, tab2, tab3, tab4 = st.tabs([
        "إدخال ذكي", "إضافة خصم", "السجلات", "تعديل / حذف",
    ])
    with tab1: _smart_discount()
    with tab2: _add_discount()
    with tab3: _list_discounts()
    with tab4: _edit_delete_discount()


# ── Smart Paste Tab (additive — mirrors Attendance/Bulk Overtime) ──
def _smart_discount():
    section_card("الإدخال الذكي للخصومات", "🧠", COLORS['danger'])

    info_banner(
        "السطر الأول: التاريخ (مثال 20/06/2025)<br>"
        "السطر الثاني: نوع الخصم والقيمة — <code>نص يوم</code> أو <code>2 ساعة</code> أو <code>100 جنيه</code><br>"
        "باقي السطور: اسم كل موظف في سطر، ويمكن إضافة <code>+50</code> لزيادة القيمة لموظف معيّن.",
        "💡", COLORS['danger']
    )

    sample = """20/06/2025
100 جنيه
خالد طارق
أسامة علي+50
محمود فتحي"""

    text = st.text_area(
        "الصق النص هنا:",
        placeholder=sample,
        height=200,
        key="smart_discount_input",
    )

    if not text.strip():
        return

    disc_date, discount_type, base_value, entries, errors = parse_smart_discount_text(text)
    if errors:
        st.error(" | ".join(errors))
        return

    type_label = DISCOUNT_TYPE_LABELS.get(discount_type, discount_type)
    value_str = f" — القيمة: {base_value:g}" if discount_type != 'half_day' else ""
    st.markdown(
        f"<div style='background:{COLORS['info']}18;border:1px solid {COLORS['info']}33;"
        f"border-radius:8px;padding:8px 16px;margin:8px 0;font-size:13px;"
        f"color:{COLORS['info']};font-weight:600;'>"
        f"التاريخ: {disc_date.strftime('%d/%m/%Y')} — نوع الخصم: {type_label}{value_str}</div>",
        unsafe_allow_html=True,
    )

    preview_df = pd.DataFrame([
        {"الاسم المُستخرَج": e['name'], "زيادة (+)": e['bonus']} for e in entries
    ])
    st.dataframe(preview_df, use_container_width=True, hide_index=True, height=min(300, 40 + len(entries) * 36))

    col_save, _ = st.columns([1, 3])
    if col_save.button("حفظ الخصومات", type="primary", use_container_width=True, key="smart_discount_save_btn"):
        with st.spinner("جاري الحفظ..."):
            result = process_smart_discount(text)

        if not result['success']:
            danger_toast(" | ".join(result.get('errors', ['خطأ غير معروف'])))
            return

        success_toast(
            f"تم حفظ خصم {result['saved']} موظف بإجمالي {result['total']:,.2f} ج.م ليوم "
            f"{result['date'].strftime('%d/%m/%Y')}!"
        )

        stat_pills([
            ("✅", "تم الحفظ",       str(result['saved']),           COLORS['success']),
            ("🔁", "مكرر (تجاهل)",  str(len(result['duplicates'])), COLORS['warning']),
            ("⚠️", "غير متطابق",    str(len(result['unmatched'])),  COLORS['danger']),
        ])

        if result['matched']:
            with st.expander(f"الموظفون المطابقون ({len(result['matched'])})", expanded=False):
                cols = st.columns(3)
                for i, name in enumerate(result['matched']):
                    cols[i % 3].markdown(
                        f"<div style='background:{COLORS['success']}12;border:1px solid {COLORS['success']}30;"
                        f"border-radius:8px;padding:8px 12px;margin:3px 0;"
                        f"font-size:13px;color:{COLORS['success']};font-weight:600;'>{name}</div>",
                        unsafe_allow_html=True,
                    )

        if result['duplicates']:
            with st.expander(f"مكرر — له خصم بنفس النوع والتاريخ بالفعل ({len(result['duplicates'])})", expanded=True):
                st.caption("لتجنب مضاعفة الخصم، هذه الأسماء لن تُحفظ لأن لديها بالفعل خصمًا بنفس النوع والتاريخ. "
                           "لو عايز تعدّل السجل الموجود، استخدم تبويب «تعديل / حذف».")
                for name in result['duplicates']:
                    st.markdown(f"- {name}")

        if result['unmatched']:
            with st.expander(f"أسماء غير متطابقة ({len(result['unmatched'])})", expanded=True):
                info_banner(
                    "هذه الأسماء لم يتم العثور عليها في قاعدة بيانات الموظفين النشطين.",
                    "⚠️", COLORS['warning']
                )
                for name in result['unmatched']:
                    st.markdown(f"- {name}")


def _load_active_employees():
    db = get_db()
    try:
        return db.query(Employee).filter(
            Employee.status == 'Active', Employee.project_id == get_current_project_id()
        ).order_by(Employee.name).all()
    finally:
        db.close()


def _add_discount():
    section_card("إضافة خصم جديد", "➖", COLORS['danger'])
    employees = _load_active_employees()
    if not employees:
        empty_state("لا يوجد موظفون نشطون في هذا المشروع", "👥")
        return

    emp_options = {f"{e.code} — {e.name}": e.id for e in employees}
    emp_by_id   = {e.id: e for e in employees}

    select_all = st.checkbox("تحديد كل الموظفين النشطين")
    chosen_labels = st.multiselect(
        "اختر موظف واحد أو أكثر",
        list(emp_options.keys()),
        default=list(emp_options.keys()) if select_all else [],
    )
    chosen_ids = [emp_options[label] for label in chosen_labels]

    type_label = st.radio(
        "نوع الخصم", list(DISCOUNT_TYPE_LABELS.values()),
        horizontal=True,
    )
    type_key = {v: k for k, v in DISCOUNT_TYPE_LABELS.items()}[type_label]

    value = 0.0
    col1, col2 = st.columns(2)
    if type_key == 'amount':
        value = col1.number_input("قيمة الخصم (ج.م)", min_value=0.0, step=50.0, value=0.0)
    elif type_key == 'hours':
        value = col1.number_input("عدد الساعات", min_value=0.0, step=0.5, value=0.0)
    else:
        col1.markdown(
            f"<div style='padding:10px 0;color:{COLORS['text_muted']};font-size:13px;'>"
            f"سيتم خصم نصف المعدل اليومي لكل موظف تلقائياً حسب راتبه.</div>",
            unsafe_allow_html=True,
        )

    disc_date = col2.date_input("التاريخ", value=date.today())
    notes = st.text_input("ملاحظات", placeholder="سبب الخصم (تأخير، غياب بدون إذن...)")

    # ── Live preview: every employee is priced off their own rate ──────
    if chosen_ids and (type_key == 'half_day' or (value and value > 0)):
        preview_rows = []
        total_preview = 0.0
        for eid in chosen_ids:
            emp = emp_by_id[eid]
            amount, _ = compute_discount_amount(emp, type_key, value)
            preview_rows.append({'الموظف': emp.name, 'القسم': emp.department or '', 'قيمة الخصم': amount})
            total_preview += amount
        st.markdown("**معاينة قيمة الخصم لكل موظف:**")
        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)
        st.caption(f"إجمالي الخصم المتوقع: {total_preview:,.2f} ج.م")

    if st.button("حفظ الخصم", type="primary", use_container_width=True):
        if not chosen_ids:
            warning_toast("يرجى اختيار موظف واحد على الأقل.")
            return
        ok, msg, _ = discount_service.create_discounts_bulk(
            project_id=get_current_project_id(),
            employee_ids=chosen_ids,
            disc_date=disc_date,
            discount_type=type_key,
            value=value,
            notes=notes,
            created_by=st.session_state.get('user_id'),
        )
        if ok:
            success_toast(msg)
            st.rerun()
        else:
            danger_toast(msg)


def _list_discounts():
    section_card("سجلات الخصومات", "📋", COLORS['primary'])
    col1, col2 = st.columns(2)
    start = col1.date_input("من تاريخ", value=date.today().replace(day=1), key="disc_list_start")
    end   = col2.date_input("إلى تاريخ", value=date.today(), key="disc_list_end")

    if start > end:
        st.error("تاريخ البداية يجب أن يكون قبل تاريخ النهاية.")
        return

    db = get_db()
    try:
        records = db.query(Discount).filter(
            Discount.date >= start, Discount.date <= end,
            Discount.project_id == get_current_project_id(),
        ).order_by(Discount.date.desc()).all()

        if not records:
            empty_state("لا توجد خصومات في هذه الفترة", "➖")
            return

        employees = {e.id: e for e in db.query(Employee).filter(
            Employee.project_id == get_current_project_id()
        ).all()}
        data = [{
            'الموظف':   employees[r.employee_id].name if r.employee_id in employees else '—',
            'القسم':    employees[r.employee_id].department if r.employee_id in employees else '—',
            'التاريخ':  str(r.date),
            'نوع الخصم': DISCOUNT_TYPE_LABELS.get(r.discount_type, r.discount_type),
            'القيمة':   r.amount,
            'ملاحظات':  r.notes or ''
        } for r in records]
        df = pd.DataFrame(data)

        stat_pills([
            ("📋", "عدد الخصومات",   str(len(df)),                      COLORS['primary']),
            ("➖", "إجمالي الخصومات", f"{df['القيمة'].sum():,.0f} ج.م",  COLORS['danger']),
        ])
        disc_search = st.text_input("بحث في السجلات", placeholder="ابحث بالاسم أو القسم...")
        display_disc = df.copy()
        if disc_search:
            mask = display_disc.apply(lambda row: row.astype(str).str.contains(disc_search, case=False).any(), axis=1)
            display_disc = display_disc[mask]
        st.dataframe(display_disc, use_container_width=True, hide_index=True)
    except Exception as e:
        danger_toast(f"خطأ في تحميل السجلات: {e}")
    finally:
        db.close()


def _edit_delete_discount():
    section_card("تعديل / حذف خصم", "✏️", COLORS['danger'])

    db_r = get_db()
    try:
        current_project_id = get_current_project_id()
        records = db_r.query(Discount).filter(
            Discount.project_id == current_project_id
        ).order_by(Discount.date.desc()).limit(100).all()
        employees = {e.id: e for e in db_r.query(Employee).filter(
            Employee.project_id == current_project_id
        ).all()}
        if not records:
            empty_state("لا توجد سجلات", "➖")
            return
        options = {
            f"{employees[r.employee_id].name if r.employee_id in employees else '—'} — {r.date} — "
            f"{DISCOUNT_TYPE_LABELS.get(r.discount_type, r.discount_type)} — {r.amount:.2f} ج.م": r.id
            for r in records
        }
        rec_map = {r.id: {
            'emp_id': r.employee_id, 'date': r.date, 'type': r.discount_type,
            'hours': float(r.hours or 0.0), 'amount': float(r.amount),
            'notes': r.notes or '',
        } for r in records}
        emp_list    = db_r.query(Employee).filter(
            Employee.status == 'Active', Employee.project_id == current_project_id
        ).all()
        emp_options = {f"{e.code} — {e.name}": e.id for e in emp_list}
    finally:
        db_r.close()

    selected = st.selectbox("اختر سجلاً", list(options.keys()))
    rec_id   = options[selected]
    rv       = rec_map[rec_id]

    emp_names   = list(emp_options.keys())
    current_emp = next((k for k, v in emp_options.items() if v == rv['emp_id']), emp_names[0] if emp_names else "")

    type_labels = list(DISCOUNT_TYPE_LABELS.values())
    type_keys   = list(DISCOUNT_TYPE_LABELS.keys())
    current_type_idx = type_keys.index(rv['type']) if rv['type'] in type_keys else 0

    with st.form("edit_discount_form"):
        sel_emp = st.selectbox("الموظف", emp_names,
                                index=emp_names.index(current_emp) if current_emp in emp_names else 0)
        col1, col2 = st.columns(2)
        disc_date = col1.date_input("التاريخ", value=rv['date'])
        type_label = col2.radio("نوع الخصم", type_labels, index=current_type_idx, horizontal=True)
        type_key = type_keys[type_labels.index(type_label)]

        if type_key == 'amount':
            value = st.number_input("قيمة الخصم (ج.م)", value=rv['amount'], min_value=0.0, step=50.0)
        elif type_key == 'hours':
            value = st.number_input("عدد الساعات", value=rv['hours'], min_value=0.0, step=0.5)
        else:
            st.caption("سيتم إعادة احتساب نصف المعدل اليومي للموظف المختار تلقائياً.")
            value = 0.0

        notes = st.text_input("ملاحظات", value=rv['notes'])
        confirm_del = st.checkbox("أؤكد حذف هذا الخصم")
        cs, cd = st.columns(2)
        save   = cs.form_submit_button("تحديث", type="primary",   use_container_width=True)
        delete = cd.form_submit_button("حذف",  type="secondary", use_container_width=True)

        if save:
            ok, msg = discount_service.update_discount(
                record_id=rec_id, project_id=get_current_project_id(),
                employee_id=emp_options[sel_emp], disc_date=disc_date,
                discount_type=type_key, value=value, notes=notes,
            )
            if ok:
                success_toast(msg)
                st.rerun()
            else:
                danger_toast(msg)

        if delete:
            if not confirm_del:
                warning_toast("يرجى تأكيد الحذف أولاً.")
            else:
                ok, msg = discount_service.delete_discount(
                    record_id=rec_id, project_id=get_current_project_id(),
                )
                if ok:
                    success_toast(msg)
                    st.rerun()
                else:
                    danger_toast(msg)
