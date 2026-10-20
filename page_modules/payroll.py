import streamlit as st
import pandas as pd
from datetime import date
from services.payroll_service import calculate_payroll
from services.projects import get_current_project_id
from services.name_matching import normalize_arabic_name
from components.cards import section_card, empty_state, kpi_card, stat_pills, info_banner
from components.layout import render_topbar
from components.theme import COLORS, MONTH_NAMES
from components.charts import payroll_bar_chart, salary_distribution_chart, dept_cost_chart


def show():
    render_topbar("مسير الرواتب", "💼", "مسير الرواتب")

    current_project_id = get_current_project_id()

    # ── Period selector ──────────────────────────────────────────────────
    section_card("اختر فترة الراتب", "📅", COLORS['primary'])

    col1, col2, col3 = st.columns([2, 2, 1])
    month = col1.selectbox(
        "الشهر", list(range(1, 13)),
        index=date.today().month - 1,
        format_func=lambda m: MONTH_NAMES[m - 1]
    )
    year  = col2.number_input("السنة", min_value=2020, max_value=2030, value=date.today().year)
    with col3:
        st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
        calc = st.button("احتساب", type="primary", use_container_width=True)

    if calc:
        with st.spinner("جاري احتساب الرواتب..."):
            try:
                df = calculate_payroll(int(month), int(year), current_project_id)
            except Exception as e:
                st.error(f"خطأ في احتساب الرواتب: {e}")
                return
        if df.empty:
            empty_state("لا توجد بيانات لهذه الفترة", "💼",
                        "تأكد من إدخال بيانات الحضور والموظفين")
            return
        st.session_state['payroll_df']         = df
        st.session_state['payroll_month']       = month
        st.session_state['payroll_year']        = year
        st.session_state['payroll_project_id']  = current_project_id

    # A payroll table calculated for a different project must never be
    # shown after switching — treat it the same as "nothing calculated yet".
    if ('payroll_df' not in st.session_state
            or st.session_state.get('payroll_project_id') != current_project_id):
        info_banner("اختر الشهر والسنة ثم اضغط «احتساب» لعرض مسير الرواتب.", "💼", COLORS['primary'])
        return

    df = st.session_state['payroll_df']
    m  = st.session_state.get('payroll_month', month)
    y  = st.session_state.get('payroll_year',  year)


    # ── KPI Row ───────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    kpi_card(c1, "👥", "عدد الموظفين", f"{len(df)}", COLORS['primary'])
    kpi_card(c2, "💰", "إجمالي الرواتب", f"{df['الراتب الأساسي'].sum():,.0f}", COLORS['success'])
    kpi_card(c3, "⏱️", "إجمالي الأوفر تايم", f"{df['الأوفر تايم'].sum():,.0f}", COLORS['warning'])
    kpi_card(c4, "➖", "إجمالي الخصومات", f"{df['الخصومات'].sum():,.0f}", COLORS['danger'])
    kpi_card(c5, "💼", "صافي الرواتب", f"{df['صافي الراتب'].sum():,.0f}", COLORS['secondary'])

    st.markdown("<div style='margin-top:6px;'></div>", unsafe_allow_html=True)

    # ── Tabs: Table | Charts ─────────────────────────────────────────────
    pt1, pt2 = st.tabs(["كشف الرواتب", "تحليل الرواتب"])

    with pt1:
        section_card(f"كشف رواتب {MONTH_NAMES[int(m)-1]} {int(y)}", "📊", COLORS['primary'])
        sc1, sc2 = st.columns([2, 2])
        depts       = ['الكل'] + sorted(df['القسم'].dropna().unique().tolist())
        dept_filter = sc1.selectbox("تصفية بالقسم", depts)
        search_pay  = sc2.text_input("بحث باسم الموظف", placeholder="اكتب اسم الموظف...")
        display_df  = df if dept_filter == 'الكل' else df[df['القسم'] == dept_filter].copy()
        if search_pay:
            norm_query = normalize_arabic_name(search_pay)
            display_df = display_df[
                display_df['اسم الموظف'].apply(lambda n: norm_query in normalize_arabic_name(n))
            ]

        # Totals row
        totals = {col: '' for col in display_df.columns}
        totals['اسم الموظف'] = 'الإجمالي'
        for num_col in ['أيام الحضور', 'الراتب الأساسي', 'الأوفر تايم', 'السلف', 'الخصومات', 'صافي الراتب']:
            totals[num_col] = display_df[num_col].sum()
        # 'المعدل اليومي' is numeric in every real row; leaving it as ''
        # here mixes str + float in one column, which pyarrow refuses to
        # serialize (ArrowInvalid) when st.dataframe renders the table.
        totals['المعدل اليومي'] = float('nan')
        display_full = pd.concat([display_df, pd.DataFrame([totals])], ignore_index=True)

        st.dataframe(display_full, use_container_width=True, hide_index=True, height=420)

        with st.expander("تفاصيل الأعلى والأدنى راتباً"):
            top    = display_df.nlargest(3,  'صافي الراتب')[['اسم الموظف', 'القسم', 'صافي الراتب']]
            bottom = display_df.nsmallest(3, 'صافي الراتب')[['اسم الموظف', 'القسم', 'صافي الراتب']]
            cl, cr = st.columns(2)
            cl.markdown("**الأعلى راتباً**")
            cl.dataframe(top,    hide_index=True, use_container_width=True)
            cr.markdown("**الأدنى راتباً**")
            cr.dataframe(bottom, hide_index=True, use_container_width=True)

    with pt2:
        col_a, col_b = st.columns(2)
        with col_a:
            st.plotly_chart(payroll_bar_chart(df, height=300),
                            use_container_width=True, config={'displayModeBar': False})
        with col_b:
            st.plotly_chart(salary_distribution_chart(df, height=300),
                            use_container_width=True, config={'displayModeBar': False})

        st.plotly_chart(dept_cost_chart(df, height=270),
                        use_container_width=True, config={'displayModeBar': False})

        avg_sal = df['صافي الراتب'].mean()
        max_sal = df['صافي الراتب'].max()
        min_sal = df['صافي الراتب'].min()
        stat_pills([
            ("📊", "متوسط الراتب",    f"{avg_sal:,.0f} ج.م", COLORS['primary']),
            ("🏆", "أعلى راتب",        f"{max_sal:,.0f} ج.م", COLORS['success']),
            ("📉", "أدنى راتب",        f"{min_sal:,.0f} ج.م", COLORS['warning']),
            ("🏦", "إجمالي السلف",     f"{df['السلف'].sum():,.0f} ج.م", COLORS['accent']),
            ("➖", "إجمالي الخصومات", f"{df['الخصومات'].sum():,.0f} ج.م", COLORS['danger']),
        ])
