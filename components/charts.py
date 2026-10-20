"""Chart helpers — consistent Plotly figures for TURF HR Pro (RTL-aware)."""

import plotly.express as px
import plotly.graph_objects as go
from components.theme import COLORS

FONT = 'Cairo, Inter, Segoe UI, Tahoma, sans-serif'

# Chart series palette: primary + its tints + neutral grays (no extra hues).
CHART_SERIES = [COLORS['primary'], "#8B85FF", "#B4B0FF", "#D6D4FF",
                COLORS['secondary'], "#B8BCC4", "#DDE0E6"]


def _base(**kw):
    """Shared layout. Callers override any key via kwargs (no duplicate-kwarg errors)."""
    layout = dict(
        font=dict(family=FONT, size=12, color=COLORS['text']),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=8, r=8, t=8, b=8),
        hoverlabel=dict(font=dict(family=FONT, size=12), align='right'),
        legend=dict(font=dict(family=FONT, size=12)),
    )
    layout.update(kw)
    return {k: v for k, v in layout.items() if v is not None}


CHART_LAYOUT = _base()  # kept for any external import


def _title(text):
    """Right-aligned title (RTL). Dashboard cards already have a header, so they pass show_title=False."""
    return dict(text=text, x=1, xanchor='right', y=0.97,
                font=dict(size=14, family=FONT, color=COLORS['text']))


def _top(show_title):
    return 40 if show_title else 8


def attendance_trend_chart(df, height=205, show_title=True):
    fig = go.Figure(go.Scatter(
        x=df['date'],
        y=df['count'],
        mode='lines',
        line=dict(color=COLORS['primary'], width=2.5, shape='spline'),
        fill='tozeroy',
        fillcolor="rgba(99,91,255,0.10)",
        name='الحضور',
        hovertemplate='<b>%{x|%d/%m/%Y}</b><br>حضور: %{y}<extra></extra>',
    ))
    ymax = int(df['count'].max()) if len(df) else 1
    dtick = max(1, -(-ymax // 4))  # whole-number ticks only (no "2.5 employees")
    fig.update_layout(**_base(
        height=height,
        showlegend=False,
        margin=dict(l=8, r=44, t=_top(show_title), b=8),
        title=_title('اتجاه الحضور — آخر 30 يوم') if show_title else None,
        xaxis=dict(showgrid=False, tickformat='%d/%m', automargin=True),
        yaxis=dict(side='right', showgrid=True, gridcolor=COLORS['border'],
                   rangemode='tozero', dtick=dtick, tickformat='d',
                   zeroline=False, automargin=False),
    ))
    return fig


def department_donut_chart(dept_df, height=205, show_title=True):
    palette = [COLORS['primary'], "#B4B0FF", COLORS['secondary'], "#8B85FF",
               "#DDE0E6", "#D6D4FF", "#B8BCC4"]
    total = int(dept_df['العدد'].sum())

    fig = px.pie(dept_df, names='القسم', values='العدد',
                 color_discrete_sequence=palette, hole=0.62)
    fig.update_traces(
        sort=False,
        textinfo='percent',
        textposition='auto',
        insidetextorientation='horizontal',
        textfont=dict(family=FONT, size=12),
        marker=dict(line=dict(color='#ffffff', width=2)),
        domain=dict(x=[0, 0.62]),  # donut on the left, legend on the right (RTL reading side)
        hovertemplate='<b>%{label}</b><br>%{value} موظف (%{percent})<extra></extra>',
    )
    fig.update_layout(**_base(
        height=height,
        margin=dict(l=8, r=8, t=(40 if show_title else 28), b=28),
        title=_title('توزيع الموظفين على الأقسام') if show_title else None,
        legend=dict(orientation='v', x=0.68, xanchor='left', y=0.5, yanchor='middle',
                    font=dict(family=FONT, size=12)),
        annotations=[dict(text=f'<b>{total}</b><br>موظف', x=0.31, y=0.5,
                          showarrow=False,
                          font=dict(family=FONT, size=15, color=COLORS['text']))],
    ))
    return fig


def payroll_bar_chart(df, height=205, show_title=True):
    top = df.nlargest(8, 'صافي الراتب')
    names = top['اسم الموظف'].astype(str).map(lambda s: s if len(s) <= 20 else s[:19] + '…')
    vmax = float(top['صافي الراتب'].max()) if len(top) else 1.0

    fig = go.Figure(go.Bar(
        x=top['صافي الراتب'],
        y=names,
        orientation='h',
        marker=dict(
            color=top['صافي الراتب'],
            colorscale=[[0, "rgba(99,91,255,0.25)"], [1, "rgba(99,91,255,1)"]],
            line=dict(width=0),
        ),
        customdata=top['اسم الموظف'],
        hovertemplate='<b>%{customdata}</b><br>%{x:,.0f} ج.م<extra></extra>',
        text=top['صافي الراتب'].apply(lambda x: f"{x:,.0f}"),
        textposition='outside',
        cliponaxis=False,
        textfont=dict(family=FONT, color=COLORS['text'], size=11),
    ))
    fig.update_layout(**_base(
        height=height,
        margin=dict(l=150, r=16, t=_top(show_title), b=8),
        title=_title('أعلى الرواتب') if show_title else None,
        xaxis=dict(showgrid=True, gridcolor=COLORS['border'], tickformat=',.0f',
                   range=[0, vmax * 1.2], nticks=5, zeroline=False),
        # automargin = the axis grows to fit the full employee names (they used to be clipped to one letter)
        yaxis=dict(showgrid=False, autorange='reversed', automargin=False, ticklabelstandoff=8),
    ))
    return fig


def salary_distribution_chart(df, height=250):
    fig = px.histogram(df, x='صافي الراتب', nbins=10,
                       color_discrete_sequence=[COLORS['primary_light']])
    fig.update_traces(
        marker_line_color=COLORS['primary'],
        marker_line_width=1.5,
        hovertemplate='%{x:,.0f} ج.م: %{y} موظف<extra></extra>',
    )
    fig.update_layout(**_base(
        height=height,
        margin=dict(l=8, r=8, t=40, b=8),
        title=_title('توزيع الرواتب'),
        xaxis=dict(title='الراتب', automargin=True),
        yaxis=dict(title='عدد الموظفين', side='right', automargin=True,
                   gridcolor=COLORS['border']),
    ))
    return fig


def dept_cost_chart(df, height=250):
    dept_cost = df.groupby('القسم')['صافي الراتب'].sum().reset_index()
    dept_cost.columns = ['القسم', 'الإجمالي']
    dept_cost = dept_cost.sort_values('الإجمالي', ascending=False)

    fig = px.bar(dept_cost, x='القسم', y='الإجمالي', color='الإجمالي',
                 color_continuous_scale=[[0, "rgba(99,91,255,0.2)"], [1, "rgba(99,91,255,1)"]],
                 text='الإجمالي')
    fig.update_traces(
        texttemplate='%{text:,.0f}',
        textposition='outside',
        cliponaxis=False,
        textfont=dict(family=FONT, size=11),
        marker_line_width=0,
    )
    fig.update_layout(**_base(
        height=height,
        margin=dict(l=8, r=8, t=40, b=8),
        title=_title('تكلفة الرواتب بالأقسام'),
        coloraxis_showscale=False,
        xaxis=dict(title='', automargin=True),
        yaxis=dict(title='المبلغ (ج.م)', side='right', automargin=True,
                   gridcolor=COLORS['border']),
    ))
    return fig
