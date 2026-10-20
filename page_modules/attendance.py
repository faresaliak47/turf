import streamlit as st
import pandas as pd
from datetime import date
from database.db import get_db
from database.models import Employee, Attendance
from services.attendance_service import (
    process_attendance, get_attendance_matrix,
    parse_smart_attendance_text, process_smart_attendance,
    update_attendance_record, delete_attendance_record,
    count_attendance_for_day, delete_attendance_for_day,
    count_attendance_for_month, delete_attendance_for_month,
    mark_attendance_bulk_dates,
)
import calendar
from components.cards import (section_card, empty_state, info_banner,
                               success_toast, danger_toast, warning_toast, stat_pills)
from components.layout import render_topbar
from components.theme import COLORS, MONTH_NAMES
from services.projects import get_current_project_id, get_current_project_name


def show():
    render_topbar("الحضور والغياب", "📅", "الحضور والغياب")
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "إدخال ذكي",
        "إدخال عادي",
        "أيام متفرقة لموظف",
        "مصفوفة الحضور",
        "سجلات الحضور",
        "تعديل / حذف",
        "حذف بالتاريخ",
    ])
    with tab1: _smart_attendance()
    with tab2: _input_attendance()
    with tab3: _bulk_dates_for_employee()
    with tab4: _attendance_matrix()
    with tab5: _attendance_records()
    with tab6: _edit_delete_attendance()
    with tab7: _delete_by_date_attendance()


def _confirm_pending_attendance(session_key: str, processor):
    """Show an explicit overwrite choice for a duplicate attendance paste."""
    text = st.session_state.get(session_key)
    if not text:
        return

    details_key = f"{session_key}_details"
    details = st.session_state.get(details_key, {})
    conflicts = details.get('conflicts', [])
    att_date = details.get('date')
    date_text = att_date.strftime('%d/%m/%Y') if hasattr(att_date, 'strftime') else str(att_date or '')
    warning_toast(
        f"يوجد {len(conflicts)} سجل حضور مكرر بتاريخ {date_text}. "
        "راجع العامل وعدد العمال المسجل والجديد قبل تأكيد الاستبدال."
        if conflicts else "يوجد حضور مسجل بالفعل. هل تريد استبداله بالبيانات الجديدة؟"
    )

    if conflicts:
        rows = []
        for conflict in conflicts:
            old_count = conflict.get('old', {}).get('workers_count', 1)
            new_count = conflict.get('new', {}).get('workers_count', 1)
            try:
                old_count = f"{float(old_count or 0):g}"
            except (TypeError, ValueError):
                old_count = str(old_count)
            try:
                new_count = f"{float(new_count or 0):g}"
            except (TypeError, ValueError):
                new_count = str(new_count)
            rows.append({
                "اسم العامل": conflict.get('name', '—'),
                "العدد المسجل حاليًا": old_count,
                "العدد في الإدخال الجديد": new_count,
            })
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
            height=min(260, 38 + len(rows) * 36),
        )

    confirm_col, cancel_col, _ = st.columns([1, 1, 4])
    if confirm_col.button("تأكيد الاستبدال", type="primary", key=f"{session_key}_confirm"):
        result = processor(text, confirm_updates=True)
        st.session_state.pop(session_key, None)
        st.session_state.pop(details_key, None)
        if result.get('success'):
            success_toast(f"تم تحديث {result.get('updated', 0)} سجل حضور بنجاح.")
        else:
            for error in result.get('errors', ['تعذر تحديث الحضور.']):
                danger_toast(error)
    if cancel_col.button("إلغاء", key=f"{session_key}_cancel"):
        st.session_state.pop(session_key, None)
        st.session_state.pop(details_key, None)


# ── Smart Attendance Tab ──────────────────────────────────────────

