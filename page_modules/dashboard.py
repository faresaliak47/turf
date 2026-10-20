import streamlit as st
import pandas as pd
from datetime import date, timedelta
from sqlalchemy import func
from database.db import get_db
from database.models import Employee, Attendance, Overtime, Advance
from components.cards import kpi_card, empty_state, stat_pills, section_card, card
from components.layout import render_topbar
from components.theme import COLORS, MONTH_NAMES
from components.charts import (attendance_trend_chart, department_donut_chart, payroll_bar_chart)
from services.payroll_service import calculate_payroll
from services.projects import get_current_project_id


@st.cache_data(ttl=20, show_spinner=False)
def _load_dashboard_kpis(current_project_id, today):
    """Cached read of the dashboard's KPI counters and chart data.
    Short TTL (20s, matching the payroll cache) keeps figures fresh after
    data entry while avoiding re-running 8+ separate queries on every
    single rerun — e.g. every sidebar click, tab switch, or widget
    interaction on this page previously re-fetched all of this from
    scratch even though nothing had changed."""
    db = get_db()
    try:
        total_emp    = db.query(Employee).filter(Employee.project_id == current_project_id).count()
        active_emp   = db.query(Employee).filter(
            Employee.status == 'Active', Employee.project_id == current_project_id
        ).count()
        inactive_emp = db.query(Employee).filter(
            Employee.status == 'Inactive', Employee.project_id == current_project_id
        ).count()
        present_today = db.query(Attendance).filter(
            Attendance.attendance_date == today, Attendance.status == 1,
            Attendance.project_id == current_project_id,
        ).count()

        # Aggregate in SQL (SUM) instead of pulling every row into Python —
        # same result, far less data transferred from the database.
        total_ot  = db.query(func.coalesce(func.sum(Overtime.amount), 0.0)).filter(
            Overtime.project_id == current_project_id
        ).scalar()
        total_ot_hours = db.query(func.coalesce(func.sum(Overtime.hours), 0.0)).filter(
            Overtime.project_id == current_project_id
        ).scalar()
        total_adv = db.query(func.coalesce(func.sum(Advance.amount), 0.0)).filter(
            Advance.project_id == current_project_id
        ).scalar()

        start_date = today - timedelta(days=29)
        trend_rows = db.query(
            Attendance.attendance_date, func.count(Attendance.id)
        ).filter(
            Attendance.attendance_date >= start_date,
            Attendance.attendance_date <= today,
            Attendance.status == 1,
            Attendance.project_id == current_project_id,
        ).group_by(Attendance.attendance_date).order_by(Attendance.attendance_date).all()

        dept_rows = db.query(
            func.coalesce(Employee.department, 'غير محدد'), func.count(Employee.id)
        ).filter(
            Employee.status == 'Active', Employee.project_id == current_project_id
        ).group_by(Employee.department).all()

        recent_att_rows = db.query(Attendance, Employee).join(
            Employee, Employee.id == Attendance.employee_id
        ).filter(
            Attendance.status == 1,
            Attendance.project_id == current_project_id,
        ).order_by(Attendance.attendance_date.desc()).limit(5).all()
        # Detach what the caller needs into plain values before the
        # session closes, so the cached result doesn't hold onto ORM
        # objects bound to a session that's about to be closed.
        recent_att = [
            (r.attendance_date, "".join([w[0] for w in emp.name.split()[:2]]), emp.name)
            for r, emp in recent_att_rows
        ]

        att_this_month = db.query(Attendance).filter(
            Attendance.attendance_date >= date(today.year, today.month, 1),
            Attendance.attendance_date <= today,
            Attendance.status == 1,
            Attendance.project_id == current_project_id,
        ).count()

        return {
            'total_emp': total_emp, 'active_emp': active_emp, 'inactive_emp': inactive_emp,
            'present_today': present_today, 'total_ot': total_ot, 'total_ot_hours': total_ot_hours,
            'total_adv': total_adv, 'trend_rows': trend_rows, 'dept_rows': dept_rows,
            'recent_att': recent_att, 'att_this_month': att_this_month,
        }
    finally:
        db.close()


