import streamlit as st
import pandas as pd
from datetime import date
from database.db import get_db
from database.models import Employee, Overtime
from components.cards import section_card, empty_state, success_toast, danger_toast, stat_pills, warning_toast, info_banner
from components.layout import render_topbar
from components.theme import COLORS, MONTH_NAMES
from services.rates import calc_hourly_rate as _calc_hourly_rate
from services.projects import get_current_project_id
from services import overtime_service


def _validate_overtime_input(ot_date, hours, hourly_rate):
    """Shared validation for both the add and edit overtime forms.

    Returns an Arabic error message string if invalid, or None if the
    input is valid.
    """
    if ot_date is None:
        return "يرجى اختيار تاريخ صحيح."
    if ot_date > date.today():
        return "لا يمكن تسجيل أوفر تايم بتاريخ في المستقبل."
    if hours is None or hours <= 0:
        return "الساعات يجب أن تكون أكبر من صفر."
    if hours > 24:
        return "عدد الساعات غير منطقي (أكثر من 24 ساعة في اليوم)."
    if hourly_rate <= 0:
        return "لا يمكن حساب معدل الساعة — يرجى تحديث بيانات الموظف (الراتب أو اليومية)."
    return None


def show():
    render_topbar("الأوفر تايم", "⏱", "الأوفر تايم")
    tab1, tab2, tab3, tab4 = st.tabs(["إضافة أوفر تايم", "إدارة السجلات", "تعديل / حذف", "مصفوفة الأوفر تايم"])
    with tab1: _add_overtime()
    with tab2: _list_overtime()
    with tab3: _edit_delete_overtime()
    with tab4: _overtime_matrix()


