"""Track paperwork handed to the legal accountant, including receipts and scans."""
import os
import re
import zipfile
from datetime import date
from io import BytesIO

import pandas as pd
import streamlit as st

from components.cards import empty_state, kpi_card, section_card, success_toast
from components.layout import render_topbar
from components.theme import COLORS
from database.db import get_db
from database.models import AccountantHandover, AccountantHandoverAttachment
from database.paths import get_app_data_dir
from services.projects import get_current_project_id


_UPLOAD_TYPES = ["pdf", "png", "jpg", "jpeg", "webp"]


def _safe_filename(name: str) -> str:
    base = os.path.basename(name or "مرفق")
    stem, extension = os.path.splitext(base)
    stem = re.sub(r"[^\w.-]+", "_", stem, flags=re.UNICODE).strip("._") or "مرفق"
    return f"{stem}{extension.lower()}"


def _add_uploaded_file(db, handover, uploaded, kind: str, ordinal: int = 1):
    ext = os.path.splitext(uploaded.name)[1].lower()
    base = _safe_filename(uploaded.name)
    name = f"{ordinal:02d}_{base}" if kind == "scanned_papers" else base
    folder = os.path.join(
        get_app_data_dir(), "accountant_handover",
        str(handover.project_id), str(handover.id),
    )
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    with open(path, "wb") as target:
        target.write(uploaded.getvalue())
    db.add(AccountantHandoverAttachment(
        handover_id=handover.id,
        kind=kind,
        original_name=uploaded.name,
        file_path=path,
    ))


