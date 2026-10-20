"""Smart plant supplier delivery entry, catalog, and dated delivery ledger."""
from io import BytesIO
from datetime import date

import pandas as pd
import streamlit as st

from components.cards import section_card, success_toast, danger_toast, info_banner
from components.layout import render_topbar
from components.theme import COLORS
from services.plant_supplies import (
    add_supplier, list_catalog, list_delivery_rows, parse_delivery_text,
    preview_delivery, save_delivery,
)
from services.projects import get_current_project_id


_SAMPLE = """توريد يوم السبت
3/10/2026
من محمد مبروك

180 شفليرا
8 جهنميه ستاند
20 جهنميه جلابرا
30 ايكوفيليم
25 فرشه الزجاج
150 دورنتا صفراء
200 تيكوماريا
4 اريكا
100 هميرو برتقالي
250 كريسيا
300 ياسمين بلدي"""


def _reset_confirmation():
    st.session_state['plant_delivery_confirm_review'] = False


def show():
    render_topbar("توريدات الزرع", "🌿", "الموردون والمقاولون")
    st.caption("سجّل كل توريد بتاريخ ومورده وأصنافه، مع التعرف تلقائيًا على الموردين والأصناف المسجلة.")

    tab_entry, tab_ledger, tab_catalog = st.tabs([
        "الإدخال الذكي",
        "سجل التوريدات",
        "الموردون والأصناف",
    ])
    with tab_entry:
        _smart_entry()
    with tab_ledger:
        _ledger()
    with tab_catalog:
        _catalog()


def _smart_entry():
    section_card("إدخال توريد من رسالة واتساب", "🧠", COLORS['primary'])
    success_message = st.session_state.pop('_plant_delivery_success', None)
    if success_message:
        success_toast(success_message)
    info_banner(
        "الصق الرسالة كما وصلتك. المطلوب تاريخ التوريد، وسطر يبدأ بـ <b>من</b> لاسم المورد، "
        "ثم كل صنف في سطر: <b>الكمية ثم اسم الصنف</b>. ستراجع المورد والأصناف قبل الحفظ.",
        "💡", COLORS['primary'],
    )

    if st.session_state.pop('_plant_clear_input', False):
        st.session_state['plant_delivery_text'] = ''
        st.session_state['plant_delivery_confirm_review'] = False
    text = st.text_area(
        "نص رسالة التوريد",
        placeholder=_SAMPLE,
        height=270,
        key="plant_delivery_text",
        on_change=_reset_confirmation,
        help="التاريخ بصيغة يوم/شهر/سنة، مثل 03/10/2026.",
    )
    if not text.strip():
        return

    parsed = parse_delivery_text(text)
    parsed['source_text'] = text.strip()
    if parsed['errors']:
        for error in parsed['errors']:
            st.warning(error)

    can_preview = bool(parsed['date'] and parsed['supplier'] and parsed['items'])
    if not can_preview:
        return

    project_id = get_current_project_id()
    preview = preview_delivery(parsed, project_id)
    st.markdown("#### مراجعة التوريد")
    supplier_state = "مورد مسجل — سيُضاف التوريد إلى سجله" if preview['supplier_existing'] else "مورد جديد — سيُسجل لأول مرة"
    st.info(f"**المورد:** {preview['supplier_catalog_name']}  ·  {supplier_state}  ·  **التاريخ:** {parsed['date'].strftime('%d/%m/%Y')}")

    rows = [{
        'الصنف في الرسالة': row['name'],
        'الكمية': row['quantity'],
        'حالة الصنف': 'مسجل — سيضاف للتوريد بهذا التاريخ' if row['existing'] else 'صنف جديد — سيضاف للكتالوج',
    } for row in preview['items']]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    total_quantity = sum(row['quantity'] for row in preview['items'])
    st.caption(f"عدد الأصناف: {len(rows)}  ·  إجمالي الكميات: {total_quantity:g}")

    if parsed['errors']:
        st.error("صحح الأسطر الموضحة بالأعلى قبل تسجيل التوريد.")
        return

    confirm = st.checkbox(
        "راجعت المورد والتاريخ والكميات وأؤكد تسجيل التوريد",
        key="plant_delivery_confirm_review",
    )
    if st.button(
        "تأكيد وحفظ التوريد",
        type="primary",
        disabled=not confirm,
        key="plant_delivery_save",
        use_container_width=True,
    ):
        try:
            delivery_id = save_delivery(parsed, project_id)
            st.session_state['_plant_clear_input'] = True
            st.session_state['_plant_delivery_success'] = (
                f"تم تسجيل التوريد رقم {delivery_id} وإضافة {len(rows)} صنف بتاريخ "
                f"{parsed['date'].strftime('%d/%m/%Y')}."
            )
            st.rerun()
        except Exception as exc:
            danger_toast(f"تعذر حفظ التوريد: {exc}")


def _ledger():
    section_card("سجل توريدات الزرع", "📦", COLORS['info'])
    col_from, col_to = st.columns(2)
    start = col_from.date_input("من تاريخ", value=date.today().replace(day=1), key="plant_delivery_from")
    end = col_to.date_input("إلى تاريخ", value=date.today(), key="plant_delivery_to")
    if start > end:
        st.warning("تاريخ البداية يجب أن يكون قبل تاريخ النهاية.")
        return
    rows = list_delivery_rows(get_current_project_id(), start, end)
    if not rows:
        st.info("لا توجد توريدات في الفترة المحددة.")
        return
    frame = pd.DataFrame([{
        'التاريخ': row['date'].strftime('%d/%m/%Y'),
        'المورد': row['supplier'],
        'الصنف': row['item'],
        'الكمية': row['quantity'],
        'ملاحظات': row['notes'],
        'رقم التوريد': row['delivery_id'],
    } for row in rows])
    st.dataframe(frame, use_container_width=True, hide_index=True)
    st.caption(f"عدد تفاصيل الأصناف المعروضة: {len(frame)}")


def _catalog():
    section_card("دليل الموردين والأصناف", "🌱", COLORS['success'])
    st.caption("إجمالي الوارد هو مجموع كميات التوريدات المسجلة لكل صنف، وليس رصيدًا بعد خصم الاستخدام.")
    suppliers, items = list_catalog(get_current_project_id())
    left, right = st.columns(2)
    with left:
        st.markdown("#### الموردون")
        with st.form("plant_supplier_add_form", clear_on_submit=True):
            supplier_name = st.text_input("اسم المورد", placeholder="اكتب اسم المورد")
            add_clicked = st.form_submit_button("إضافة مورد", type="primary", use_container_width=True)
        if add_clicked:
            try:
                added, message = add_supplier(supplier_name, get_current_project_id())
                if added:
                    st.success(message)
                    st.rerun()
                else:
                    st.warning(message)
            except Exception as exc:
                st.error(f"تعذرت إضافة المورد: {exc}")
        if suppliers:
            supplier_frame = pd.DataFrame(suppliers)
            st.dataframe(supplier_frame, use_container_width=True, hide_index=True)
            output = BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                supplier_frame.to_excel(writer, sheet_name="الموردون", index=False)
            st.download_button(
                "تصدير قائمة الموردين إلى Excel",
                data=output.getvalue(),
                file_name="قائمة_الموردين.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="plant_suppliers_excel_export",
                use_container_width=True,
            )
        else:
            st.info("لا توجد موردون مسجلون في هذا المشروع بعد.")
    with right:
        st.markdown("#### الأصناف")
        if items:
            st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)
        else:
            st.info("ستظهر الأصناف هنا تلقائيًا بعد حفظ أول توريد.")
