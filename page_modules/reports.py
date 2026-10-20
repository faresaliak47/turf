import os
import streamlit as st
from datetime import date
from services.excel_export import save_full_report
from services.excel_import import validate_file, build_preview, import_report, IMPORTABLE_SHEETS
from components.cards import section_card, info_banner, success_toast, danger_toast, stat_pills
from components.layout import render_topbar
from components.icons import render_icon
from components.theme import COLORS, MONTH_NAMES
from services.projects import get_current_project_id


# ── Shared CSS injected once per page load ──────────────────────────────────
_IMPORT_CSS = """
<style>
.imp-mode-card {
    border:2px solid transparent;
    border-radius:12px;
    padding:16px 18px;
    cursor:pointer;
    transition:all .2s;
    background:var(--surface,#1e2a38);
    margin-bottom:8px;
}
.imp-mode-card.active {
    border-color:#635BFF;
    background:rgba(99,91,255,.12);
}
.imp-sheet-pill {
    display:inline-flex;align-items:center;gap:6px;
    padding:5px 12px;border-radius:20px;font-size:12px;font-weight:600;
    margin:3px;
}
.imp-preview-table {overflow-x:auto;border-radius:8px;}
.imp-preview-table table {font-size:11px;width:100%;border-collapse:collapse;}
.imp-preview-table th {
    background:#635BFF;color:#fff;padding:6px 10px;
    text-align:center;font-weight:600;
}
.imp-preview-table td {
    padding:5px 10px;border-bottom:1px solid rgba(255,255,255,.06);
    text-align:center;
}
.imp-result-row {
    display:flex;align-items:center;gap:8px;
    padding:8px 12px;border-radius:8px;margin-bottom:6px;
    font-size:13px;
}
.imp-result-ok  { background:rgba(99,91,255,.15);border:1px solid rgba(99,91,255,.3); }
.imp-result-warn{ background:rgba(255,153,0,.12); border:1px solid rgba(255,153,0,.3); }
.imp-result-err { background:rgba(220,53,69,.12); border:1px solid rgba(220,53,69,.3); }
@media(max-width:768px){
    .imp-preview-table td,.imp-preview-table th{padding:4px 6px;font-size:10px;}
}
</style>
"""

SHEET_ICONS = {
    'الموظفون':      ('👥', COLORS['primary']),
    'سجلات الحضور': ('📅', COLORS['info']),
    'الأوفر تايم':  ('⏱', COLORS['warning']),
    'السلف':         ('💰', COLORS['danger']),
    'مسير الرواتب': ('💼', COLORS['secondary']),
    'مصفوفة الحضور':('📊', COLORS['success']),
}


def show():
    render_topbar("التقارير والتصدير", "📈", "التقارير")
    st.markdown(_IMPORT_CSS, unsafe_allow_html=True)

    # ── Two tab areas: Export | Import ──────────────────────────────────────
    tab_export, tab_import = st.tabs(["تصدير تقرير", "استيراد تقرير"])

    # ════════════════════════════════════════════════════════════
    # TAB 1: Export (unchanged)
    # ════════════════════════════════════════════════════════════
    with tab_export:
        _show_export_tab()

    # ════════════════════════════════════════════════════════════
    # TAB 2: Import
    # ════════════════════════════════════════════════════════════
    with tab_import:
        _show_import_tab()


# ── Export (original code, untouched) ───────────────────────────────────────

