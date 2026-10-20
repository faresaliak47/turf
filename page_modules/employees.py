import streamlit as st
import pandas as pd
from datetime import date
from database.db import get_db
from database.models import Employee
from services.rates import calc_daily_rate
from services import employee_service
from components.cards import (page_header, employee_card, empty_state, status_badge,
                               section_card, success_toast, danger_toast, info_banner,
                               warning_toast, stat_pills, confirm_delete_section)
from components.layout import render_topbar
from components.theme import COLORS
from services.projects import get_current_project_id


def show():
    render_topbar("إدارة الموظفين", "👥", "الموظفون")

    tab1, tab2, tab3, tab4 = st.tabs([
        "قائمة الموظفين",
        "إضافة موظف",
        "استيراد Excel",
        "تعديل / حذف"
    ])
    with tab1: _list_employees()
    with tab2: _add_employee()
    with tab3: _import_employees()
    with tab4: _edit_delete_employee()


def _list_employees():
    db = get_db()
    try:
        employees = db.query(Employee).filter(Employee.project_id == get_current_project_id()).all()
        if not employees:
            empty_state("لا يوجد موظفون مسجلون في هذا المشروع", "👥", "أضف موظفاً جديداً من تبويب «إضافة موظف»")
            return

        # ── Filter bar (no wrapper div — avoids orphan bug) ──────────────
        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
        search        = col1.text_input("بحث بالاسم أو الكود", placeholder="اكتب للبحث...")
        depts         = sorted({e.department for e in employees if e.department})
        dept_filter   = col2.selectbox("القسم", ["الكل"] + depts)
        status_filter = col3.selectbox("الحالة", ["الكل", "Active", "Inactive", "Suspended"],
                                       format_func=lambda s: {"الكل": "الكل", "Active": "نشط",
                                                              "Inactive": "غير نشط", "Suspended": "موقوف"}.get(s, s))
        view_mode     = col4.selectbox("عرض", ["بطاقات", "جدول"])

        # ── Filter data ───────────────────────────────────────────────────
        filtered = employees
        if search:
            s = search.strip().lower()
            filtered = [e for e in filtered if s in e.name.lower() or s in (e.code or '').lower()]
        if dept_filter != "الكل":
            filtered = [e for e in filtered if e.department == dept_filter]
        if status_filter != "الكل":
            filtered = [e for e in filtered if e.status == status_filter]

        total_sal  = sum(e.salary or 0 for e in filtered)
        active_cnt = sum(1 for e in filtered if e.status == 'Active')

        stat_pills([
            ("👥", "إجمالي",         str(len(filtered)), COLORS['primary']),
            ("✅", "نشط",            str(active_cnt),    COLORS['success']),
            ("💰", "إجمالي الرواتب", f"{total_sal:,.0f} ج.م", COLORS['warning']),
        ])

        if not filtered:
            empty_state("لا توجد نتائج مطابقة", "🔍", "جرب تغيير معايير البحث")
            return

        if view_mode == "بطاقات":
            cols = st.columns(3)
            for i, emp in enumerate(filtered):
                employee_card(cols[i % 3], emp.code, emp.name,
                              emp.job_title or "", emp.department or "",
                              emp.status, emp.salary)
        else:
            data = [{
                'الكود':         e.code,
                'الاسم':         e.name,
                'المسمى':        e.job_title or '',
                'القسم':         e.department or '',
                'الراتب':        e.salary,
                'المعدل اليومي': e.daily_rate,
                'الحالة':        {'Active': 'نشط', 'Inactive': 'غير نشط', 'Suspended': 'موقوف'}.get(e.status, e.status),
            } for e in filtered]
            st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
    finally:
        db.close()