def show():
    render_topbar("لوحة التحكم", "📊", "الرئيسية")

    try:
        current_project_id = get_current_project_id()
        today        = date.today()
        kpis = _load_dashboard_kpis(current_project_id, today)
        total_emp      = kpis['total_emp']
        active_emp     = kpis['active_emp']
        inactive_emp   = kpis['inactive_emp']
        present_today  = kpis['present_today']
        total_ot       = kpis['total_ot']
        total_ot_hours = kpis['total_ot_hours']
        total_adv      = kpis['total_adv']
        absent_today = max(active_emp - present_today, 0)

        try:
            pay_df    = calculate_payroll(today.month, today.year, current_project_id)
            total_net = pay_df['صافي الراتب'].sum() if not pay_df.empty else 0
        except Exception as e:
            print(f"[dashboard] Payroll calculation failed: {e}")
            pay_df    = pd.DataFrame()
            total_net = 0

        # ── KPI Row ──────────────────────────────────────────────────────
        c1, c2, c3, c4, c5 = st.columns(5)
        kpi_card(c1, "👥", "إجمالي الموظفين", total_emp,
                 COLORS['primary'], sub_label=f"{active_emp} نشط · {inactive_emp} غير نشط")
        kpi_card(c2, "✅", "حاضرون اليوم", present_today,
                 COLORS['success'], sub_label=f"من أصل {active_emp} نشط")
        kpi_card(c3, "❌", "غائبون اليوم", absent_today,
                 COLORS['danger'], sub_label="موظف غائب")
        kpi_card(c4, "⏱", "إجمالي الأوفر تايم", f"{total_ot:,.0f}",
                 COLORS['warning'], sub_label="جنيه مصري")
        kpi_card(c5, "🏦", "إجمالي السلف", f"{total_adv:,.0f}",
                 COLORS['accent'], sub_label="جنيه مصري")


        # ── Charts Row ───────────────────────────────────────────────────
        _cfg = {'displayModeBar': False}
        col_a, col_b = st.columns([3, 2])

        with col_a:
            with card("منحنى الحضور (30 يوماً)", "📈"):
                trend_rows = kpis['trend_rows']
                if trend_rows:
                    att_trend = pd.DataFrame(trend_rows, columns=['date', 'count'])
                    att_trend['date'] = pd.to_datetime(att_trend['date'])
                    st.plotly_chart(attendance_trend_chart(att_trend, height=260, show_title=False),
                                    use_container_width=True, config=_cfg)
                else:
                    empty_state("لا توجد بيانات حضور بعد", "📅",
                                "أدخل بيانات الحضور من قسم الحضور والغياب", flat=True)

        with col_b:
            with card("توزيع الموظفين بالأقسام", "🏢"):
                dept_rows = kpis['dept_rows']
                if dept_rows:
                    dept_count = pd.DataFrame(dept_rows, columns=['القسم', 'العدد'])
                    st.plotly_chart(department_donut_chart(dept_count, height=260, show_title=False),
                                    use_container_width=True, config=_cfg)
                else:
                    empty_state("لا توجد بيانات", "🏢", flat=True)

        # ── Bottom Row ───────────────────────────────────────────────────
        col_c, col_d = st.columns([3, 2])

        with col_c:
            with card("أعلى رواتب الشهر الحالي", "💼"):
                if not pay_df.empty:
                    st.plotly_chart(payroll_bar_chart(pay_df, height=290, show_title=False),
                                    use_container_width=True, config=_cfg)
                else:
                    st.info("احسب مسير الرواتب أولاً لعرض البيانات.")

        with col_d:
            with card("آخر نشاط", "🕐"):
                recent_att = kpis['recent_att']
                if recent_att:
                    rows_html = ""
                    last = len(recent_att) - 1
                    for i, (att_date, initials, emp_name) in enumerate(recent_att):
                        border = "" if i == last else f"border-bottom:1px solid {COLORS['border']};"
                        rows_html += f"""
<div style="display:flex;align-items:center;gap:12px;padding:9px 0;direction:rtl;{border}">
  <div style="background:{COLORS['primary_light']};border-radius:8px;width:32px;height:32px;
              display:flex;align-items:center;justify-content:center;
              font-size:13px;font-weight:600;color:{COLORS['primary']};flex-shrink:0;"><bdi>{initials}</bdi></div>
  <div style="flex:1;min-width:0;text-align:right;">
    <div style="font-size:13px;font-weight:600;color:{COLORS['text']};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"><bdi>{emp_name}</bdi></div>
    <div style="font-size:11.5px;color:{COLORS['text_muted']};margin-top:1px;">حضور · <bdi dir="ltr">{att_date}</bdi></div>
  </div>
</div>"""
                    st.markdown(rows_html, unsafe_allow_html=True)
                else:
                    empty_state("لا توجد سجلات حضور بعد", "🕐", hint="", flat=True)

        # ── Summary Stats Bar ─────────────────────────────────────────────
        att_this_month = kpis['att_this_month']

        stat_pills([
            ("👥", "إجمالي الموظفين",  str(total_emp),          COLORS['primary']),
            ("✅", "حضور هذا الشهر",   str(att_this_month),     COLORS['success']),
            ("⏱", "ساعات أوفر تايم",  f"{total_ot_hours:.0f}", COLORS['warning']),
            ("💰", "إجمالي السلف",      f"{total_adv:,.0f} ج.م", COLORS['accent']),
            ("💼", "صافي رواتب الشهر", f"{total_net:,.0f} ج.م", COLORS['secondary']),
        ])

    except Exception as e:
        st.error(f"خطأ في تحميل لوحة التحكم: {e}")