def _smart_attendance():
    section_card("الإدخال الذكي للحضور", "🧠", COLORS['primary'])

    info_banner(
        "أدخل النص الحر مباشرة — كل سطر موظف.<br>"
        "<b>بدون رقم:</b> عدد العمال = 1 تلقائياً<br>"
        "<b>بدون تاريخ:</b> يُستخدم تاريخ اليوم تلقائياً<br>"
        "<b>مثال:</b> <code>6 عمال سامح</code> → سامح، 6 عمال | <code>خالد طارق</code> → خالد طارق، 1 عامل",
        "💡", COLORS['primary']
    )

    # ── Sample placeholder ────────────────────────────────────────
    sample = """20/06/2025
خالد طارق
أسامة علي
6 عمال سامح
7 عمال مختار
2 عمال أشرف"""

    text = st.text_area(
        "الصق النص هنا:",
        placeholder=sample,
        height=220,
        help="السطر الأول تاريخ اختياري (DD/MM/YYYY)، ثم الأسماء",
        key="smart_att_input",
    )

    # ── Live Preview ──────────────────────────────────────────────
    if text.strip():
        att_date, entries, errors = parse_smart_attendance_text(text)

        if errors:
            st.error(" | ".join(errors))
        else:
            # Date display
            st.markdown(
                f"<div style='background:{COLORS['info']}18;border:1px solid {COLORS['info']}33;"
                f"border-radius:8px;padding:8px 16px;margin:8px 0;font-size:13px;"
                f"color:{COLORS['info']};font-weight:600;'>التاريخ المُحدَّد: {att_date.strftime('%d/%m/%Y')}</div>",
                unsafe_allow_html=True,
            )

            # Parsed entries table preview
            total_workers = sum(e['workers_count'] for e in entries)
            st.markdown(
                f"<div style='background:{COLORS['success']}12;border:1px solid {COLORS['success']}30;"
                f"border-radius:8px;padding:8px 16px;margin:4px 0 10px;font-size:13px;"
                f"color:{COLORS['success']};font-weight:700;'>"
                f"تم تحليل {len(entries)} سطر — إجمالي العمال: {total_workers}</div>",
                unsafe_allow_html=True,
            )

            preview_df = pd.DataFrame([
                {
                    "الاسم المُستخرَج": e['name'],
                    "عدد العمال":       e['workers_count'],
                }
                for e in entries
            ])
            st.dataframe(preview_df, use_container_width=True, hide_index=True, height=min(300, 40 + len(entries) * 36))

            # ── Save Button ───────────────────────────────────────
            st.markdown("<div style='margin-top:4px;'></div>", unsafe_allow_html=True)
            col_save, _ = st.columns([1, 3])
            if col_save.button("حفظ الحضور", type="primary", use_container_width=True, key="smart_save_btn"):
                with st.spinner("جاري الحفظ..."):
                    result = process_smart_attendance(text)

                if result['success']:
                    success_toast(
                        f"تم حفظ حضور يوم {result['date'].strftime('%d/%m/%Y')} بنجاح!"
                    )

                    stat_pills([
                        ("✅", "تم الحفظ",       str(result['saved']),          COLORS['success']),
                        ("🔁", "مكرر (تجاهل)",  str(result['duplicates']),     COLORS['warning']),
                        ("⚠️", "غير متطابق",    str(len(result['unmatched'])), COLORS['danger']),
                    ])

                    if result['matched']:
                        with st.expander(f"الموظفون المطابقون ({len(result['matched'])})", expanded=False):
                            cols = st.columns(3)
                            for i, entry in enumerate(result['matched']):
                                worker_badge = (
                                    f" <span style='background:{COLORS['primary']}22;border-radius:4px;"
                                    f"padding:1px 6px;font-size:11px;'>{entry['workers_count']} عمال</span>"
                                    if entry['workers_count'] > 1 else ""
                                )
                                cols[i % 3].markdown(
                                    f"<div style='background:{COLORS['success']}12;border:1px solid {COLORS['success']}30;"
                                    f"border-radius:8px;padding:8px 12px;margin:3px 0;"
                                    f"font-size:13px;color:{COLORS['success']};font-weight:600;'>"
                                    f"{entry['name']}{worker_badge}</div>",
                                    unsafe_allow_html=True,
                                )

                    if result['unmatched']:
                        with st.expander(f"أسماء غير متطابقة ({len(result['unmatched'])})", expanded=True):
                            info_banner(
                                "هذه الأسماء لم يتم العثور عليها في قاعدة بيانات الموظفين النشطين.",
                                "⚠️", COLORS['warning']
                            )
                            cols = st.columns(3)
                            for i, entry in enumerate(result['unmatched']):
                                cols[i % 3].markdown(
                                    f"<div style='background:{COLORS['warning']}12;border:1px solid {COLORS['warning']}30;"
                                    f"border-radius:8px;padding:8px 12px;margin:3px 0;"
                                    f"font-size:13px;color:{COLORS['warning']};font-weight:600;'>"
                                    f"{entry['name']} ({entry['workers_count']})</div>",
                                    unsafe_allow_html=True,
                                )
                elif result.get('requires_confirmation'):
                    st.session_state['pending_smart_attendance'] = text
                    st.session_state['pending_smart_attendance_details'] = {
                        'date': result.get('date'),
                        'conflicts': result.get('conflicts', []),
                    }
                else:
                    for err in result.get('errors', ['تعذر حفظ الحضور.']):
                        danger_toast(err)

            _confirm_pending_attendance('pending_smart_attendance', process_smart_attendance)
    else:
        # Show format guide when empty
        st.markdown(
            f"""
<div style="background:{COLORS['surface']};border:1px solid {COLORS['border']};
border-radius:14px;padding:22px 24px;margin-top:10px;box-shadow:0 2px 14px {COLORS['shadow']};">
  <p style="font-size:13px;font-weight:700;color:{COLORS['text_muted']};margin-bottom:14px;
            text-transform:uppercase;letter-spacing:.3px;">
    تنسيقات مقبولة
  </p>
  <table style="width:100%;border-collapse:collapse;font-size:13px;">
    <tr style="border-bottom:2px solid {COLORS['primary']}22;">
      <td style="padding:8px 12px;color:{COLORS['text_muted']};font-weight:700;font-size:11.5px;text-transform:uppercase;">النص</td>
      <td style="padding:8px 12px;color:{COLORS['text_muted']};font-weight:700;font-size:11.5px;text-transform:uppercase;">الاسم</td>
      <td style="padding:8px 12px;color:{COLORS['text_muted']};font-weight:700;font-size:11.5px;text-transform:uppercase;">عدد العمال</td>
    </tr>
    <tr style="border-bottom:1px solid {COLORS['border']};">
      <td style="padding:9px 12px;font-family:monospace;color:{COLORS['primary']};">خالد طارق</td>
      <td style="padding:9px 12px;color:{COLORS['text']};">خالد طارق</td>
      <td style="padding:9px 12px;color:{COLORS['success']};font-weight:700;">1</td>
    </tr>
    <tr style="border-bottom:1px solid {COLORS['border']};">
      <td style="padding:9px 12px;font-family:monospace;color:{COLORS['primary']};">6 عمال سامح</td>
      <td style="padding:9px 12px;color:{COLORS['text']};">سامح</td>
      <td style="padding:9px 12px;color:{COLORS['success']};font-weight:700;">6</td>
    </tr>
    <tr style="border-bottom:1px solid {COLORS['border']};">
      <td style="padding:9px 12px;font-family:monospace;color:{COLORS['primary']};">7 عمال مختار</td>
      <td style="padding:9px 12px;color:{COLORS['text']};">مختار</td>
      <td style="padding:9px 12px;color:{COLORS['success']};font-weight:700;">7</td>
    </tr>
    <tr>
      <td style="padding:9px 12px;font-family:monospace;color:{COLORS['primary']};">2 أشرف</td>
      <td style="padding:9px 12px;color:{COLORS['text']};">أشرف</td>
      <td style="padding:9px 12px;color:{COLORS['success']};font-weight:700;">2</td>
    </tr>
  </table>
</div>
""",
            unsafe_allow_html=True,
        )