def _show_export_tab():
    section_card("تصدير تقرير شامل", "📥", COLORS['primary'])

    col1, col2, col3 = st.columns([2, 2, 1])
    month = col1.selectbox(
        "الشهر", list(range(1, 13)),
        index=date.today().month - 1,
        format_func=lambda m: MONTH_NAMES[m - 1]
    )
    year  = col2.number_input("السنة", min_value=2020, max_value=2030, value=date.today().year)

    section_card("محتويات ملف Excel", "📋", COLORS['info'])
    sheets = [
        ("1️⃣", "الموظفون",        "بيانات جميع الموظفين",             COLORS['primary']),
        ("2️⃣", "سجلات الحضور",   "تفاصيل حضور وغياب الشهر",         COLORS['info']),
        ("3️⃣", "مصفوفة الحضور",  "جدول يومي لكل موظف",              COLORS['secondary']),
        ("4️⃣", "الأوفر تايم",    "ساعات وقيم الوقت الإضافي",        COLORS['warning']),
        ("5️⃣", "السلف",           "سجلات السلف المدفوعة",             COLORS['danger']),
        ("6️⃣", "مسير الرواتب",   "ملخص رواتب مع إجماليات وخصومات",  COLORS['success']),
    ]
    r1, r2 = st.columns(2)
    for i, (num, name, desc, color) in enumerate(sheets):
        col = r1 if i % 2 == 0 else r2
        col.markdown(f"""
<div style="background:{color}08;border-radius:10px;padding:12px 16px;
            border:1px solid {color}22;border-right:3px solid {color};margin-bottom:8px;">
  <div style="font-weight:700;color:{COLORS['text']};font-size:13px;">{num} {name}</div>
  <div style="font-size:11px;color:{COLORS['text_muted']};margin-top:2px;">{desc}</div>
</div>
""", unsafe_allow_html=True)

    with col3:
        st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
        generate = st.button("إنشاء", type="primary", use_container_width=True)

    if generate:
        with st.spinner("جاري إنشاء التقرير الشامل..."):
            try:
                data, saved_path = save_full_report(int(month), int(year), get_current_project_id())
                filename = os.path.basename(saved_path)

                st.success(
                    f"تم إنشاء التقرير وحفظه بنجاح! — {MONTH_NAMES[int(month)-1]} {int(year)}\n\n"
                    f"اسم الملف: **{filename}**\n\n"
                    f"تم الحفظ في: `{saved_path}`"
                )

                st.download_button(
                    label=f"تحميل {filename}",
                    data=data,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    type="primary"
                )

                stat_pills([
                    ("📊", "الأوراق المُصدَّرة", "6",                                        COLORS['primary']),
                    ("📅", "الفترة",              f"{MONTH_NAMES[int(month)-1]} {int(year)}", COLORS['info']),
                ])

            except Exception as e:
                danger_toast(f"خطأ في إنشاء التقرير: {e}")


# ── Import ───────────────────────────────────────────────────────────────────

