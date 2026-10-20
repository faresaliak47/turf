"""Bulk Overtime Entry — adds overtime for multiple employees, each with their own auto-calculated rate."""
import re
import streamlit as st
import pandas as pd
from datetime import date, datetime
from database.db import get_db
from database.models import Employee, Overtime
from components.cards import section_card, empty_state, success_toast, danger_toast, warning_toast, stat_pills
from components.layout import render_topbar
from components.theme import COLORS
from services.rates import calc_hourly_rate as _calc_hourly_rate
from services.projects import get_current_project_id
from services.payroll_service import clear_payroll_cache
from services.name_matching import build_employee_name_index, match_employee_by_name


# ── Bulk-overtime tagging & safe delete-by-date (bulk overtime only) ─
# Overtime and "normal overtime" share the same `overtime` table with no
# column to tell them apart, and we must not change the DB schema. So every
# record created by THIS module is tagged inside the existing `notes` field.
# Deletion is then scoped to date + tag, never touching normal-overtime rows.
_BOT_TAG = "[BULK_OT]"


def _bot_tag_note(note: str) -> str:
    """Prefix a note with the bulk-overtime tag, used on every save in this module."""
    note = (note or "").strip()
    return f"{_BOT_TAG} {note}".strip() if note else _BOT_TAG


def delete_bulk_overtime_by_date(target_date):
    """
    Delete ONLY bulk-overtime-tagged Overtime records for the given date.

    Safety:
      - Filters by date AND the bulk-overtime tag in `notes`, so normal
        overtime (or any record not created via Bulk Overtime) is never
        touched, and other dates are never touched.
      - Note: legacy bulk-overtime rows saved before this tagging was
        introduced won't carry the tag, so they are intentionally NOT
        deleted by this function (we can't safely tell them apart from
        normal overtime without it).

    Returns: (deleted_count: int, error: str | None)
    """
    db = get_db()
    try:
        records = db.query(Overtime).filter(
            Overtime.date == target_date,
            Overtime.notes.like(f"{_BOT_TAG}%"),
            Overtime.project_id == get_current_project_id(),
        ).all()
        deleted_count = len(records)
        for r in records:
            db.delete(r)
        db.commit()
        clear_payroll_cache()
        return deleted_count, None
    except Exception as e:
        db.rollback()
        return 0, str(e)
    finally:
        db.close()


# ── Smart Paste: parsing helpers (bulk overtime only) ─────────────
# NOTE: Equipment entries (عربية / لودر / معدات) are treated EXACTLY like
# employee entries everywhere in this module — same parsing, same matching,
# same rate calculation, same save/list/delete pipeline. There is no
# separate "equipment" path anymore.
_BOT_AR_DIGITS   = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_BOT_NOISE_RE    = re.compile(r'\bعمال\b', re.UNICODE)
_BOT_UNITS_RE    = re.compile(r'\+\s*(\d+)\s*$')

# A line that is ONLY a number followed by "ساعة"/"ساعات" (e.g. "2 ساعة",
# "14 ساعة", "3 ساعات") — i.e. a group-header line that sets the CURRENT
# hours value for every name line that follows it, until the next such
# line. Deliberately anchored start-to-end so a name that happens to
# contain a number is never mistaken for an hours line.
_BOT_HOURS_LINE_RE = re.compile(r'^(\d+(?:[.,]\d+)?)\s*ساع(?:ة|ات)\s*$', re.UNICODE)


def _bot_normalize_digits(s: str) -> str:
    """Convert Arabic-Indic digits (٠-٩) to Western digits (0-9)."""
    return s.translate(_BOT_AR_DIGITS)


def _bot_parse_hours_line(line: str):
    """
    Return the hours value (int|float) if `line` is a standalone
    "N ساعة"/"N ساعات" group-header line, or None if it's a name/equipment
    line instead. Used by parse_bulk_overtime_text() to detect where a new
    hours-group begins (see that function's docstring).
    """
    normalized = _bot_normalize_digits(line).strip()
    m = _BOT_HOURS_LINE_RE.match(normalized)
    if not m:
        return None
    num_str = m.group(1).replace(',', '.')
    try:
        hours = float(num_str)
    except ValueError:
        return None
    if hours.is_integer():
        hours = int(hours)
    return hours