# ── Classic Attendance Tab (unchanged) ───────────────────────────

def _input_attendance():
    section_card("إدخال الحضور اليومي", "📝", COLORS['primary'])
    info_banner(
        "السطر الأول: التاريخ بصيغة DD/MM/YYYY<br>باقي الأسطر: أسماء الموظفين (سطر لكل موظف)<br>يمكن إضافة بادئات مثل «م» أو «أ» قبل الاسم",
        "📋", COLORS['primary']
    )

    sample = f"""{date.today().strftime('%d/%m/%Y')}
م محمد عبدالجواد
م محمد التوني
شريف ابو العزم
شحاته رزق
عادل عربي"""

    text = st.text_area(
        "أدخل بيانات الحضور:",
        placeholder=sample,
        height=200,
        help="السطر الأول تاريخ، ثم الأسماء"
    )

    st.markdown("<div style='margin-top:2px;'></div>", unsafe_allow_html=True)
    col1, col2 = st.columns([1, 4])
    with col1:
        submitted = st.button("حفظ الحضور", type="primary", use_container_width=True)

    if submitted:
        if not text.strip():
            st.error("الرجاء إدخال بيانات الحضور.")
            return
        with st.spinner("جاري معالجة بيانات الحضور..."):
            try:
                result = process_attendance(text)
            except Exception as e:
                danger_toast(f"خطأ في المعالجة: {e}")
                return

        if result['success']:
            success_toast(f"تم حفظ حضور يوم {result['date']} بنجاح!")

            stat_pills([
                ("✅", "تم الحفظ",       str(result['saved']),         COLORS['success']),
                ("🔁", "مكرر (تجاهل)",  str(result['duplicates']),    COLORS['warning']),
                ("⚠️", "غير متطابق",    str(len(result['unmatched'])), COLORS['danger']),
            ])

            if result['matched']:
                with st.expander(f"الموظفون المطابقون ({len(result['matched'])})", expanded=False):
                    cols = st.columns(3)
                    for i, name in enumerate(result['matched']):
                        cols[i % 3].markdown(f"""
<div style="background:{COLORS['success']}12;border:1px solid {COLORS['success']}30;
            border-radius:8px;padding:8px 12px;margin:3px 0;
            font-size:13px;color:{COLORS['success']};font-weight:600;">
  {name}
</div>""", unsafe_allow_html=True)

            if result['unmatched']:
                with st.expander(f"أسماء غير متطابقة ({len(result['unmatched'])})", expanded=True):
                    info_banner("هذه الأسماء لم يتم العثور عليها في قاعدة بيانات الموظفين النشطين.", "⚠️", COLORS['warning'])
                    cols = st.columns(3)
                    for i, name in enumerate(result['unmatched']):
                        cols[i % 3].markdown(f"""
<div style="background:{COLORS['warning']}12;border:1px solid {COLORS['warning']}30;
            border-radius:8px;padding:8px 12px;margin:3px 0;
            font-size:13px;color:{COLORS['warning']};font-weight:600;">
  {name}
</div>""", unsafe_allow_html=True)
        elif result.get('requires_confirmation'):
            st.session_state['pending_classic_attendance'] = text
            st.session_state['pending_classic_attendance_details'] = {
                'date': result.get('date'),
                'conflicts': result.get('conflicts', []),
            }
        else:
            for err in result.get('errors', ['تعذر حفظ الحضور.']):
                danger_toast(err)

    _confirm_pending_attendance('pending_classic_attendance', process_attendance)


