import streamlit as st
import pandas as pd
from datetime import date
from database.db import get_db
from database.models import Employee, Advance
from components.cards import section_card, empty_state, success_toast, danger_toast, stat_pills, warning_toast
from components.layout import render_topbar
from components.theme import COLORS
from services.projects import get_current_project_id
from services import advance_service


def show():
    render_topbar("إدارة السلف", "💰", "السلف")
    tab1, tab2, tab3 = st.tabs(["إضافة سلفة", "السجلات", "تعديل / حذف"])
    with tab1: _add_advance()
    with tab2: _list_advances()
    with tab3: _edit_delete_advance()


def _add_advance():
    section_card("إضافة سلفة جديدة", "➕", COLORS['success'])
    db = get_db()
    try:
        employees = db.query(Employee).filter(
            Employee.status == 'Active', Employee.project_id == get_current_project_id()
        ).all()
        if not employees:
            empty_state("لا يوجد موظفون نشطون في هذا المشروع", "👥")
            return
        emp_options = {f"{e.code} — {e.name}": e.id for e in employees}
    finally:
        db.close()

    with st.form("add_advance_form", clear_on_submit=True):
        selected  = st.selectbox("الموظف", list(emp_options.keys()))
        col1, col2 = st.columns(2)
        adv_date  = col1.date_input("التاريخ", value=date.today())
        amount    = col2.number_input("المبلغ (ج.م)", min_value=0.0, step=100.0, value=500.0)
        notes     = st.text_input("ملاحظات", placeholder="سلفة شهرية...")
        submitted = st.form_submit_button("حفظ السلفة", type="primary", use_container_width=True)
        if submitted:
            if amount <= 0:
                st.error("المبلغ يجب أن يكون أكبر من صفر.")
                return
            ok, msg = advance_service.create_advance(
                project_id=get_current_project_id(),
                employee_id=emp_options[selected],
                adv_date=adv_date, amount=amount, notes=notes,
            )
            if ok:
                success_toast(msg)
                st.rerun()
            else:
                danger_toast(msg)


def _list_advances():
    section_card("سجلات السلف", "📋", COLORS['primary'])
    col1, col2 = st.columns(2)
    start = col1.date_input("من تاريخ", value=date.today().replace(day=1))
    end   = col2.date_input("إلى تاريخ", value=date.today())

    if start > end:
        st.error("تاريخ البداية يجب أن يكون قبل تاريخ النهاية.")
        return

    db = get_db()
    try:
        records = db.query(Advance).filter(
            Advance.date >= start, Advance.date <= end,
            Advance.project_id == get_current_project_id(),
        ).order_by(Advance.date.desc()).all()

        if not records:
            empty_state("لا توجد سلف في هذه الفترة", "💰")
            return

        employees = {e.id: e for e in db.query(Employee).filter(
            Employee.project_id == get_current_project_id()
        ).all()}
        data = [{
            'الموظف':  employees[r.employee_id].name if r.employee_id in employees else '—',
            'القسم':   employees[r.employee_id].department if r.employee_id in employees else '—',
            'التاريخ': str(r.date),
            'المبلغ':  r.amount,
            'ملاحظات': r.notes or ''
        } for r in records]
        df = pd.DataFrame(data)

        stat_pills([
            ("📋", "عدد السلف",   str(len(df)),                       COLORS['primary']),
            ("💰", "إجمالي السلف", f"{df['المبلغ'].sum():,.0f} ج.م",  COLORS['danger']),
        ])
        adv_search = st.text_input("بحث في السجلات", placeholder="ابحث بالاسم أو القسم...")
        display_adv = df.copy()
        if adv_search:
            mask = display_adv.apply(lambda row: row.astype(str).str.contains(adv_search, case=False).any(), axis=1)
            display_adv = display_adv[mask]
        st.dataframe(display_adv, use_container_width=True, hide_index=True)
    except Exception as e:
        danger_toast(f"خطأ في تحميل السجلات: {e}")
    finally:
        db.close()


def _edit_delete_advance():
    section_card("تعديل / حذف سلفة", "✏️", COLORS['danger'])

    # ── Load list with a dedicated short-lived session ────────────────────
    db_r = get_db()
    try:
        current_project_id = get_current_project_id()
        records   = db_r.query(Advance).filter(
            Advance.project_id == current_project_id
        ).order_by(Advance.date.desc()).limit(100).all()
        employees = {e.id: e for e in db_r.query(Employee).filter(
            Employee.project_id == current_project_id
        ).all()}
        if not records:
            empty_state("لا توجد سجلات", "💰")
            return
        options = {
            f"{employees[r.employee_id].name if r.employee_id in employees else '—'} — {r.date} — {r.amount:.2f} ج.م": r.id
            for r in records
        }
        # Cache values before closing session
        rec_map = {r.id: {'emp_id': r.employee_id, 'date': r.date,
                          'amount': float(r.amount), 'notes': r.notes or ''}
                   for r in records}
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

    with st.form("edit_adv_form"):
        sel_emp  = st.selectbox("الموظف", emp_names,
                                index=emp_names.index(current_emp) if current_emp in emp_names else 0)
        col1, col2 = st.columns(2)
        adv_date = col1.date_input("التاريخ", value=rv['date'])
        amount   = col2.number_input("المبلغ", value=rv['amount'], min_value=0.0, step=100.0)
        notes    = st.text_input("ملاحظات", value=rv['notes'])
        confirm_del = st.checkbox("أؤكد حذف هذه السلفة")
        cs, cd   = st.columns(2)
        save     = cs.form_submit_button("تحديث", type="primary",   use_container_width=True)
        delete   = cd.form_submit_button("حذف",  type="secondary", use_container_width=True)

        if save:
            ok, msg = advance_service.update_advance(
                record_id=rec_id, project_id=get_current_project_id(),
                employee_id=emp_options[sel_emp], adv_date=adv_date,
                amount=amount, notes=notes,
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
                ok, msg = advance_service.delete_advance(
                    record_id=rec_id, project_id=get_current_project_id(),
                )
                if ok:
                    success_toast(msg)
                    st.rerun()
                else:
                    danger_toast(msg)