def _bot_parse_line(line: str):
    """
    Parse a single bulk-overtime name line, extracting the optional "+N" bonus.
      "شريف أبو العزم+1"  -> {name:"شريف أبو العزم", bonus:1}
      "عربية نقل عمال"     -> {name:"عربية نقل",      bonus:0}

    `bonus` is added to the current group's hours by the caller (see
    parse_bulk_overtime_text) to get overtime_units.
    Every entry (employee or equipment name) goes through identical parsing —
    there is no type distinction.
    """
    line = _bot_normalize_digits(line).strip()
    if not line:
        return None

    bonus = 0
    m = _BOT_UNITS_RE.search(line)
    if m:
        bonus = int(m.group(1))
        line = line[:m.start()].strip()

    name = _BOT_NOISE_RE.sub('', line)
    name = re.sub(r'\s+', ' ', name).strip()
    if not name:
        return None

    return {"name": name, "bonus": bonus}


def parse_bulk_overtime_text(text: str):
    """
    Parse the smart-paste bulk overtime format.

      line 1               -> date (DD/M/YYYY, also accepts Arabic digits)
      remaining lines      -> one or more GROUPS, each group being:
                                 • one "hours" line (e.g. "2 ساعة", "3 ساعات",
                                   "14 ساعة") — this becomes the CURRENT hours
                                   value
                                 • followed by one or more employee/equipment
                                   name lines, each credited with the CURRENT
                                   hours value (never split/divided between
                                   them; an optional trailing "+N" on a name
                                   line still adds a per-person bonus on top,
                                   exactly as before)

      A new hours line always starts a new group and replaces the current
      hours value for every name line after it, until the next hours line
      (or the end of the text). A single hours line followed directly by
      names — the old format — is just a text with exactly one group, so
      old-format pastes parse identically to before.

    Returns: (ot_date | None, first_hours | None, entries: list[dict], errors: list[str])
      `first_hours` is the hours value of the FIRST group (kept for the
      summary display / backward compatibility). Each entry also carries
      its own group's hours in `base_hours`, since different entries can
      belong to different groups.
    """
    raw_lines = [l.strip() for l in text.strip().splitlines()]
    lines = [l for l in raw_lines if l]

    if len(lines) < 2:
        return None, None, [], ['النص غير مكتمل: يجب أن يحتوي على سطر تاريخ وسطر ساعات على الأقل']

    date_line = _bot_normalize_digits(lines[0])
    ot_date = None
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y'):
        try:
            ot_date = datetime.strptime(date_line, fmt).date()
            break
        except ValueError:
            continue
    if ot_date is None:
        return None, None, [], [f'تنسيق التاريخ غير صحيح: {lines[0]}']

    entries = []
    current_hours = None   # hours value of the group we're currently inside
    first_hours = None     # hours value of the very first group (for display/compat)

    for line in lines[1:]:
        group_hours = _bot_parse_hours_line(line)
        if group_hours is not None:
            # New group starts here — every name line below this point
            # (until the next hours line) is credited with group_hours.
            current_hours = group_hours
            if first_hours is None:
                first_hours = group_hours
            continue

        parsed = _bot_parse_line(line)
        if not parsed:
            continue
        if current_hours is None:
            # A name appeared before any hours line was found — no group
            # to attach it to yet, so it's skipped rather than guessed.
            continue

        units = current_hours + parsed["bonus"]
        if isinstance(units, float) and units.is_integer():
            units = int(units)
        entries.append({
            "name": parsed["name"],
            "base_hours": current_hours,
            "overtime_units": units,
        })

    if first_hours is None:
        return ot_date, None, [], ['لم يتم العثور على عدد الساعات']

    if not entries:
        return ot_date, first_hours, [], ['لم يتم العثور على أسماء صالحة في النص']

    return ot_date, first_hours, entries, []


def show():
    render_topbar("إدخال أوفر تايم جماعي", "⏱", "الأوفر تايم الجماعي")

    tab1, tab2, tab3, tab4 = st.tabs([
        "إدخال جماعي", "سجلات الأوفر تايم", "لصق نص ذكي", "حذف بالتاريخ",
    ])
    with tab1:
        _bulk_add_overtime()
    with tab2:
        _list_overtime()
    with tab3:
        _smart_paste_overtime()
    with tab4:
        _delete_bulk_overtime_tab()