# ── Bulk: one employee, several non-consecutive days at once ────────
# For the common "we forgot to log him day by day, but we know he
# actually showed up on the 3rd, the 9th and the 17th" case — pick the
# employee once, tick every day he was present across a chosen month,
# save in one go instead of one row at a time.

def _bulk_dates_for_employee():
    section_card("تسجيل أيام متفرقة لموظف واحد", "📌", COLORS['secondary'])
    info_banner(
        "اختر الموظف والشهر، ثم حدد كل الأيام التي كان فيها حاضراً (مش لازم تكون متتالية) "
        "واضغط حفظ — هيتسجلوا كلهم دفعة واحدة. أي يوم مسجل بالفعل لنفس الموظف يتم تجاوزه تلقائياً.",
        "💡", COLORS['secondary']
    )

    current_project_id = get_current_project_id()

    db = get_db()
    try:
        emp_list = db.query(Employee).filter(
            Employee.status == 'Active', Employee.project_id == current_project_id
        ).order_by(Employee.name).all()
    finally:
        db.close()

    if not emp_list:
        empty_state("لا يوجد موظفون نشطون في هذا المشروع", "👤")
        return

    emp_options = {f"{e.code} — {e.name}": e.id for e in emp_list}
    sel_emp = st.selectbox("الموظف", list(emp_options.keys()), key="bulk_att_emp")
    employee_id = emp_options[sel_emp]

    col1, col2, col3 = st.columns([2, 1, 1])
    month = col1.selectbox(
        "الشهر", list(range(1, 13)),
        index=date.today().month - 1,
        format_func=lambda m: MONTH_NAMES[m - 1],
        key="bulk_att_month",
    )
    year = col2.number_input("السنة", min_value=2020, max_value=2030,
                              value=date.today().year, key="bulk_att_year")
    workers_count = col3.number_input("عدد الأفراد/يوم", min_value=0.5, value=1.0,
                                       step=0.5, key="bulk_att_workers")

    days_in_month = calendar.monthrange(int(year), int(month))[1]
    all_days = [date(int(year), int(month), d) for d in range(1, days_in_month + 1)]

    selected_days = st.multiselect(
        "اختر الأيام التي كان فيها حاضراً",
        options=all_days,
        format_func=lambda d: f"{d.day:02d} ({['إثنين','ثلاثاء','أربعاء','خميس','جمعة','سبت','أحد'][d.weekday()]})",
        key="bulk_att_days",
    )

    if selected_days:
        st.markdown(
            f"<div style='background:{COLORS['info']}18;border:1px solid {COLORS['info']}33;"
            f"border-radius:8px;padding:8px 16px;margin:8px 0;font-size:13px;"
            f"color:{COLORS['info']};font-weight:600;'>تم اختيار {len(selected_days)} يوم</div>",
            unsafe_allow_html=True,
        )

    save = st.button("حفظ كل الأيام المحددة", type="primary",
                      use_container_width=False, disabled=not selected_days,
                      key="bulk_att_save")

    if save:
        with st.spinner("جاري الحفظ..."):
            result = mark_attendance_bulk_dates(
                employee_id=employee_id,
                dates=selected_days,
                project_id=current_project_id,
                workers_count=float(workers_count),
                status=1,
            )
        if not result['success']:
            danger_toast(result['error'])
        else:
            success_toast(f"تم حفظ {result['saved']} يوم حضور لـ «{sel_emp.split(' — ', 1)[-1]}»")
            stat_pills([
                ("✅", "تم الحفظ",       str(result['saved']),               COLORS['success']),
                ("🔁", "مكرر (تجاهل)",  str(len(result['duplicate_dates'])), COLORS['warning']),
            ])
            if result['duplicate_dates']:
                dup_str = "، ".join(d.strftime('%d/%m/%Y') for d in result['duplicate_dates'])
                warning_toast(f"الأيام التالية كانت مسجلة بالفعل وتم تجاوزها: {dup_str}")