# ─────────────────────────────────────────────────────────────────
# TAB 1 — إضافة سجل
# ─────────────────────────────────────────────────────────────────
def _add_overtime():
    section_card("إضافة سجل أوفر تايم", "➕", COLORS['warning'])
    db = get_db()
    try:
        employees = db.query(Employee).filter(
            Employee.status == 'Active', Employee.project_id == get_current_project_id()
        ).order_by(Employee.name).all()
        if not employees:
            empty_state("لا يوجد موظفون نشطون في هذا المشروع", "👥")
            return
        emp_map = {f"{e.code} — {e.name}": e for e in employees}
    finally:
        db.close()

    # اختيار الموظف خارج الـ form لعرض البيانات الحسابية فوراً
    selected_key = st.selectbox("الموظف", list(emp_map.keys()), key="add_ot_emp")
    emp = emp_map[selected_key]

    hourly_rate = _calc_hourly_rate(emp)

    # ── إذا كان هناك تكرار معلّق ينتظر قرار المستخدم، اعرض خيارات القرار أولاً ──
    # نتجاهل أي حالة معلّقة أصبحت قديمة (مثلاً غيّر المستخدم الموظف المختار)
    pending = st.session_state.get('ot_dup_pending')
    if pending and pending['employee_id'] != emp.id:
        del st.session_state['ot_dup_pending']
        pending = None

    if pending:
        warning_toast(
            f"يوجد سجل أوفر تايم بالفعل لهذا الموظف بنفس التاريخ "
            f"({pending['emp_name']} — {pending['date']}، {pending['existing_hours']} ساعة). "
            f"اختر أحد الإجراءات التالية:"
        )
        c1, c2, c3 = st.columns(3)
        do_edit    = c1.button("تعديل البيانات", use_container_width=True, key="ot_dup_edit")
        do_replace = c2.button("استبدال السجل الموجود", type="primary", use_container_width=True, key="ot_dup_replace")
        do_cancel  = c3.button("إلغاء", use_container_width=True, key="ot_dup_cancel")

        if do_edit:
            # نلغي الانتظار ونترك المستخدم يعدّل القيم في النموذج أدناه قبل إعادة الحفظ
            del st.session_state['ot_dup_pending']
            st.info("يمكنك الآن تعديل البيانات في النموذج أدناه ثم الحفظ مرة أخرى.")

        elif do_replace:
            ok, msg = overtime_service.replace_overtime(
                record_id=pending['existing_id'], project_id=get_current_project_id(),
                employee_id=pending['employee_id'], ot_date=pending['date'],
                hours=pending['hours'], rate_per_hour=pending['rate_per_hour'],
                amount=pending['amount'], notes=pending['notes'],
            )
            if ok:
                success_toast(msg)
            else:
                danger_toast(msg)
            del st.session_state['ot_dup_pending']
            st.rerun()

        elif do_cancel:
            del st.session_state['ot_dup_pending']
            info_banner("تم إلغاء العملية. لم يتم حفظ أو تعديل أي سجل.", "ℹ️", COLORS['text_muted'])

        st.markdown(f"<div class='section-sep'></div>", unsafe_allow_html=True)

    # A new overtime entry is reviewed on a separate screen before it is
    # written. Keep the payload in session state because the form resets on
    # submit and a Streamlit rerun follows.
    save_pending = st.session_state.get('ot_save_pending')
    if save_pending and save_pending['employee_id'] != emp.id:
        st.session_state.pop('ot_save_pending', None)
        save_pending = None
    if save_pending:
        date_label = save_pending['date'].strftime('%d/%m/%Y')
        info_banner(
            f"<b>مراجعة قبل الحفظ</b><br>الموظف: {save_pending['emp_name']} — "
            f"التاريخ: {date_label} — الساعات: {save_pending['hours']:g} — "
            f"المبلغ: {save_pending['amount']:,.2f} ج.م",
            "👀", COLORS['info']
        )
        confirm_col, cancel_col, _ = st.columns([1, 1, 4])
        if confirm_col.button("تأكيد حفظ الأوفر تايم", type="primary", key="ot_save_confirm"):
            # Recheck immediately before writing in case another entry was
            # added after the review screen opened.
            existing = overtime_service.find_duplicate(
                emp.id, save_pending['date'], project_id=get_current_project_id(),
            )
            if existing:
                st.session_state['ot_dup_pending'] = {
                    **save_pending,
                    'existing_id': existing.id,
                    'existing_hours': existing.hours,
                }
                st.session_state.pop('ot_save_pending', None)
                st.rerun()
                return

            ok, msg = overtime_service.create_overtime(
                project_id=get_current_project_id(), employee_id=emp.id,
                ot_date=save_pending['date'], hours=save_pending['hours'],
                rate_per_hour=save_pending['rate_per_hour'],
                amount=save_pending['amount'], notes=save_pending['notes'],
            )
            if ok:
                st.session_state.pop('ot_save_pending', None)
                success_toast(msg)
                st.rerun()
            else:
                danger_toast(msg)
        if cancel_col.button("إلغاء", key="ot_save_cancel"):
            st.session_state.pop('ot_save_pending', None)
            info_banner("تم الإلغاء. لم يتم حفظ أي سجل.", "ℹ️", COLORS['text_muted'])
            st.rerun()

        st.markdown(f"<div class='section-sep'></div>", unsafe_allow_html=True)

    # عرض معدل الساعة قبل الإدخال
    info_banner(
        f"<b>معدل الساعة المحسوب:</b> {hourly_rate:,.4f} ج.م &nbsp;·&nbsp; "
        f"راتب: {(emp.salary or 0):,.2f} ج.م — يومي: {(emp.daily_rate or 0):,.2f} ج.م",
        "💡", COLORS['info']
    )

    with st.form("add_overtime_form", clear_on_submit=True):
        st.markdown(
            f"<div style='font-size:12.5px;font-weight:700;color:{COLORS['text_muted']};"
            f"text-transform:uppercase;letter-spacing:.3px;margin-bottom:10px;'>بيانات الأوفر تايم</div>",
            unsafe_allow_html=True,
        )
        col1, col2 = st.columns(2)
        ot_date = col1.date_input("التاريخ", value=date.today())
        hours   = col2.number_input("الساعات", min_value=0.0, max_value=24.0, step=0.5, value=2.0)
        notes   = st.text_input("ملاحظات", placeholder="اختياري")

        st.markdown(f"<div class='section-sep'></div>", unsafe_allow_html=True)

        # عرض الحساب قبل الحفظ (read-only)
        amount = round(hours * hourly_rate, 2)
        rc1, rc2 = st.columns(2)
        rc1.metric("معدل الساعة (ج.م)", f"{hourly_rate:,.4f}")
        rc2.metric("المبلغ المحسوب (ج.م)", f"{amount:,.2f}")

        submitted = st.form_submit_button("مراجعة قبل الحفظ", type="primary", use_container_width=True)
        if submitted:
            error = _validate_overtime_input(ot_date, hours, hourly_rate)
            if error:
                st.error(error)
                return

            # ── منع التكرار: نفس الموظف + نفس التاريخ ──
            existing = overtime_service.find_duplicate(
                emp.id, ot_date, project_id=get_current_project_id(),
            )
            if existing:
                st.session_state['ot_dup_pending'] = {
                    'existing_id':    existing.id,
                    'emp_name':       emp.name,
                    'existing_hours': existing.hours,
                    'employee_id':    emp.id,
                    'date':           ot_date,
                    'hours':          hours,
                    'rate_per_hour':  hourly_rate,
                    'amount':         amount,
                    'notes':          notes,
                }
                st.rerun()
                return

            st.session_state['ot_save_pending'] = {
                'emp_name': emp.name,
                'employee_id': emp.id,
                'date': ot_date,
                'hours': hours,
                'rate_per_hour': hourly_rate,
                'amount': amount,
                'notes': notes,
            }
            st.rerun()