def _show_import_tab():
    section_card("استيراد تقرير سابق", "📤", COLORS['info'])

    # Info banner
    st.markdown(f"""
<div style="background:rgba(13,110,253,.08);border:1px solid rgba(13,110,253,.25);
            border-radius:10px;padding:14px 18px;margin-bottom:18px;">
  <div style="font-size:13px;font-weight:700;color:{COLORS['text']};margin-bottom:6px;">
    كيف يعمل الاستيراد؟
  </div>
  <div style="font-size:12px;color:{COLORS['text_muted']};line-height:1.8;">
    • ارفع ملف Excel تم تصديره مسبقاً من هذا النظام<br/>
    • سيتم التحقق من البنية تلقائياً قبل الاستيراد<br/>
    • اختر وضع الدمج (الاحتفاظ بالبيانات الموجودة) أو الاستبدال (مسح وإعادة بناء)<br/>
    • ستعمل جميع التقارير ولوحات التحكم بشكل طبيعي بعد الاستيراد
  </div>
</div>
""", unsafe_allow_html=True)

    # ── File uploader ─────────────────────────────────────────────────────
    uploaded = st.file_uploader(
        "اختر ملف Excel (.xlsx)",
        type=["xlsx"],
        help="يجب أن يكون الملف مُصدَّراً من هذا النظام",
        key="import_file_uploader",
    )

    if not uploaded:
        st.markdown(f"""
<div style="border:2px dashed {COLORS['primary']}44;border-radius:14px;
            padding:40px;text-align:center;margin-top:8px;">
  <div style="margin-bottom:10px;color:{COLORS['text_muted']};display:flex;justify-content:center;">{render_icon('📥', size=40)}</div>
  <div style="font-size:15px;font-weight:600;color:{COLORS['text']};">
    اسحب وأفلت ملف Excel هنا
  </div>
  <div style="font-size:12px;color:{COLORS['text_muted']};margin-top:6px;">
    أو اضغط على زر الرفع أعلاه · يقبل ملفات .xlsx فقط
  </div>
</div>
""", unsafe_allow_html=True)
        return

    file_bytes = uploaded.read()

    # ── Validate ──────────────────────────────────────────────────────────
    with st.spinner("جاري التحقق من الملف..."):
        is_valid, msg, sheets = validate_file(file_bytes)

    if not is_valid:
        st.error(f"{msg}")
        return

    st.success(f"{msg}")

    # ── Detected sheets pills ─────────────────────────────────────────────
    st.markdown("<div style='margin:10px 0 4px;font-size:13px;font-weight:600;'>الأوراق المكتشفة:</div>",
                unsafe_allow_html=True)
    pills_html = ""
    for name in sheets:
        icon, color = SHEET_ICONS.get(name, ("📄", COLORS["text_muted"]))
        pills_html += (
            f'<span class="imp-sheet-pill" style="background:{color}22;'
            f'color:{color};border:1px solid {color}44;">'
            f'{render_icon(icon, size=14)} {name} · {len(sheets[name].dropna(how="all"))} صف'
            f'</span>'
        )
    st.markdown(f"<div style='margin-bottom:14px;'>{pills_html}</div>",
                unsafe_allow_html=True)

    # ── Preview ───────────────────────────────────────────────────────────
    with st.expander("معاينة البيانات", expanded=False):
        preview = build_preview(sheets)
        for sheet_name, info in preview.items():
            icon, color = SHEET_ICONS.get(sheet_name, ("📄", COLORS["text_muted"]))
            st.markdown(
                f"<div style='font-weight:700;font-size:13px;color:{color};"
                f"margin:12px 0 6px;display:flex;align-items:center;gap:6px;'>{render_icon(icon, size=15)} {sheet_name} — {info['count']} سجل</div>",
                unsafe_allow_html=True
            )
            if not info['sample'].empty:
                st.dataframe(
                    info['sample'],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("لا توجد بيانات في هذه الورقة.")

    st.markdown("<hr style='margin:20px 0;opacity:.15;'/>", unsafe_allow_html=True)

    # ── Mode selection ────────────────────────────────────────────────────
    section_card("وضع الاستيراد", "⚙️", COLORS['warning'])

    mode_col1, mode_col2 = st.columns(2)
    with mode_col1:
        st.markdown(f"""
<div style="background:rgba(99,91,255,.08);border:2px solid rgba(99,91,255,.35);
            border-radius:12px;padding:16px 18px;">
  <div style="font-size:15px;font-weight:800;color:{COLORS['primary']};">دمج مع البيانات الموجودة</div>
  <div style="font-size:12px;color:{COLORS['text_muted']};margin-top:8px;line-height:1.7;">
    • الاحتفاظ بجميع البيانات الحالية<br/>
    • إضافة السجلات الجديدة فقط<br/>
    • تخطي السجلات المكررة تلقائياً<br/>
    • الأكثر أماناً · موصى به
  </div>
</div>
""", unsafe_allow_html=True)

    with mode_col2:
        st.markdown(f"""
<div style="background:rgba(220,53,69,.06);border:2px solid rgba(220,53,69,.25);
            border-radius:12px;padding:16px 18px;">
  <div style="font-size:15px;font-weight:800;color:{COLORS['danger']};">استبدال البيانات الموجودة</div>
  <div style="font-size:12px;color:{COLORS['text_muted']};margin-top:8px;line-height:1.7;">
    • حذف البيانات الحالية أولاً<br/>
    • استعادة كاملة من الملف<br/>
    • مناسب بعد إعادة النشر الكامل<br/>
    • لا يمكن التراجع عن هذا الوضع
  </div>
</div>
""", unsafe_allow_html=True)

    mode = st.radio(
        "اختر وضع الاستيراد",
        options=["دمج مع البيانات الموجودة", "استبدال البيانات الموجودة"],
        horizontal=True,
        key="import_mode_radio",
    )
    import_mode = "merge" if mode.startswith("دمج") else "replace"

    # Warning for replace mode
    if import_mode == "replace":
        st.warning(
            "**تحذير:** وضع الاستبدال سيحذف جميع البيانات الحالية "
            "(الموظفين، الحضور، الأوفر تايم، السلف) قبل الاستيراد. "
            "هذا الإجراء **لا يمكن التراجع عنه**."
        )

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    # ── Confirm + Import button ────────────────────────────────────────────
    confirm_col, btn_col = st.columns([3, 1])
    with confirm_col:
        confirmed = st.checkbox(
            "أؤكد أنني أرغب في استيراد البيانات ومراجعت وضع الاستيراد المختار",
            key="import_confirm_checkbox",
        )
    with btn_col:
        st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
        do_import = st.button(
            "بدء الاستيراد",
            type="primary",
            use_container_width=True,
            disabled=not confirmed,
            key="import_run_button",
        )

    # ── Run import ─────────────────────────────────────────────────────────
    if do_import and confirmed:
        with st.spinner("جاري استيراد البيانات... يرجى الانتظار"):
            try:
                results = import_report(sheets, mode=import_mode, project_id=get_current_project_id())
                _render_import_results(results, import_mode)
            except RuntimeError as e:
                st.error(f"{e}")
            except Exception as e:
                st.error(f"خطأ غير متوقع: {e}")


def _render_import_results(results: dict, mode: str):
    """Render detailed import results."""
    sheet_labels = {
        'employees':  ('👥', 'الموظفون'),
        'attendance': ('📅', 'سجلات الحضور'),
        'overtime':   ('⏱', 'الأوفر تايم'),
        'advances':   ('💰', 'السلف'),
    }

    total_inserted = sum(v['inserted'] for v in results.values())
    total_updated  = sum(v['updated']  for v in results.values())
    total_skipped  = sum(v['skipped']  for v in results.values())
    total_errors   = sum(len(v['errors']) for v in results.values())

    mode_label = "دمج" if mode == "merge" else "استبدال"

    # Summary banner
    if total_errors == 0:
        st.success(
            f"اكتمل الاستيراد بنجاح (وضع {mode_label}) — "
            f"تمت إضافة {total_inserted} سجل · "
            f"تحديث {total_updated} · تخطي {total_skipped}"
        )
    else:
        st.warning(
            f"اكتمل الاستيراد مع {total_errors} تحذير — "
            f"إضافة {total_inserted} · تحديث {total_updated} · تخطي {total_skipped}"
        )

    stat_pills([
        ("➕", "سجلات مضافة",   str(total_inserted), COLORS['success']),
        ("✏️", "سجلات محدَّثة",  str(total_updated),  COLORS['info']),
        ("⏭️", "سجلات متخطاة",  str(total_skipped),  COLORS['warning']),
        ("❌", "أخطاء",          str(total_errors),   COLORS['danger']),
    ])

    st.markdown("<div style='margin:14px 0 8px;font-size:14px;font-weight:700;'>التفاصيل:</div>",
                unsafe_allow_html=True)

    for key, (icon, label) in sheet_labels.items():
        r = results[key]
        if r['inserted'] == 0 and r['updated'] == 0 and r['skipped'] == 0 and not r['errors']:
            continue  # sheet not processed (not in file)

        has_errors = len(r['errors']) > 0
        cls = "imp-result-err" if has_errors else "imp-result-ok"

        detail = (
            f"مضاف: <b>{r['inserted']}</b> · "
            f"محدَّث: <b>{r['updated']}</b> · "
            f"متخطي: <b>{r['skipped']}</b>"
            + (f" · أخطاء: <b>{len(r['errors'])}</b>" if has_errors else "")
        )

        st.markdown(
            f'<div class="imp-result-row {cls}">'
            f'<span style="display:flex;">{render_icon(icon, size=18)}</span>'
            f'<span style="font-weight:700;min-width:140px;">{label}</span>'
            f'<span style="font-size:12px;color:{COLORS["text_muted"]};">{detail}</span>'
            f'</div>',
            unsafe_allow_html=True
        )

        if has_errors:
            with st.expander(f"أخطاء {label} ({len(r['errors'])})", expanded=False):
                for err in r['errors']:
                    st.caption(f"• {err}")

    if total_errors == 0:
        st.info(
            "**تم الاستيراد بنجاح.** يمكنك الآن التنقل بين لوحات التحكم، "
            "تقارير الحضور، ومسير الرواتب — ستعمل جميعها بشكل طبيعي."
        )