def _attendance_matrix():
    section_card("مصفوفة الحضور الشهرية", "🗂️", COLORS['secondary'])

    col1, col2, col3 = st.columns(3)
    month = col1.selectbox(
        "الشهر", list(range(1, 13)),
        index=date.today().month - 1,
        format_func=lambda m: MONTH_NAMES[m - 1]
    )
    year = col2.number_input("السنة", min_value=2020, max_value=2030, value=date.today().year)

    db = get_db()
    try:
        depts = ['الكل'] + sorted([
            d[0] for d in db.query(Employee.department)
            .filter(Employee.project_id == get_current_project_id())
            .distinct() if d[0]
        ])
    finally:
        db.close()

    dept = col3.selectbox("القسم", depts)
    dept_filter = None if dept == 'الكل' else dept

    st.markdown("<div style='margin-top:2px;'></div>", unsafe_allow_html=True)
    if st.button("عرض المصفوفة", type="primary"):
        with st.spinner("جاري تحميل المصفوفة..."):
            try:
                matrix = get_attendance_matrix(int(month), int(year), dept_filter, project_id=get_current_project_id())
            except Exception as e:
                danger_toast(f"خطأ في تحميل المصفوفة: {e}")
                return

        if matrix.empty:
            empty_state("لا توجد بيانات حضور لهذه الفترة", "📅",
                        "أدخل بيانات الحضور من تبويب «إدخال الحضور»")
            return

        day_cols      = [c for c in matrix.columns if c.isdigit()]
        # Days-present count (1 per day a row has any value > 0), independent
        # of headcount. Using the headcount sum here would push the
        # percentage past 100% whenever a day has more than 1 person.
        days_present   = (matrix[day_cols] > 0).sum().sum() if day_cols else 0
        total_headcount = matrix['إجمالي الحضور'].sum()
        total_possible = len(matrix) * len(day_cols)
        pct = (days_present / total_possible * 100) if total_possible else 0

        stat_pills([
            ("👥", "عدد الموظفين",       str(len(matrix)),     COLORS['primary']),
            ("📅", "أيام الشهر",         str(len(day_cols)),   COLORS['info']),
            ("📊", "نسبة الحضور الكلية", f"{pct:.1f}%",        COLORS['success'] if pct >= 80 else COLORS['warning']),
            ("✅", "إجمالي أيام الحضور", str(int(days_present)), COLORS['success']),
            ("🧮", "إجمالي عدد الأفراد", str(int(total_headcount)), COLORS['secondary']),
        ])

        st.markdown("<div style='margin-top:4px;'></div>", unsafe_allow_html=True)
        st.dataframe(matrix, use_container_width=True, hide_index=True, height=400)
        success_toast(f"مصفوفة {MONTH_NAMES[int(month)-1]} {int(year)} — {len(matrix)} موظف")