# ─────────────────────────────────────────────────────────────────
# TAB 2 — عرض السجلات
# ─────────────────────────────────────────────────────────────────
def _list_overtime():
    section_card("سجلات الأوفر تايم", "📋", COLORS['primary'])
    col1, col2 = st.columns(2)
    start = col1.date_input("من تاريخ", value=date.today().replace(day=1))
    end   = col2.date_input("إلى تاريخ", value=date.today())

    if start > end:
        st.error("تاريخ البداية يجب أن يكون قبل تاريخ النهاية.")
        return

    db = get_db()
    try:
        records = (
            db.query(Overtime)
            .filter(Overtime.date >= start, Overtime.date <= end,
                    Overtime.project_id == get_current_project_id())
            .order_by(Overtime.date.desc())
            .all()
        )
        if not records:
            empty_state("لا توجد سجلات أوفر تايم في هذه الفترة", "⏱")
            return

        employees = {e.id: e for e in db.query(Employee).filter(
            Employee.project_id == get_current_project_id()
        ).all()}
        data = [{
            'الرقم':        r.id,
            'الموظف':      employees[r.employee_id].name if r.employee_id in employees else '—',
            'القسم':       employees[r.employee_id].department if r.employee_id in employees else '—',
            'التاريخ':     str(r.date),
            'الساعات':     r.hours,
            'معدل الساعة': r.rate_per_hour,
            'قيمة الأوفر': r.amount,
            'ملاحظات':     r.notes or '',
        } for r in records]
    finally:
        db.close()

    df = pd.DataFrame(data)

    stat_pills([
        ("📋", "عدد السجلات",   str(len(df)),                           COLORS['primary']),
        ("⏱",  "إجمالي الساعات", f"{df['الساعات'].sum():.1f} ساعة",    COLORS['warning']),
        ("💰", "إجمالي المبلغ",  f"{df['قيمة الأوفر'].sum():,.0f} ج.م", COLORS['success']),
    ])

    search = st.text_input("بحث في السجلات", placeholder="ابحث بالاسم أو القسم أو التاريخ...")
    display_df = df.drop(columns=["الرقم"])
    if search:
        mask = display_df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)
        display_df = display_df[mask]

    st.markdown("<div style='margin-top:2px;'></div>", unsafe_allow_html=True)
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    if len(df) > 0:
        st.markdown(f"<div class='section-sep'></div>", unsafe_allow_html=True)
        dept_sum = df.groupby('القسم')['قيمة الأوفر'].sum().reset_index()
        st.bar_chart(dept_sum.set_index('القسم'))


def _overtime_matrix():
    """Monthly overtime view, aligned with the attendance matrix design."""
    section_card("مصفوفة الأوفر تايم الشهرية", "🗂️", COLORS['secondary'])

    current_project_id = get_current_project_id()
    col1, col2, col3 = st.columns(3)
    month = col1.selectbox(
        "الشهر", list(range(1, 13)), index=date.today().month - 1,
        format_func=lambda selected_month: MONTH_NAMES[selected_month - 1],
        key="ot_matrix_month",
    )
    year = col2.number_input(
        "السنة", min_value=2020, max_value=2030, value=date.today().year,
        key="ot_matrix_year",
    )

    db = get_db()
    try:
        departments = ['الكل'] + sorted(
            department[0] for department in db.query(Employee.department)
            .filter(Employee.project_id == current_project_id)
            .distinct() if department[0]
        )
    finally:
        db.close()
    selected_department = col3.selectbox("القسم", departments, key="ot_matrix_department")
    department_filter = None if selected_department == 'الكل' else selected_department

    if st.button("عرض المصفوفة", type="primary", key="show_ot_matrix"):
        with st.spinner("جاري تحميل مصفوفة الأوفر تايم..."):
            try:
                matrix = overtime_service.get_overtime_matrix(
                    int(month), int(year), department_filter, current_project_id,
                )
            except Exception as error:
                danger_toast(f"خطأ في تحميل المصفوفة: {error}")
                return

        if matrix.empty:
            empty_state("لا يوجد موظفون نشطون في هذه الفترة", "⏱")
            return

        day_columns = [column for column in matrix.columns if column.isdigit()]
        total_hours = matrix['إجمالي الأوفر تايم'].sum()
        employees_with_overtime = (matrix['إجمالي الأوفر تايم'] > 0).sum()
        active_days = (matrix[day_columns] > 0).sum().sum() if day_columns else 0

        stat_pills([
            ("👥", "عدد الموظفين", str(len(matrix)), COLORS['primary']),
            ("⏱", "إجمالي الساعات", f"{total_hours:.1f} ساعة", COLORS['warning']),
            ("📅", "أيام بها أوفر تايم", str(int(active_days)), COLORS['info']),
            ("✅", "موظفون لهم أوفر تايم", str(int(employees_with_overtime)), COLORS['success']),
        ])
        st.markdown("<div style='margin-top:4px;'></div>", unsafe_allow_html=True)
        st.dataframe(matrix, use_container_width=True, hide_index=True, height=400)
        success_toast(
            f"مصفوفة الأوفر تايم — {MONTH_NAMES[int(month) - 1]} {int(year)}"
        )