def _render_bulk_overtime_confirmation(emp_by_id):
    """Review a bulk-entry payload and save only after an explicit confirm."""
    pending = st.session_state.get("bulk_ot_save_pending")
    if not pending:
        return False

    project_id = get_current_project_id()
    if pending.get("project_id") != project_id:
        st.session_state.pop("bulk_ot_save_pending", None)
        st.warning("تم إلغاء المراجعة لأن المشروع الحالي تغيّر.")
        return False

    employee_ids = [eid for eid in pending["employee_ids"] if eid in emp_by_id]
    if not employee_ids:
        st.session_state.pop("bulk_ot_save_pending", None)
        st.warning("لم يعد هناك موظفون صالحون في عملية الحفظ.")
        return False

    check_db = get_db()
    try:
        existing_records = check_db.query(Overtime).filter(
            Overtime.employee_id.in_(employee_ids),
            Overtime.date == pending["date"],
            Overtime.project_id == project_id,
        ).all()
    finally:
        check_db.close()

    existing_by_employee = {}
    for record in existing_records:
        existing_by_employee.setdefault(record.employee_id, record)

    rows = []
    eligible_ids = []
    duplicate_names = []
    for eid in employee_ids:
        emp = emp_by_id[eid]
        rate = _calc_hourly_rate(emp)
        amount = round(pending["hours"] * rate, 2)
        previous = existing_by_employee.get(eid)
        if previous:
            duplicate_names.append(emp.name)
            status = "مكرر — لن يُحفظ"
            old_hours = previous.hours
        else:
            eligible_ids.append(eid)
            status = "جديد — ينتظر التأكيد"
            old_hours = "—"
        rows.append({
            "الاسم": emp.name,
            "التاريخ": pending["date"].strftime("%d/%m/%Y"),
            "الساعات الجديدة": pending["hours"],
            "الساعات المسجلة سابقًا": old_hours,
            "المبلغ المسجل سابقًا": previous.amount if previous else "—",
            "المبلغ المتوقع": amount,
            "الحالة": status,
        })

    st.markdown("### مراجعة الأوفر تايم قبل الحفظ")
    st.caption(
        f"التاريخ {pending['date'].strftime('%d/%m/%Y')} — "
        f"الساعات لكل موظف {pending['hours']:g} — "
        f"الموظفون الجدد {len(eligible_ids)} من {len(employee_ids)}. "
        "لن يتم الحفظ حتى تضغط زر التأكيد."
    )
    if duplicate_names:
        warning_toast("سجلات مكررة لن تُحفظ: " + "، ".join(duplicate_names))
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    confirm_col, cancel_col, _ = st.columns([1.4, 1, 3.6])
    confirmed = confirm_col.button(
        f"تأكيد حفظ {len(eligible_ids)} سجل",
        type="primary",
        disabled=not eligible_ids,
        key="bulk_ot_save_confirm",
    )
    cancelled = cancel_col.button("إلغاء", key="bulk_ot_save_cancel")

    if cancelled:
        st.session_state.pop("bulk_ot_save_pending", None)
        st.info("تم الإلغاء. لم يتم حفظ أي سجل.")
        st.rerun()

    if confirmed:
        write_db = get_db()
        try:
            # Repeat duplicate check at commit time to avoid races between
            # rendering the review and confirming it.
            latest_existing = {
                row.employee_id for row in write_db.query(Overtime.employee_id).filter(
                    Overtime.employee_id.in_(eligible_ids),
                    Overtime.date == pending["date"],
                    Overtime.project_id == project_id,
                ).all()
            }
            if latest_existing:
                write_db.rollback()
                warning_toast("ظهر تكرار جديد أثناء المراجعة؛ حدّثت القائمة لتراجعه قبل الحفظ.")
                st.rerun()

            for eid in eligible_ids:
                emp = emp_by_id[eid]
                rate = _calc_hourly_rate(emp)
                write_db.add(Overtime(
                    employee_id=eid,
                    date=pending["date"],
                    hours=pending["hours"],
                    rate_per_hour=rate,
                    amount=round(pending["hours"] * rate, 2),
                    notes=_bot_tag_note(pending["notes"]),
                    project_id=project_id,
                ))
            write_db.commit()
            clear_payroll_cache()
            st.session_state.pop("bulk_ot_save_pending", None)
            st.session_state["bulk_ot_selected_ids"] = set()
            success_toast(
                f"تم حفظ الأوفر تايم لـ {len(eligible_ids)} موظف بعد التأكيد. "
                f"إجمالي المبلغ: {sum(round(pending['hours'] * _calc_hourly_rate(emp_by_id[eid]), 2) for eid in eligible_ids):,.2f} ج.م"
            )
            st.rerun()
        except Exception as exc:
            write_db.rollback()
            danger_toast(f"خطأ أثناء الحفظ، تم التراجع عن جميع التغييرات: {exc}")
        finally:
            write_db.close()

    return True