def _add_employee():
    section_card("إضافة موظف جديد", "➕", COLORS['success'])

    suggested_code = employee_service.next_employee_code()

    # إذا كان اسم الموظف المُدخل يتطابق (بعد تجاهل الهمزات/التشكيل) مع
    # موظف موجود بالفعل في هذا المشروع، لا نحفظ مباشرة — نعرض تنبيهاً
    # ونطلب من المستخدم تأكيد إنه فعلاً موظف مختلف قبل الحفظ.
    pending = st.session_state.get('emp_dup_pending')
    if pending:
        warning_toast(
            f"يوجد موظف بنفس الاسم تقريباً في هذا المشروع: "
            f"«{pending['existing_name']}» (كود {pending['existing_code']}). "
            f"هل تقصد فعلاً إضافة «{pending['name']}» كموظف مختلف؟"
        )
        c1, c2 = st.columns(2)
        do_confirm = c1.button("نعم، إضافة كموظف مختلف", type="primary",
                                use_container_width=True, key="emp_dup_confirm")
        do_cancel  = c2.button("إلغاء", use_container_width=True, key="emp_dup_cancel")

        if do_confirm:
            ok, msg = employee_service.create_employee(**pending['data'])
            del st.session_state['emp_dup_pending']
            if ok:
                if pending.get('rate_note'):
                    msg += pending['rate_note']
                success_toast(msg)
            else:
                danger_toast(msg)
            st.rerun()
        elif do_cancel:
            del st.session_state['emp_dup_pending']
            info_banner("تم إلغاء العملية. لم يتم حفظ أي موظف.", "ℹ️", COLORS['text_muted'])
        return

    with st.form("add_employee_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        code        = col1.text_input("كود الموظف *", value=suggested_code,
                                       help="مقترح تلقائياً كآخر كود + 1 — تقدر تعدّله لو حابب.")
        name        = col2.text_input("الاسم الكامل *", placeholder="محمد أحمد علي")
        job_title   = col1.text_input("المسمى الوظيفي", placeholder="مهندس")
        department  = col2.text_input("القسم", placeholder="الصيانة")
        salary      = col1.number_input("الراتب (ج.م)", min_value=0.0, step=500.0)
        daily_rate  = col2.number_input("المعدل اليومي (ج.م)", min_value=0.0, step=10.0)
        auto_rate   = st.checkbox(
            "حساب المعدل اليومي تلقائياً = الراتب ÷ 30",
            value=True,
            help="عند التفعيل، سيتم تجاهل القيمة المكتوبة في «المعدل اليومي» "
                 "أعلاه وحسابها أوتوماتيكياً من الراتب عند الحفظ — لمنع أخطاء الإدخال اليدوي.",
            key="add_emp_auto_rate",
        )
        phone       = col1.text_input("الهاتف", placeholder="01xxxxxxxxx")
        national_id = col2.text_input("الرقم القومي")
        area        = col1.text_input("المنطقة")
        hire_date   = col2.date_input("تاريخ التعيين", value=date.today())
        status      = st.selectbox("الحالة", ["Active", "Inactive", "Suspended"],
                                   format_func=lambda s: {"Active": "نشط",
                                                          "Inactive": "غير نشط",
                                                          "Suspended": "موقوف"}[s])
        submitted = st.form_submit_button("حفظ الموظف", type="primary", use_container_width=True)
        if submitted:
            if not code.strip() or not name.strip():
                st.error("الكود والاسم حقول إجبارية.")
                return
            final_daily_rate = calc_daily_rate(salary) if auto_rate else daily_rate
            emp_data = dict(
                project_id=get_current_project_id(),
                code=code.strip(), name=name.strip(),
                job_title=job_title, department=department,
                salary=salary, daily_rate=final_daily_rate,
                phone=phone, national_id=national_id,
                area=area, hire_date=hire_date, status=status,
            )
            rate_note = f" (المعدل اليومي المحسوب: {final_daily_rate:,.2f} ج.م)" if auto_rate else ""

            similar = employee_service.find_similar_employee(emp_data['project_id'], emp_data['name'])
            if similar:
                st.session_state['emp_dup_pending'] = {
                    'data': emp_data, 'name': emp_data['name'],
                    'existing_name': similar.name, 'existing_code': similar.code,
                    'rate_note': rate_note,
                }
                st.rerun()
                return

            ok, msg = employee_service.create_employee(**emp_data)
            if ok:
                if auto_rate:
                    msg += rate_note
                success_toast(msg)
                st.rerun()
            else:
                danger_toast(msg)


