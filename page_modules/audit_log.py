"""Admin view and Excel export for the append-only user activity history."""
from io import BytesIO
import json
import pandas as pd
import streamlit as st

from database.db import get_db
from database.models import AuditLog
from components.layout import render_topbar


def show():
    render_topbar("سجل التغييرات", "🧾", "سجل التغييرات")
    st.caption("يسجل هذا القسم عمليات الإضافة والتعديل والحذف التي ينفذها المستخدمون من داخل التطبيق.")
    db = get_db()
    try:
        rows = db.query(AuditLog).order_by(AuditLog.occurred_at.desc()).limit(5000).all()
        data = [{
            "التاريخ والوقت (UTC)": row.occurred_at,
            "المستخدم": row.username,
            "العملية": row.action,
            "القسم": row.table_name,
            "رقم السجل": row.record_id,
            "التفاصيل": json.dumps(json.loads(row.changes_json or "{}"), ensure_ascii=False),
        } for row in rows]
    finally:
        db.close()

    if not data:
        st.info("لا توجد تغييرات مسجلة بعد. ستظهر التغييرات الجديدة هنا.")
        return
    df = pd.DataFrame(data)
    c1, c2 = st.columns(2)
    users = ["الكل"] + sorted(df["المستخدم"].dropna().unique().tolist())
    actions = ["الكل"] + sorted(df["العملية"].dropna().unique().tolist())
    with c1:
        selected_user = st.selectbox("المستخدم", users)
    with c2:
        selected_action = st.selectbox("العملية", actions)
    if selected_user != "الكل":
        df = df[df["المستخدم"] == selected_user]
    if selected_action != "الكل":
        df = df[df["العملية"] == selected_action]
    st.download_button(
        "⬇️ تصدير سجل التغييرات Excel",
        data=_to_excel(df),
        file_name="TURF_HR_Audit_Log.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    st.dataframe(df, use_container_width=True, hide_index=True)


def _to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="سجل التغييرات")
        ws = writer.sheets["سجل التغييرات"]
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for column in ws.columns:
            letter = column[0].column_letter
            ws.column_dimensions[letter].width = min(max(max(len(str(c.value or "")) for c in column) + 2, 14), 55)
    return output.getvalue()