def _bulk_add_overtime():
    section_card("اختيار الموظفين", "👥", COLORS['primary'])

    # ── Persistent selection set ──────────────────────────────────
    # We store selected employee IDs in a set that survives filter/search changes.
    if "bulk_ot_selected_ids" not in st.session_state:
        st.session_state["bulk_ot_selected_ids"] = set()

    db = get_db()
    try:
        employees = db.query(Employee).filter(
            Employee.status == 'Active', Employee.project_id == get_current_project_id()
        ).order_by(Employee.name).all()
        if not employees:
            empty_state("لا يوجد موظفون نشطون في هذا المشروع", "👥")
            return
        emp_data = [{
            "id":      e.id,
            "الاسم":  e.name,
            "الكود":  e.code,
            "القسم":  e.department or "—",
            "_emp":   e,
        } for e in employees]
    finally:
        db.close()

    df_all = pd.DataFrame(emp_data)
    emp_by_id = {row["id"]: row["_emp"] for _, row in df_all.iterrows()}

    if _render_bulk_overtime_confirmation(emp_by_id):
        return

    # ── Filter Controls ──────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    search_name = col1.text_input("بحث بالاسم",  placeholder="اكتب اسم الموظف...")
    search_code = col2.text_input("بحث بالكود",  placeholder="اكتب كود الموظف...")
    depts       = ["الكل"] + sorted(df_all["القسم"].dropna().unique().tolist())
    filter_dept = col3.selectbox("تصفية بالقسم", depts)

    df_filtered = df_all.copy()
    if search_name:
        df_filtered = df_filtered[df_filtered["الاسم"].str.contains(search_name, case=False, na=False)]
    if search_code:
        df_filtered = df_filtered[df_filtered["الكود"].str.contains(search_code, case=False, na=False)]
    if filter_dept != "الكل":
        df_filtered = df_filtered[df_filtered["القسم"] == filter_dept]

    # ── Select All / Unselect All (acts on filtered view only) ────
    ca, cb, _ = st.columns([1, 1, 4])
    if ca.button("تحديد الكل", use_container_width=True):
        for eid in df_filtered["id"].tolist():
            st.session_state["bulk_ot_selected_ids"].add(eid)
        st.rerun()
    if cb.button("إلغاء التحديد", use_container_width=True):
        for eid in df_filtered["id"].tolist():
            st.session_state["bulk_ot_selected_ids"].discard(eid)
        st.rerun()

    st.markdown(
        f"<p style='font-size:12px;color:{COLORS['text_muted']};'>"
        f"يُظهر {len(df_filtered)} موظف من أصل {len(df_all)}</p>",
        unsafe_allow_html=True,
    )

    # ── Employee Selection Table ──────────────────────────────────
    with st.container(key="bulk_ot_emp_table"):
        hc1, hc2, hc3, hc4, hc5 = st.columns([0.5, 3, 1.5, 2, 2])
        for col, label in zip(
            [hc1, hc2, hc3, hc4, hc5],
            ["تحديد", "الاسم", "الكود", "القسم", "معدل الساعة (ج.م)"],
        ):
            col.markdown(
                f"<span style='font-size:11px;font-weight:700;color:{COLORS['text_muted']};'>{label}</span>",
                unsafe_allow_html=True,
            )
        st.markdown(f"<hr style='margin:4px 0 8px;border-color:{COLORS['border']};'>", unsafe_allow_html=True)

        for _, row in df_filtered.iterrows():
            eid = row["id"]
            emp = row["_emp"]
            hr  = _calc_hourly_rate(emp)
            ec1, ec2, ec3, ec4, ec5 = st.columns([0.5, 3, 1.5, 2, 2])

            # Read current state from our persistent set (not from a keyed widget)
            current_checked = eid in st.session_state["bulk_ot_selected_ids"]
            new_checked = ec1.checkbox(
                "",
                value=current_checked,
                key=f"bulk_ot_cb_{eid}",
                label_visibility="collapsed",
            )

            # Sync checkbox change back to the persistent set
            if new_checked != current_checked:
                if new_checked:
                    st.session_state["bulk_ot_selected_ids"].add(eid)
                else:
                    st.session_state["bulk_ot_selected_ids"].discard(eid)

            ec2.markdown(f"<span style='font-size:13px;'>{row['الاسم']}</span>", unsafe_allow_html=True)
            ec3.markdown(f"<span style='font-size:12px;color:{COLORS['primary']};font-weight:600;'>{row['الكود']}</span>", unsafe_allow_html=True)
            ec4.markdown(f"<span style='font-size:12px;color:{COLORS['text_muted']};'>{row['القسم']}</span>", unsafe_allow_html=True)
            ec5.markdown(
                f"<span style='font-size:12px;color:{COLORS['success'] if hr > 0 else COLORS['danger']};font-weight:600;'>"
                f"{'%.4f' % hr if hr > 0 else 'غير محدد'}</span>",
                unsafe_allow_html=True,
            )

    # ── Selected Employees Counter ────────────────────────────────
    selected_ids = list(st.session_state["bulk_ot_selected_ids"])
    selected_count = len(selected_ids)

    st.markdown(
        f"<div style=\"background:{COLORS['primary']}18;border:1px solid {COLORS['primary']}40;"
        f"border-radius:8px;padding:10px 16px;margin:12px 0;font-size:14px;font-weight:700;"
        f"color:{COLORS['primary']};\">"
        f"الموظفون المحددون: {selected_count}</div>",
        unsafe_allow_html=True,
    )

    # ── Selected Employees Preview Panel ─────────────────────────
    if selected_count > 0:
        with st.expander(f"عرض الموظفين المحددين ({selected_count})", expanded=True):
            preview_rows = []
            for eid in selected_ids:
                emp = emp_by_id.get(eid)
                if emp:
                    hr = _calc_hourly_rate(emp)
                    preview_rows.append({
                        "الاسم":              emp.name,
                        "الكود":              emp.code,
                        "القسم":              emp.department or "—",
                        "معدل الساعة (ج.م)": f"{hr:.4f}" if hr > 0 else "غير محدد",
                    })
            if preview_rows:
                st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)

    st.markdown("---")
    section_card("بيانات الأوفر تايم", "⏱", COLORS['warning'])

    # ── Overtime Data Entry ───────────────────────────────────────
    with st.form("bulk_overtime_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        ot_date = col1.date_input("التاريخ", value=date.today())
        hours   = col2.number_input("الساعات", min_value=0.0, max_value=24.0, step=0.5, value=2.0)
        notes   = st.text_input("ملاحظات", placeholder="اختياري")

        st.info(
            "سيتم حساب معدل الساعة والمبلغ تلقائياً لكل موظف بناءً على راتبه أو يوميته.",
            icon=None,
        )

        submitted = st.form_submit_button(
            "حفظ الأوفر تايم للموظفين المحددين",
            type="primary",
            use_container_width=True,
        )

        if submitted:
            # Read final selection from the persistent set
            final_ids = list(st.session_state.get("bulk_ot_selected_ids", set()))

            if not final_ids:
                st.error("يرجى تحديد موظف واحد على الأقل.")
            elif hours <= 0:
                st.error("الساعات يجب أن تكون أكبر من صفر.")
            else:
                no_rate = [emp_by_id[eid].name for eid in final_ids if _calc_hourly_rate(emp_by_id[eid]) <= 0]
                if no_rate:
                    st.error(
                        f"الموظفون التاليون ليس لديهم راتب أو يومية محددة:\n"
                        + "\n".join(f"• {n}" for n in no_rate)
                    )
                else:
                    st.session_state["bulk_ot_save_pending"] = {
                        "employee_ids": final_ids,
                        "date": ot_date,
                        "hours": hours,
                        "notes": notes,
                        "project_id": get_current_project_id(),
                    }
                    st.rerun()


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
            'الموظف':      employees[r.employee_id].name if r.employee_id in employees else '—',
            'كود الموظف':  employees[r.employee_id].code if r.employee_id in employees else '—',
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
        ("📋", "عدد السجلات",    str(len(df)),                           COLORS['primary']),
        ("⏱",  "إجمالي الساعات", f"{df['الساعات'].sum():.1f} ساعة",    COLORS['warning']),
        ("💰", "إجمالي المبلغ",   f"{df['قيمة الأوفر'].sum():,.0f} ج.م", COLORS['success']),
    ])

    search = st.text_input("بحث في السجلات", placeholder="ابحث بالاسم أو القسم...")
    if search:
        mask = df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)
        df = df[mask]

    st.dataframe(df, use_container_width=True, hide_index=True)