def _attendance_records():
    section_card("سجلات الحضور", "📋", COLORS['info'])

    col1, col2 = st.columns(2)
    start = col1.date_input("من تاريخ", value=date.today().replace(day=1))
    end   = col2.date_input("إلى تاريخ", value=date.today())

    if start > end:
        st.error("تاريخ البداية يجب أن يكون قبل تاريخ النهاية.")
        return

    st.markdown("<div style='margin-top:2px;'></div>", unsafe_allow_html=True)
    if st.button("بحث", type="primary"):
        db = get_db()
        try:
            records = db.query(Attendance).filter(
                Attendance.attendance_date >= start,
                Attendance.attendance_date <= end,
                Attendance.project_id == get_current_project_id(),
            ).order_by(Attendance.attendance_date.desc()).all()

            if not records:
                empty_state("لا توجد سجلات في هذه الفترة", "📅")
                return

            employees = {e.id: e for e in db.query(Employee).filter(
                Employee.project_id == get_current_project_id()
            ).all()}
            data = [{
                'اسم الموظف': employees[r.employee_id].name if r.employee_id in employees else 'غير معروف',
                'القسم':      employees[r.employee_id].department if r.employee_id in employees else '—',
                'التاريخ':    str(r.attendance_date),
                'الحالة':     'حاضر' if r.status == 1 else 'غائب',
                'عدد الأفراد': r.workers_count if r.workers_count is not None else 1,
            } for r in records]

            df      = pd.DataFrame(data)
            present = df[df['الحالة'].str.contains('حاضر')].shape[0]

            stat_pills([
                ("✅", "حاضر",    str(present),           COLORS['success']),
                ("❌", "غائب",    str(len(df) - present), COLORS['danger']),
                ("📋", "الإجمالي", str(len(df)),           COLORS['primary']),
            ])

            st.dataframe(df, use_container_width=True, hide_index=True)
        except Exception as e:
            danger_toast(f"خطأ في تحميل السجلات: {e}")
        finally:
            db.close()