def _import_employees():
    section_card("استيراد الموظفين من Excel", "📥", COLORS['info'])
    info_banner(
        "يجب أن يحتوي الملف على الأعمدة: ID · Name · Job Title · Department · Salary · Daily Rate",
        "📋", COLORS['info']
    )
    uploaded = st.file_uploader("اسحب وأفلت ملف Excel هنا", type=["xlsx", "xls"])
    if not uploaded:
        return
    try:
        df = pd.read_excel(uploaded)
        st.caption(f"معاينة البيانات — {len(df)} صف")
        st.dataframe(df.head(5), use_container_width=True, hide_index=True)

        col_map = {
            'ID': 'code', 'Name': 'name', 'Job Title': 'job_title',
            'Department': 'department', 'Salary': 'salary', 'Daily Rate': 'daily_rate'
        }
        mapped = {}
        for expected, field in col_map.items():
            for actual in df.columns:
                if expected.lower() in str(actual).lower():
                    mapped[field] = actual
                    break

        if 'code' not in mapped or 'name' not in mapped:
            danger_toast("لم يتم العثور على أعمدة ID و Name في الملف.")
            return

        if st.button("استيراد الآن", type="primary", use_container_width=True):
            db = get_db()
            added = skipped = 0
            try:
                for _, row in df.iterrows():
                    code = str(row[mapped['code']]).strip()
                    name = str(row[mapped['name']]).strip()
                    if not code or not name or code == 'nan':
                        continue
                    if db.query(Employee).filter(Employee.code == code).first():
                        skipped += 1
                        continue
                    db.add(Employee(
                        code=code, name=name,
                        job_title=str(row.get(mapped.get('job_title', ''), '')).strip() if mapped.get('job_title') else '',
                        department=str(row.get(mapped.get('department', ''), '')).strip() if mapped.get('department') else '',
                        salary=float(row[mapped['salary']]) if mapped.get('salary') else 0.0,
                        daily_rate=float(row[mapped['daily_rate']]) if mapped.get('daily_rate') else 0.0,
                        status='Active',
                        project_id=get_current_project_id(),
                    ))
                    added += 1
                db.commit()
                success_toast(f"تم استيراد {added} موظف بنجاح. تم تخطي {skipped} مكرر.")
                st.rerun()
            except Exception as e:
                db.rollback()
                danger_toast(f"خطأ في الاستيراد: {e}")
            finally:
                db.close()
    except Exception as e:
        danger_toast(f"خطأ في قراءة الملف: {e}")