# ── Smart Paste Tab (additive — does not affect the two tabs above) ──
def _bot_match_employee(name: str, name_index: dict):
    """Tolerant Arabic name matching — diacritics, أ/إ/آ/ا, "أبو"/"ابو",
    extra spaces (see services/name_matching.py). Never guesses between
    two equally-plausible matches: those come back unmatched, same as
    a name that matches nothing at all, so a human resolves it instead
    of the wrong employee's timesheet getting credited silently."""
    emp, _status = match_employee_by_name(name, name_index=name_index)
    return emp


def _smart_paste_overtime():
    import json as _json

    section_card("لصق نص ذكي للأوفر تايم الجماعي", "🧠", COLORS['primary'])

    st.markdown(
        f"<div style=\"background:{COLORS['primary']}12;border:1px solid {COLORS['primary']}30;"
        f"border-radius:8px;padding:10px 16px;margin-bottom:12px;font-size:13px;color:{COLORS['primary']};\">"
        f"السطر الأول: التاريخ (مثال 16/6/2026). بعده أي عدد من المجموعات، كل مجموعة = "
        f"سطر عدد ساعات (مثال \"2 ساعة\" أو \"3 ساعات\") يليه أسماء الموظفين/المعدات اللي بتاخد "
        f"نفس عدد الساعات ده (بدون قسمة). أي سطر ساعات جديد يبدأ مجموعة جديدة بقيمة جديدة."
        f" يمكن إضافة \"+1\" على أي اسم لوحدات إضافية فوق ساعات مجموعته."
        f" المعدات (عربية / لودر / معدات...) تُعامل تمامًا كأي موظف — لا يوجد فصل بينهما."
        f"</div>",
        unsafe_allow_html=True,
    )

    sample = """16/6/2026
2 ساعة
علاء محمد
شريف أبو العزم+1
عادل عربي +1

1 ساعة
محمود فتحي

3 ساعات
عربية نقل عمال"""

    text = st.text_area(
        "الصق النص هنا:",
        placeholder=sample,
        height=240,
        key="bot_smart_paste_input",
    )

    pending_payload = st.session_state.get("bot_smart_ot_save_pending")
    if pending_payload and (
        pending_payload.get("text") != text
        or pending_payload.get("project_id") != get_current_project_id()
    ):
        st.session_state.pop("bot_smart_ot_save_pending", None)
        pending_payload = None
    pending_text = bool(pending_payload)

    if not text.strip():
        return

    ot_date, hours, entries, errors = parse_bulk_overtime_text(text)

    if errors:
        st.error(" | ".join(errors))
        return

    db = get_db()
    try:
        employees = db.query(Employee).filter(
            Employee.status == 'Active', Employee.project_id == get_current_project_id()
        ).all()
        name_index = build_employee_name_index(employees)

        # All entries (employee names AND equipment names) go through the
        # exact same matching + rate-calculation + save pipeline. There is
        # no separate equipment path: an equipment entry only "counts" if it
        # matches an active record in the Employee table, exactly like any
        # other name — same as a worker would.
        matched_rows, unmatched_rows = [], []
        for e in entries:
            emp = _bot_match_employee(e["name"], name_index)
            if emp:
                hr = _calc_hourly_rate(emp)
                total_hours = e["overtime_units"]  # already base_hours + bonus
                matched_rows.append({
                    **e,
                    "employee_id": emp.id,
                    "rate_per_hour": hr,
                    "amount": round(total_hours * hr, 2),
                    "total_hours": total_hours,
                })
            else:
                unmatched_rows.append(e)

        # ── Duplicate detection (same employee + same date) ────────────
        # Mirrors the "smart paste" duplicate logic already used in
        # Attendance: if an employee already has ANY overtime row (normal
        # or bulk) for this exact date, saving again would double their
        # overtime for the day. We flag those separately and exclude them
        # from the save instead of silently re-adding them.
        dup_rows, new_rows = [], []
        if matched_rows:
            matched_emp_ids = {r["employee_id"] for r in matched_rows}
            existing = db.query(Overtime).filter(
                Overtime.date == ot_date,
                Overtime.employee_id.in_(matched_emp_ids),
                Overtime.project_id == get_current_project_id(),
            ).all()
            existing_by_emp = {}
            for rec in existing:
                existing_by_emp.setdefault(rec.employee_id, rec)  # first one is enough to flag

            seen_in_paste = {}
            for r in matched_rows:
                prev = existing_by_emp.get(r["employee_id"])
                if prev:
                    dup_rows.append({**r, "_prev_hours": prev.hours, "_prev_amount": prev.amount,
                                      "_prev_notes": prev.notes or "",
                                      "_duplicate_source": "سجل محفوظ لنفس الموظف والتاريخ"})
                elif r["employee_id"] in seen_in_paste:
                    first = seen_in_paste[r["employee_id"]]
                    dup_rows.append({
                        **r,
                        "_prev_hours": first["total_hours"],
                        "_prev_amount": first["amount"],
                        "_prev_notes": "تكرار داخل النص الملصق",
                        "_duplicate_source": "الاسم مكرر داخل النص نفسه",
                    })
                else:
                    new_rows.append(r)
                    seen_in_paste[r["employee_id"]] = r
    finally:
        db.close()

    if pending_text and not new_rows:
        st.session_state.pop("bot_smart_ot_save_pending", None)
        pending_text = False

    # A paste can now contain more than one hours-group (see
    # parse_bulk_overtime_text), so show every distinct base-hours value
    # found — not just the first — to avoid implying all names share one
    # hours figure when they don't.
    _seen_hours = []
    for _e in entries:
        _bh = _e.get('base_hours', hours)
        if _bh not in _seen_hours:
            _seen_hours.append(_bh)
    hours_display = " / ".join(f"{h:g}" for h in _seen_hours) if _seen_hours else f"{hours:g}"

    st.markdown(
        f"<div style='background:{COLORS['info']}18;border:1px solid {COLORS['info']}33;"
        f"border-radius:8px;padding:8px 16px;margin:8px 0;font-size:13px;color:{COLORS['info']};font-weight:600;'>"
        f"التاريخ: {ot_date.strftime('%d/%m/%Y')} — الساعات: {hours_display}</div>",
        unsafe_allow_html=True,
    )

    stat_pills([
        ("✅", "جديد (ينتظر التأكيد)",    str(len(new_rows)),       COLORS['success']),
        ("🔁", "مكرر (له سجل بنفس اليوم)", str(len(dup_rows)),       COLORS['warning']),
        ("⚠️", "غير متطابق",              str(len(unmatched_rows)), COLORS['danger']),
    ])

    if new_rows:
        st.dataframe(
            pd.DataFrame([{
                "الاسم": r["name"],
                "الوحدات": r["overtime_units"],
                "إجمالي الساعات": r["total_hours"],
                "معدل الساعة": r["rate_per_hour"],
                "المبلغ المتوقع": r["amount"],
            } for r in new_rows]),
            use_container_width=True, hide_index=True,
        )

    if dup_rows:
        with st.expander(f"مكرر — له سجل أوفر تايم بالفعل في نفس اليوم ({len(dup_rows)}) — لن يتم حفظه", expanded=True):
            st.caption("لتجنب مضاعفة المبلغ، هذه الأسماء لن تُحفظ لأن لديها بالفعل سجل أوفر تايم بنفس التاريخ. "
                       "لو عايز تعدّل السجل الموجود، استخدم صفحة سجلات الأوفر تايم مباشرة.")
            st.dataframe(
                pd.DataFrame([{
                    "الاسم": r["name"],
                    "سبب التكرار": r.get("_duplicate_source", "سجل محفوظ لنفس الموظف والتاريخ"),
                    "الوحدات في اللصق الحالي": r["overtime_units"],
                    "الساعات المسجّلة بالفعل": r["_prev_hours"],
                    "المبلغ المسجّل بالفعل": r["_prev_amount"],
                    "ملاحظات": r["_prev_notes"],
                } for r in dup_rows]),
                use_container_width=True, hide_index=True,
            )

    if unmatched_rows:
        with st.expander(f"أسماء غير متطابقة مع الموظفين/المعدات ({len(unmatched_rows)})", expanded=True):
            for r in unmatched_rows:
                st.markdown(f"- {r['name']} (وحدات: {r['overtime_units']})")

    with st.expander("عرض JSON الناتج عن التحليل", expanded=False):
        st.code(_json.dumps({
            "date": ot_date.isoformat(),
            "hours": hours,
            "entries": entries,
        }, ensure_ascii=False, indent=2), language="json")

    if new_rows:
        if not pending_text:
            review_label = f"مراجعة {len(new_rows)} سجل أوفر تايم قبل الحفظ"
            if dup_rows:
                review_label += f" (مع تجاهل {len(dup_rows)} مكرر)"
            if st.button(
                review_label,
                type="primary",
                use_container_width=True,
                key="bot_smart_review_btn",
            ):
                st.session_state["bot_smart_ot_save_pending"] = {
                    "text": text,
                    "project_id": get_current_project_id(),
                }
                st.rerun()
        else:
            st.info(
                f"راجع الجدول أعلاه: سيتم حفظ {len(new_rows)} سجل جديد فقط، "
                f"وسيتم تجاهل {len(dup_rows)} سجل مكرر. لم يتم حفظ شيء بعد."
            )
            confirm_col, cancel_col, _ = st.columns([1.5, 1, 3.5])
            confirm = confirm_col.button(
                f"تأكيد حفظ {len(new_rows)} سجل",
                type="primary",
                key="bot_smart_confirm_btn",
            )
            cancel = cancel_col.button("إلغاء", key="bot_smart_cancel_btn")

            if cancel:
                st.session_state.pop("bot_smart_ot_save_pending", None)
                st.info("تم الإلغاء. لم يتم حفظ أي سجل.")
                st.rerun()

            if confirm:
                db_w = get_db()
                try:
                    new_employee_ids = {r["employee_id"] for r in new_rows}
                    raced_duplicates = {
                        row.employee_id for row in db_w.query(Overtime.employee_id).filter(
                            Overtime.employee_id.in_(new_employee_ids),
                            Overtime.date == ot_date,
                            Overtime.project_id == get_current_project_id(),
                        ).all()
                    }
                    if raced_duplicates:
                        db_w.rollback()
                        warning_toast("ظهر تكرار جديد أثناء المراجعة؛ حدّثت القائمة لتراجعه قبل الحفظ.")
                        st.rerun()

                    for r in new_rows:
                        # Use this row's OWN group hours (base_hours), not the
                        # first group's — different rows can belong to different
                        # hours-groups when the paste has more than one.
                        bonus = r['overtime_units'] - r.get('base_hours', hours)
                        note = "لصق نص ذكي" + (f" (+{bonus:g} ساعة إضافية)" if bonus > 0 else "")
                        db_w.add(Overtime(
                            employee_id=r["employee_id"],
                            date=ot_date,
                            hours=r["total_hours"],
                            rate_per_hour=r["rate_per_hour"],
                            amount=r["amount"],
                            notes=_bot_tag_note(note),
                            project_id=get_current_project_id(),
                        ))
                    db_w.commit()
                    clear_payroll_cache()
                    st.session_state.pop("bot_smart_ot_save_pending", None)
                    msg = f"تم حفظ الأوفر تايم لـ {len(new_rows)} عنصر بعد التأكيد."
                    if dup_rows:
                        msg += f" تم تجاهل {len(dup_rows)} عنصر مكرر (له سجل بالفعل بنفس اليوم)."
                    success_toast(msg)
                    st.rerun()
                except Exception as ex:
                    db_w.rollback()
                    danger_toast(f"خطأ أثناء الحفظ، تم التراجع عن جميع التغييرات: {ex}")
                finally:
                    db_w.close()
    elif dup_rows and not unmatched_rows:
        st.session_state.pop("bot_smart_ot_save_pending", None)
        warning_toast("كل الأسماء المطابقة لها سجل أوفر تايم بالفعل في هذا التاريخ — لا يوجد جديد ليتم حفظه.")