# ── Edit / Delete a single record ─────────────────────────────────
# Mirrors the existing Overtime / Advances "تعديل / حذف" tab pattern
# (select a record from a dropdown → edit form with a delete option
# behind an explicit confirmation checkbox).

def _edit_delete_attendance():
    section_card("تعديل / حذف سجل حضور", "✏️", COLORS['danger'])

    current_project_id = get_current_project_id()

    db_r = get_db()
    try:
        records = db_r.query(Attendance).filter(
            Attendance.project_id == current_project_id
        ).order_by(Attendance.attendance_date.desc()).limit(100).all()
        employees = {e.id: e for e in db_r.query(Employee).filter(
            Employee.project_id == current_project_id
        ).all()}
        emp_list = db_r.query(Employee).filter(
            Employee.status == 'Active', Employee.project_id == current_project_id
        ).all()
        if not records:
            empty_state("لا توجد سجلات", "📅")
            return
        options = {
            f"{employees[r.employee_id].name if r.employee_id in employees else '—'} — "
            f"{r.attendance_date} — {r.workers_count if r.workers_count is not None else 1} عامل": r.id
            for r in records
        }
        rec_map = {
            r.id: {
                'emp_id': r.employee_id,
                'date':   r.attendance_date,
                'workers_count': float(r.workers_count) if r.workers_count is not None else 1.0,
                'status': r.status if r.status is not None else 1,
            }
            for r in records
        }
        emp_options = {f"{e.code} — {e.name}": e.id for e in emp_list}
    finally:
        db_r.close()

    selected = st.selectbox("اختر سجلاً", list(options.keys()), key="edit_att_select")
    rec_id   = options[selected]
    rv       = rec_map[rec_id]

    emp_names   = list(emp_options.keys())
    current_emp = next((k for k, v in emp_options.items() if v == rv['emp_id']), emp_names[0] if emp_names else "")

    with st.form("edit_att_form"):
        sel_emp = st.selectbox("الموظف", emp_names,
                                index=emp_names.index(current_emp) if current_emp in emp_names else 0)
        col1, col2 = st.columns(2)
        att_date      = col1.date_input("التاريخ", value=rv['date'])
        workers_count = col2.number_input("عدد العمال", value=rv['workers_count'], min_value=0.0, step=1.0)
        present       = st.checkbox("حاضر (إلغاء التحديد = غائب)", value=(rv['status'] == 1))

        confirm_del = st.checkbox("أؤكد حذف هذا السجل")
        cs, cd = st.columns(2)
        save   = cs.form_submit_button("تحديث", type="primary",   use_container_width=True)
        delete = cd.form_submit_button("حذف",  type="secondary", use_container_width=True)

        if save:
            if not emp_names:
                st.error("لا يوجد موظف محدد.")
            else:
                ok, msg = update_attendance_record(
                    record_id=rec_id,
                    project_id=current_project_id,
                    employee_id=emp_options[sel_emp],
                    attendance_date=att_date,
                    workers_count=workers_count,
                    status=1 if present else 0,
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
                ok, msg = delete_attendance_record(record_id=rec_id, project_id=current_project_id)
                if ok:
                    success_toast(msg)
                    st.rerun()
                else:
                    danger_toast(msg)


# ── Delete by day / month ──────────────────────────────────────────
# Both flows follow the same shape: 1) count-only query (never loads
# the actual rows into memory), 2) show the exact count + date +
# project scope to the user, 3) require an explicit confirmation
# checkbox, 4) only then run a single database-side DELETE inside a
# transaction (rollback on any exception). Always scoped to the
# CURRENTLY SELECTED project — never touches another project's rows.

def _delete_by_date_attendance():
    section_card("حذف الحضور حسب التاريخ", "🗑️", COLORS['danger'])
    info_banner(
        "يحذف هذا الإجراء سجلات <b>الحضور فقط</b>، ولمشروعك الحالي فقط. "
        "لن يتأثر أي مشروع آخر بهذا الحذف.",
        "⚠️", COLORS['danger']
    )

    current_project_id   = get_current_project_id()
    current_project_name = get_current_project_name()

    scope = st.radio("نطاق الحذف", ["حذف يوم كامل", "حذف شهر كامل"], horizontal=True, key="att_del_scope")

    if scope == "حذف يوم كامل":
        target_date = st.date_input("اختر اليوم المطلوب حذفه", value=date.today(), key="att_del_day")
        preview_count = count_attendance_for_day(target_date, current_project_id)

        if preview_count == 0:
            empty_state("لا توجد سجلات حضور في هذا التاريخ لهذا المشروع", "📅")
            return

        st.markdown(
            f"<div style=\"background:{COLORS['warning']}18;border:1px solid {COLORS['warning']}40;"
            f"border-radius:8px;padding:10px 16px;margin:12px 0;font-size:14px;font-weight:700;"
            f"color:{COLORS['warning']};\">"
            f"سيتم حذف {preview_count} سجل حضور ليوم {target_date.strftime('%d/%m/%Y')} "
            f"من مشروع {current_project_name}. هل أنت متأكد؟</div>",
            unsafe_allow_html=True,
        )

        confirm = st.checkbox(
            f"أؤكد حذف جميع سجلات الحضور ({preview_count}) ليوم "
            f"{target_date.strftime('%d/%m/%Y')} من مشروع {current_project_name} — لا يمكن التراجع.",
            key="att_del_day_confirm",
        )

        if st.button("حذف اليوم", type="primary", use_container_width=True,
                      disabled=not confirm, key="att_del_day_btn"):
            deleted, err = delete_attendance_for_day(target_date, current_project_id)
            if err:
                danger_toast(f"خطأ أثناء الحذف: {err}")
            else:
                success_toast(
                    f"تم حذف {deleted} سجل حضور ليوم {target_date.strftime('%d/%m/%Y')} "
                    f"من مشروع {current_project_name}."
                )
                st.rerun()

    else:  # حذف شهر كامل
        col1, col2 = st.columns(2)
        month = col1.selectbox(
            "الشهر", list(range(1, 13)),
            index=date.today().month - 1,
            format_func=lambda m: MONTH_NAMES[m - 1],
            key="att_del_month",
        )
        year = col2.number_input("السنة", min_value=2020, max_value=2030,
                                  value=date.today().year, key="att_del_year")

        preview_count = count_attendance_for_month(int(year), int(month), current_project_id)

        if preview_count == 0:
            empty_state("لا توجد سجلات حضور في هذا الشهر لهذا المشروع", "📅")
            return

        st.markdown(
            f"<div style=\"background:{COLORS['warning']}18;border:1px solid {COLORS['warning']}40;"
            f"border-radius:8px;padding:10px 16px;margin:12px 0;font-size:14px;font-weight:700;"
            f"color:{COLORS['warning']};\">"
            f"سيتم حذف {preview_count:,} سجل حضور لشهر {int(month):02d}/{int(year)} "
            f"من مشروع {current_project_name}.</div>",
            unsafe_allow_html=True,
        )

        confirm = st.checkbox(
            f"أؤكد حذف جميع سجلات الحضور ({preview_count:,}) لشهر "
            f"{int(month):02d}/{int(year)} من مشروع {current_project_name} — لا يمكن التراجع.",
            key="att_del_month_confirm",
        )

        if st.button("حذف الشهر", type="primary", use_container_width=True,
                      disabled=not confirm, key="att_del_month_btn"):
            deleted, err = delete_attendance_for_month(int(year), int(month), current_project_id)
            if err:
                danger_toast(f"خطأ أثناء الحذف: {err}")
            else:
                success_toast(
                    f"تم حذف {deleted:,} سجل حضور لشهر {int(month):02d}/{int(year)} "
                    f"من مشروع {current_project_name}."
                )
                st.rerun()