def _edit_delete_employee():
    # ── CRITICAL FIX: Use two separate DB sessions for read vs write ──────
    # Read list for selectbox
    db_read = get_db()
    try:
        employees = db_read.query(Employee).filter(
            Employee.project_id == get_current_project_id()
        ).order_by(Employee.code).all()
        if not employees:
            empty_state("لا يوجد موظفون في هذا المشروع", "👥")
            return
        emp_options = {f"{e.code} — {e.name}": e.id for e in employees}
    finally:
        db_read.close()

    section_card("تعديل أو حذف موظف", "✏️", COLORS['warning'])
    selected = st.selectbox("اختر موظفاً", list(emp_options.keys()))
    emp_id   = emp_options[selected]

    # Load fresh record for display
    db_show = get_db()
    try:
        emp = db_show.query(Employee).filter(Employee.id == emp_id).first()
        if not emp:
            return

        st.markdown(
            f"<div style='margin:8px 0;'>الحالة الحالية: {status_badge(emp.status)}</div>",
            unsafe_allow_html=True
        )

        # Read current values into local variables before closing session
        v_code = emp.code; v_name = emp.name; v_job = emp.job_title or ''
        v_dept = emp.department or ''; v_salary = float(emp.salary or 0)
        v_rate = float(emp.daily_rate or 0); v_phone = emp.phone or ''
        v_nid  = emp.national_id or ''; v_area = emp.area or ''
        v_status = emp.status or 'Active'
    finally:
        db_show.close()

    with st.form("edit_employee_form"):
        col1, col2 = st.columns(2)
        code        = col1.text_input("الكود",           value=v_code)
        name        = col2.text_input("الاسم",            value=v_name)
        job_title   = col1.text_input("المسمى",           value=v_job)
        department  = col2.text_input("القسم",            value=v_dept)
        salary      = col1.number_input("الراتب",         value=v_salary, step=500.0)
        daily_rate  = col2.number_input("المعدل اليومي",  value=v_rate, step=10.0)
        auto_rate   = st.checkbox(
            "إعادة حساب المعدل اليومي تلقائياً = الراتب ÷ 30",
            value=False,
            help="عند التفعيل، سيتم تجاهل القيمة المكتوبة في «المعدل اليومي» "
                 "وحسابها أوتوماتيكياً من الراتب الجديد عند التحديث.",
            key="edit_emp_auto_rate",
        )
        phone       = col1.text_input("الهاتف",           value=v_phone)
        national_id = col2.text_input("الرقم القومي",    value=v_nid)
        area        = col1.text_input("المنطقة",          value=v_area)
        status_opts = ["Active", "Inactive", "Suspended"]
        status      = col2.selectbox(
            "الحالة", status_opts,
            index=status_opts.index(v_status) if v_status in status_opts else 0,
            format_func=lambda s: {"Active": "نشط", "Inactive": "غير نشط", "Suspended": "موقوف"}[s]
        )

        confirm_name_dup = st.checkbox(
            "أؤكد أن هذا موظف مختلف رغم تشابه الاسم مع موظف آخر في المشروع",
            help="تظهر الحاجة لهذا التأكيد فقط إذا كان الاسم مطابقاً "
                 "(بعد تجاهل الهمزات/التشكيل، مثل «أبو» و«ابو») لموظف آخر بالفعل.",
            key="edit_emp_confirm_name_dup",
        )
        confirm_del = st.checkbox("أؤكد حذف هذا الموظف وجميع بياناته")
        c_save, c_del = st.columns(2)
        save   = c_save.form_submit_button("تحديث",       type="primary",   use_container_width=True)
        delete = c_del.form_submit_button("حذف الموظف", type="secondary", use_container_width=True)

        if save:
            if not name.strip():
                st.error("الاسم لا يمكن أن يكون فارغاً.")
            else:
                similar = employee_service.find_similar_employee(
                    get_current_project_id(), name.strip(), exclude_id=emp_id
                )
                if similar and not confirm_name_dup:
                    warning_toast(
                        f"يوجد موظف آخر بنفس الاسم تقريباً في هذا المشروع: "
                        f"«{similar.name}» (كود {similar.code}). إذا كان فعلاً موظفاً مختلفاً، "
                        f"فعّل خانة التأكيد أعلاه ثم اضغط «تحديث» مرة أخرى."
                    )
                else:
                    final_daily_rate = calc_daily_rate(salary) if auto_rate else daily_rate
                    ok, msg = employee_service.update_employee(
                        employee_id=emp_id, project_id=get_current_project_id(),
                        code=code, name=name, job_title=job_title, department=department,
                        salary=salary, daily_rate=final_daily_rate,
                        phone=phone, national_id=national_id, area=area, status=status,
                    )
                    if ok:
                        success_toast(msg)
                        st.rerun()
                    else:
                        danger_toast(msg)

        if delete:
            if not confirm_del:
                warning_toast("يرجى تأكيد الحذف بتفعيل خانة التأكيد أولاً.")
            else:
                ok, msg = employee_service.delete_employee(
                    employee_id=emp_id, project_id=get_current_project_id(),
                )
                if ok:
                    success_toast(msg)
                    st.rerun()
                else:
                    danger_toast(msg)