# ── Delete Day Tab (additive — only ever deletes bulk-overtime-tagged rows) ──
def _delete_bulk_overtime_tab():
    section_card("حذف الأوفر تايم الجماعي بالتاريخ", "🗑️", COLORS['danger'])

    st.markdown(
        f"<div style=\"background:{COLORS['danger']}12;border:1px solid {COLORS['danger']}30;"
        f"border-radius:8px;padding:10px 16px;margin-bottom:12px;font-size:13px;color:{COLORS['danger']};\">"
        f"يحذف هذا الإجراء سجلات الأوفر تايم <b>الجماعي فقط</b> (المُدخَلة من هذه الصفحة) ليوم واحد محدد."
        f" لا يؤثر على الأوفر تايم العادي ولا على أي تاريخ آخر."
        f"</div>",
        unsafe_allow_html=True,
    )

    target_date = st.date_input("اختر التاريخ المطلوب حذفه", value=date.today(), key="bot_delete_date")

    db = get_db()
    try:
        records = db.query(Overtime).filter(
            Overtime.date == target_date,
            Overtime.notes.like(f"{_BOT_TAG}%"),
            Overtime.project_id == get_current_project_id(),
        ).all()
        preview_count = len(records)
        if preview_count:
            emp_ids = {r.employee_id for r in records}
            emps = {e.id: e for e in db.query(Employee).filter(Employee.id.in_(emp_ids)).all()}
            preview_rows = [{
                "الاسم":    emps[r.employee_id].name if r.employee_id in emps else "—",
                "الساعات":  r.hours,
                "المبلغ":   r.amount,
                "ملاحظات":  r.notes or "",
            } for r in records]
    finally:
        db.close()

    if preview_count == 0:
        empty_state("لا توجد سجلات أوفر تايم جماعي في هذا التاريخ", "🗑️")
        return

    st.markdown(
        f"<div style=\"background:{COLORS['warning']}18;border:1px solid {COLORS['warning']}40;"
        f"border-radius:8px;padding:10px 16px;margin:12px 0;font-size:14px;font-weight:700;"
        f"color:{COLORS['warning']};\">"
        f"سيتم حذف {preview_count} سجل أوفر تايم جماعي بتاريخ {target_date.strftime('%d/%m/%Y')}</div>",
        unsafe_allow_html=True,
    )

    with st.expander(f"عرض السجلات المطلوب حذفها ({preview_count})", expanded=True):
        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)

    confirm = st.checkbox(
        f"أؤكد حذف جميع سجلات الأوفر تايم الجماعي ({preview_count}) بتاريخ "
        f"{target_date.strftime('%d/%m/%Y')} — لا يمكن التراجع عن هذا الإجراء.",
        key="bot_delete_confirm",
    )

    if st.button(
        "حذف اليوم (Delete Day)",
        type="primary",
        use_container_width=True,
        disabled=not confirm,
        key="bot_delete_btn",
    ):
        deleted, err = delete_bulk_overtime_by_date(target_date)
        if err:
            danger_toast(f"خطأ أثناء الحذف: {err}")
        else:
            success_toast(
                f"تم حذف {deleted} سجل أوفر تايم جماعي بتاريخ {target_date.strftime('%d/%m/%Y')}."
            )
            st.rerun()