# ─────────────────────────────────────────────────────────────────
# TAB 3 — تعديل / حذف
# ─────────────────────────────────────────────────────────────────
def _edit_delete_overtime():
    section_card("تعديل / حذف سجل أوفر تايم", "✏️", COLORS['danger'])

    db_r = get_db()
    try:
        current_project_id = get_current_project_id()
        records   = db_r.query(Overtime).filter(
            Overtime.project_id == current_project_id
        ).order_by(Overtime.date.desc()).limit(100).all()
        employees = {e.id: e for e in db_r.query(Employee).filter(
            Employee.project_id == current_project_id
        ).all()}
        emp_list  = db_r.query(Employee).filter(
            Employee.status == 'Active', Employee.project_id == current_project_id
        ).all()
        if not records:
            empty_state("لا توجد سجلات", "⏱")
            return
        options = {
            f"{employees[r.employee_id].name if r.employee_id in employees else '—'} — {r.date} — {r.hours} ساعة": r.id
            for r in records
        }
        rec_map = {
            r.id: {
                'emp_id': r.employee_id,
                'date':   r.date,
                'hours':  float(r.hours),
                'rate':   float(r.rate_per_hour),
                'amount': float(r.amount),
                'notes':  r.notes or '',
            }
            for r in records
        }
        emp_options = {f"{e.code} — {e.name}": e for e in emp_list}
    finally:
        db_r.close()

    selected = st.selectbox("اختر سجلاً", list(options.keys()), key="edit_ot_select")
    rec_id = options[selected]
    rv     = rec_map[rec_id]

    # اختيار الموظف خارج الـ form لحساب المعدل فوراً
    emp_names   = list(emp_options.keys())
    current_emp = next((k for k, v in emp_options.items() if v.id == rv['emp_id']), emp_names[0] if emp_names else "")
    sel_emp_key = st.selectbox("الموظف", emp_names,
                               index=emp_names.index(current_emp) if current_emp in emp_names else 0,
                               key="edit_ot_emp")
    sel_emp     = emp_options[sel_emp_key]
    hourly_rate = _calc_hourly_rate(sel_emp)

    info_banner(
        f"<b>معدل الساعة المحسوب:</b> {hourly_rate:,.4f} ج.م &nbsp;·&nbsp; "
        f"راتب: {(sel_emp.salary or 0):,.2f} ج.م — يومي: {(sel_emp.daily_rate or 0):,.2f} ج.م",
        "💡", COLORS['info']
    )

    with st.form("edit_ot_form"):
        st.markdown(
            f"<div style='font-size:12.5px;font-weight:700;color:{COLORS['text_muted']};"
            f"text-transform:uppercase;letter-spacing:.3px;margin-bottom:10px;'>بيانات السجل</div>",
            unsafe_allow_html=True,
        )
        col1, col2 = st.columns(2)
        ot_date = col1.date_input("التاريخ", value=rv['date'])
        hours   = col2.number_input("الساعات", value=rv['hours'], min_value=0.0, step=0.5)
        notes   = st.text_input("ملاحظات", value=rv['notes'])

        st.markdown(f"<div class='section-sep'></div>", unsafe_allow_html=True)

        amount = round(hours * hourly_rate, 2)
        rc1, rc2 = st.columns(2)
        rc1.metric("معدل الساعة (ج.م)", f"{hourly_rate:,.4f}")
        rc2.metric("المبلغ المحسوب (ج.م)", f"{amount:,.2f}")

        confirm_del = st.checkbox("أؤكد حذف هذا السجل")
        cs, cd = st.columns(2)
        save   = cs.form_submit_button("تحديث",  type="primary",   use_container_width=True)
        delete = cd.form_submit_button("حذف",   type="secondary", use_container_width=True)

        if save:
            error = _validate_overtime_input(ot_date, hours, hourly_rate)
            if error:
                st.error(error)
            else:
                ok, msg = overtime_service.update_overtime(
                    record_id=rec_id, project_id=get_current_project_id(),
                    employee_id=sel_emp.id, ot_date=ot_date, hours=hours,
                    rate_per_hour=hourly_rate, amount=amount, notes=notes,
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
                ok, msg = overtime_service.delete_overtime(
                    record_id=rec_id, project_id=get_current_project_id(),
                )
                if ok:
                    success_toast(msg)
                    st.rerun()
                else:
                    danger_toast(msg)
