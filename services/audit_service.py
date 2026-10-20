"""User attribution, durable change history, and optional SMTP notifications."""
import contextvars
import json
import logging
import smtplib
from email.message import EmailMessage
from datetime import datetime

import streamlit as st
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from database.models import AuditLog

_actor = contextvars.ContextVar("hrpro_audit_actor", default=None)
_log = logging.getLogger(__name__)
_EXCLUDED = {"password_hash", "national_id"}


class audit_actor:
    def __init__(self, user_id, username):
        self.value = {"user_id": user_id, "username": username or "غير معروف"}

    def __enter__(self):
        self.token = _actor.set(self.value)
        return self

    def __exit__(self, *_):
        _actor.reset(self.token)


def _json(value):
    return json.dumps(value, ensure_ascii=False, default=str)


def _snapshot(obj, changed_only=False):
    state = inspect(obj)
    result = {}
    for attr in state.mapper.column_attrs:
        key = attr.key
        if key in _EXCLUDED or key == "id":
            continue
        history = state.attrs[key].history
        if changed_only and not history.has_changes():
            continue
        if changed_only:
            old = history.deleted[0] if history.deleted else None
            new = history.added[0] if history.added else getattr(obj, key, None)
            result[key] = {"من": old, "إلى": new}
        else:
            result[key] = getattr(obj, key, None)
    return result


@event.listens_for(Session, "after_flush")
def _write_audit_rows(session, flush_context):
    actor = _actor.get()
    if not actor or session.info.get("audit_writing"):
        return
    changed = []
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        if isinstance(obj, AuditLog):
            continue
        state = inspect(obj)
        if obj in session.new:
            action, details = "إضافة", _snapshot(obj)
        elif obj in session.deleted:
            action, details = "حذف", _snapshot(obj)
        elif state.modified:
            details = _snapshot(obj, changed_only=True)
            if not details:
                continue
            action = "تعديل"
        else:
            continue
        record_id = getattr(obj, "id", None)
        entry = AuditLog(
            occurred_at=datetime.utcnow(), user_id=actor["user_id"],
            username=actor["username"], action=action,
            table_name=obj.__tablename__, record_id=str(record_id or ""),
            changes_json=_json(details),
        )
        session.add(entry)
        changed.append({"user": actor["username"], "action": action,
                        "table": obj.__tablename__, "record_id": record_id,
                        "details": details})
    if changed:
        session.info.setdefault("audit_email_events", []).extend(changed)


@event.listens_for(Session, "after_commit")
def _email_after_commit(session):
    events = session.info.pop("audit_email_events", [])
    if not events:
        return
    try:
        cfg = st.secrets.get("audit_email", {})
        host = cfg.get("host")
        sender = cfg.get("from_email", cfg.get("username"))
        recipient = cfg.get("to_email")
        if not all((host, sender, recipient)):
            return
        port = int(cfg.get("port", 587))
        msg = EmailMessage()
        msg["Subject"] = f"TURF HR — {len(events)} تغيير جديد"
        msg["From"] = sender
        msg["To"] = recipient
        lines = ["تم تسجيل تغييرات جديدة في TURF HR:", ""]
        for item in events[:50]:
            lines.append(f"• {item['user']} — {item['action']} — {item['table']} #{item['record_id']}")
        msg.set_content("\n".join(lines))
        if cfg.get("use_ssl", False):
            with smtplib.SMTP_SSL(host, port, timeout=12) as smtp:
                if cfg.get("username"):
                    smtp.login(cfg["username"], cfg.get("password", ""))
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=12) as smtp:
                smtp.starttls()
                if cfg.get("username"):
                    smtp.login(cfg["username"], cfg.get("password", ""))
                smtp.send_message(msg)
    except Exception:
        # The database commit has already succeeded; email trouble must not
        # make the user think the saved business record was rolled back.
        _log.exception("Audit email notification could not be sent")


@event.listens_for(Session, "after_rollback")
def _discard_uncommitted_email_events(session):
    session.info.pop("audit_email_events", None)