def show():
    render_topbar("المحاسب القانوني", "🧾", "تسليم الأوراق والمستندات")
    section_card("تسجيل تسليم أوراق", "📑", COLORS["primary"])
    st.caption("سجّل الأوراق التي تم تسليمها، وأرفق إيصال الاستلام ونسخ السكانر للرجوع إليها لاحقًا.")

    if "accountant_handover_paper_count" not in st.session_state:
        st.session_state["accountant_handover_paper_count"] = 2
    paper_count = st.session_state["accountant_handover_paper_count"]
    add_col, remove_col, _ = st.columns([1, 1, 4])
    if add_col.button("+ إضافة خانة ورقة", key="add_handover_paper_field"):
        st.session_state["accountant_handover_paper_count"] += 1
        st.rerun()
    if paper_count > 2 and remove_col.button("− إزالة آخر خانة", key="remove_handover_paper_field"):
        st.session_state["accountant_handover_paper_count"] -= 1
        st.rerun()

    with st.form("accountant_handover_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        handover_date = c1.date_input("تاريخ التسليم", value=date.today())
        accountant_name = c2.text_input("اسم المحاسب القانوني *")
        receipt_number = c3.text_input("رقم إيصال الاستلام")
        st.markdown("**الأوراق التي تم تسليمها**")
        paper_values = [
            st.text_input(
                f"الورقة رقم {index}",
                placeholder="اكتب اسم الورقة أو رقم المستند",
                key=f"accountant_handover_paper_{index}",
            )
            for index in range(1, paper_count + 1)
        ]
        c4, c5 = st.columns(2)
        receipt_pdf = c4.file_uploader("إيصال الاستلام (PDF)", type=["pdf"], key="accountant_handover_receipt")
        scanned_files = c5.file_uploader(
            "الأوراق الممسوحة بالسكانر", type=_UPLOAD_TYPES,
            accept_multiple_files=True, key="accountant_handover_scans",
        )
        notes = st.text_input("ملاحظات إضافية")
        submitted = st.form_submit_button("حفظ تسليم الأوراق", type="primary", use_container_width=True)

    if submitted:
        papers_description = "\n".join(
            f"{index}. {value.strip()}"
            for index, value in enumerate(paper_values, start=1)
            if value.strip()
        )
        if not accountant_name.strip() or not papers_description.strip():
            st.error("أدخل اسم المحاسب واكتب ورقة واحدة على الأقل.")
        elif not receipt_pdf:
            st.error("أرفق إيصال الاستلام بصيغة PDF.")
        else:
            db = get_db()
            try:
                handover = AccountantHandover(
                    handover_date=handover_date,
                    accountant_name=accountant_name.strip(),
                    receipt_number=receipt_number.strip(),
                    papers_description=papers_description.strip(),
                    notes=notes.strip(),
                    project_id=get_current_project_id(),
                )
                db.add(handover)
                db.flush()
                _add_uploaded_file(db, handover, receipt_pdf, "receipt")
                for index, uploaded in enumerate(scanned_files or [], start=1):
                    _add_uploaded_file(db, handover, uploaded, "scanned_papers", index)
                db.commit()
                st.session_state["accountant_handover_paper_count"] = 2
                success_toast("تم حفظ تسليم الأوراق ومرفقاته.")
                st.rerun()
            except Exception as exc:
                db.rollback()
                st.error(f"تعذر حفظ التسليم: {exc}")
            finally:
                db.close()

    db = get_db()
    try:
        handovers = db.query(AccountantHandover).filter(
            AccountantHandover.project_id == get_current_project_id()
        ).order_by(AccountantHandover.handover_date.desc(), AccountantHandover.id.desc()).all()
        rows = []
        for record in handovers:
            rows.append({
                "id": record.id,
                "تاريخ التسليم": record.handover_date,
                "المحاسب القانوني": record.accountant_name,
                "رقم إيصال الاستلام": record.receipt_number or "",
                "الأوراق المسلّمة": record.papers_description,
                "ملاحظات": record.notes or "",
                "المرفقات": [{
                    "kind": attachment.kind,
                    "name": attachment.original_name,
                    "path": attachment.file_path,
                } for attachment in record.attachments],
            })
    finally:
        db.close()

    if not rows:
        empty_state("لا توجد تسليمات مسجلة في هذا المشروع بعد", "🧾")
        return

    dates = [row["تاريخ التسليم"] for row in rows]
    f1, f2, f3 = st.columns(3)
    date_from = f1.date_input("من تاريخ", value=min(dates), key="accountant_handover_from")
    date_to = f2.date_input("إلى تاريخ", value=max(max(dates), date.today()), key="accountant_handover_to")
    accountants = ["الكل"] + sorted({row["المحاسب القانوني"] for row in rows})
    accountant_filter = f3.selectbox("المحاسب القانوني", accountants, key="accountant_handover_filter")
    filtered = [row for row in rows if date_from <= row["تاريخ التسليم"] <= date_to
                and (accountant_filter == "الكل" or row["المحاسب القانوني"] == accountant_filter)]
    total_files = sum(len(row["المرفقات"]) for row in filtered)
    k1, k2 = st.columns(2)
    kpi_card(k1, "📦", "عدد مرات التسليم", str(len(filtered)), COLORS["primary"])
    kpi_card(k2, "📎", "عدد الملفات المرفقة", str(total_files), COLORS["info"])
    if not filtered:
        empty_state("لا توجد نتائج في الفترة المحددة", "🔍")
        return

    display = [{
        "تاريخ التسليم": row["تاريخ التسليم"].strftime("%Y-%m-%d"),
        "المحاسب القانوني": row["المحاسب القانوني"],
        "رقم إيصال الاستلام": row["رقم إيصال الاستلام"],
        "الأوراق المسلّمة": row["الأوراق المسلّمة"],
        "عدد المرفقات": len(row["المرفقات"]),
        "ملاحظات": row["ملاحظات"],
    } for row in filtered]
    st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True)

    # The workbook hyperlinks are relative to the attachments folder in the ZIP.
    workbook_buffer = BytesIO()
    export_rows = []
    row_links = []
    max_scans = max((sum(item["kind"] == "scanned_papers" for item in row["المرفقات"]) for row in filtered), default=0)
    for row in filtered:
        receipt = next((item for item in row["المرفقات"] if item["kind"] == "receipt"), None)
        scans = [item for item in row["المرفقات"] if item["kind"] == "scanned_papers"]
        receipt_target = f"مرفقات/{row['id']}/{os.path.basename(receipt['path'])}" if receipt else ""
        scan_targets = [f"مرفقات/{row['id']}/{os.path.basename(item['path'])}" for item in scans]
        export_row = {
            "تاريخ التسليم": row["تاريخ التسليم"].strftime("%Y-%m-%d"),
            "المحاسب القانوني": row["المحاسب القانوني"],
            "رقم إيصال الاستلام": row["رقم إيصال الاستلام"],
            "الأوراق المسلّمة": row["الأوراق المسلّمة"],
            "ملف إيصال الاستلام": os.path.basename(receipt_target) if receipt_target else "",
            "ملاحظات": row["ملاحظات"],
        }
        links = {"ملف إيصال الاستلام": receipt_target}
        for index in range(max_scans):
            column_name = f"ملف سكانر {index + 1}"
            target = scan_targets[index] if index < len(scan_targets) else ""
            export_row[column_name] = os.path.basename(target) if target else ""
            links[column_name] = target
        export_rows.append(export_row)
        row_links.append(links)
    with pd.ExcelWriter(workbook_buffer, engine="openpyxl") as writer:
        pd.DataFrame(export_rows).to_excel(writer, sheet_name="تسليمات المحاسب القانوني", index=False)
        worksheet = writer.sheets["تسليمات المحاسب القانوني"]
        columns = {cell.value: cell.column for cell in worksheet[1]}
        for index, links in enumerate(row_links, start=2):
            for column_name, target in links.items():
                if target:
                    cell = worksheet.cell(row=index, column=columns[column_name])
                    cell.hyperlink = target
                    cell.style = "Hyperlink"
    workbook_bytes = workbook_buffer.getvalue()
    st.download_button(
        "تصدير قائمة المحاسب القانوني إلى Excel",
        data=workbook_bytes,
        file_name=f"تسليمات المحاسب القانوني - {date.today().isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="accountant_handover_excel",
        use_container_width=True,
    )
    bundle = BytesIO()
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("تسليمات المحاسب القانوني.xlsx", workbook_bytes)
        for row in filtered:
            for attachment in row["المرفقات"]:
                if os.path.isfile(attachment["path"]):
                    archive.write(
                        attachment["path"],
                        f"مرفقات/{row['id']}/{os.path.basename(attachment['path'])}",
                    )
    st.download_button(
        "تنزيل Excel مع إيصالات الاستلام وملفات السكانر (ZIP)",
        data=bundle.getvalue(),
        file_name=f"تسليمات المحاسب القانوني ومرفقاته - {date.today().isoformat()}.zip",
        mime="application/zip",
        key="accountant_handover_bundle",
        use_container_width=True,
    )

    with st.expander("عرض إيصال الاستلام وملفات السكانر"):
        labels = {f"{row['تاريخ التسليم']} — {row['المحاسب القانوني']} — {row['رقم إيصال الاستلام'] or row['id']}": row for row in filtered}
        chosen = st.selectbox("اختر عملية تسليم", list(labels), key="accountant_handover_detail")
        selected = labels[chosen]
        if not selected["المرفقات"]:
            st.caption("لا توجد مرفقات محفوظة لهذا التسليم.")
        for attachment in selected["المرفقات"]:
            if not os.path.isfile(attachment["path"]):
                continue
            st.markdown(f"**{'إيصال الاستلام' if attachment['kind'] == 'receipt' else 'ورقة ممسوحة'}:** {attachment['name']}")
            ext = os.path.splitext(attachment["path"])[1].lower()
            if ext in (".png", ".jpg", ".jpeg", ".webp"):
                st.image(attachment["path"], use_container_width=True)
            else:
                with open(attachment["path"], "rb") as file:
                    st.download_button(
                        f"تنزيل {attachment['name']}", file.read(),
                        file_name=attachment["name"], key=f"handover_file_{selected['id']}_{attachment['name']}",
                    )
