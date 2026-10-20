"""
Daily attendance reminder notifications (isolated module).

One SEPARATE notification per ACTIVE project, every working day at the
configured time (default 09:00). Each notification is:
  * stored in the `attendance_reminders` table (read/unread survives restarts), and
  * shown as a Windows desktop toast (only when it is newly created).

Nothing here changes existing logic: it only READS the projects table and
owns two new tables (`attendance_reminders`, `reminder_settings`), created
on first use via ensure_tables().

Duplicates: a UNIQUE(project_id, reminder_date) constraint guarantees a
project is never reminded twice on the same day, no matter how many times
the scheduler ticks or the app is restarted. If the app was closed at the
reminder time, the first tick after it opens creates the missed reminders
once (catch-up).

Delivery mode: an in-process scheduler thread (start_scheduler()), so
reminders fire while the app is open. See app.py for where it is started.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from datetime import datetime, date

from sqlalchemy import (Column, Integer, String, Boolean, Date, DateTime,
                        ForeignKey, UniqueConstraint)
from sqlalchemy.exc import IntegrityError

from database.db import get_db, engine
from database.models import Base, Project
from services.reminder_rules import (
    DEFAULT_ENABLED, DEFAULT_TIME, DEFAULT_WORKING_DAYS,
    parse_days, should_generate,
)

TICK_SECONDS = 30
TOAST_TITLE = "تذكير الحضور"


# ── Models (new tables only) ────────────────────────────────────────────
class AttendanceReminder(Base):
    __tablename__ = "attendance_reminders"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    # ON DELETE CASCADE: deleting a project (existing feature) must never be blocked
    # by its reminder rows, since SQLite foreign keys are enforced in this app.
    project_id    = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    project_name  = Column(String(150), nullable=False)   # snapshot at creation time
    message       = Column(String(300), nullable=False)
    reminder_date = Column(Date, nullable=False, index=True)
    created_at    = Column(DateTime, default=datetime.now)  # local time
    is_read       = Column(Boolean, default=False, nullable=False)
    __table_args__ = (
        UniqueConstraint("project_id", "reminder_date", name="uq_reminder_project_date"),
    )


class ReminderSetting(Base):
    __tablename__ = "reminder_settings"
    key   = Column(String(50), primary_key=True)
    value = Column(String(200), nullable=False)


_tables_ready = False
_tables_lock = threading.Lock()


def ensure_tables():
    """Create the two new tables if missing (no change to existing tables)."""
    global _tables_ready
    if _tables_ready:
        return
    with _tables_lock:
        if not _tables_ready:
            Base.metadata.create_all(
                bind=engine,
                tables=[AttendanceReminder.__table__, ReminderSetting.__table__],
            )
            _tables_ready = True


# ── Settings ────────────────────────────────────────────────────────────
def get_settings() -> dict:
    ensure_tables()
    db = get_db()
    try:
        rows = {r.key: r.value for r in db.query(ReminderSetting).all()}
    finally:
        db.close()
    enabled = rows.get("enabled")
    days = parse_days(rows["working_days"]) if "working_days" in rows else list(DEFAULT_WORKING_DAYS)
    return {
        "enabled": DEFAULT_ENABLED if enabled is None else enabled == "1",
        "time": rows.get("time", DEFAULT_TIME),
        "working_days": days,
    }


def save_settings(enabled: bool, time_str: str, working_days) -> None:
    ensure_tables()
    values = {
        "enabled": "1" if enabled else "0",
        "time": time_str,
        "working_days": ",".join(str(d) for d in parse_days(working_days)),
    }
    db = get_db()
    try:
        for k, v in values.items():
            row = db.query(ReminderSetting).filter(ReminderSetting.key == k).first()
            if row:
                row.value = v
            else:
                db.add(ReminderSetting(key=k, value=v))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── Generation ──────────────────────────────────────────────────────────
def generate_due_reminders(now: datetime | None = None) -> list[dict]:
    """Create today's missing reminders (one per active project) if due.
    Returns only the NEWLY created ones (so the caller toasts each once)."""
    ensure_tables()
    now = now or datetime.now()
    s = get_settings()
    if not should_generate(now, s["enabled"], s["time"], s["working_days"]):
        return []

    today = now.date()
    created: list[dict] = []
    db = get_db()
    try:
        projects = db.query(Project).filter(
            (Project.is_active == True) | (Project.is_active.is_(None))  # noqa: E712
        ).order_by(Project.name).all()
        done_ids = {
            r.project_id for r in
            db.query(AttendanceReminder.project_id).filter(AttendanceReminder.reminder_date == today).all()
        }
        for p in projects:
            if p.id in done_ids:
                continue
            row = AttendanceReminder(
                project_id=p.id,
                project_name=p.name,
                message=f"تذكير: سجّل الحضور لمشروع ({p.name})",
                reminder_date=today,
                created_at=now,
                is_read=False,
            )
            db.add(row)
            try:
                db.commit()
            except IntegrityError:      # another tick/instance got there first
                db.rollback()
                continue
            created.append({"id": row.id, "project_id": p.id,
                            "project_name": p.name, "message": row.message})
    finally:
        db.close()
    return created


# ── Reading / read-state (used by the top-bar bell) ─────────────────────
def _fmt_created(dt: datetime) -> str:
    if dt is None:
        return ""
    return dt.strftime("%H:%M") if dt.date() == date.today() else dt.strftime("%Y-%m-%d %H:%M")


def list_notifications(limit: int = 15) -> list[dict]:
    """Newest first. Only users who can open the attendance screen
    (existing permission: admin / hr) see them."""
    try:
        from services.auth import can_access
        if not can_access("attendance"):
            return []
    except Exception:
        return []
    ensure_tables()
    db = get_db()
    try:
        rows = (db.query(AttendanceReminder)
                .order_by(AttendanceReminder.created_at.desc(), AttendanceReminder.id.desc())
                .limit(limit).all())
        return [{
            "id": r.id, "project_id": r.project_id, "project_name": r.project_name,
            "message": r.message, "created_at": _fmt_created(r.created_at),
            "is_read": bool(r.is_read),
        } for r in rows]
    finally:
        db.close()


def mark_read(notification_id: int) -> None:
    ensure_tables()
    db = get_db()
    try:
        db.query(AttendanceReminder).filter(AttendanceReminder.id == notification_id) \
            .update({"is_read": True})
        db.commit()
    finally:
        db.close()


def mark_all_read() -> None:
    ensure_tables()
    db = get_db()
    try:
        db.query(AttendanceReminder).filter(AttendanceReminder.is_read == False) \
            .update({"is_read": True})  # noqa: E712
        db.commit()
    finally:
        db.close()


# ── Desktop toast (Windows) ─────────────────────────────────────────────
_PS_TOAST = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$t = $xml.GetElementsByTagName('text')
$t.Item(0).AppendChild($xml.CreateTextNode($env:HRPRO_TOAST_TITLE)) | Out-Null
$t.Item(1).AppendChild($xml.CreateTextNode($env:HRPRO_TOAST_MSG)) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
$appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
"""


def show_toast(title: str, message: str) -> bool:
    """Show a Windows toast. Returns False (silently) on other platforms or
    on any failure — the in-app notification is the source of truth."""
    if sys.platform != "win32":
        return False
    try:
        env = dict(os.environ, HRPRO_TOAST_TITLE=title, HRPRO_TOAST_MSG=message)
        subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
             "-Command", _PS_TOAST],
            env=env, creationflags=0x08000000,  # CREATE_NO_WINDOW
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as e:
        print(f"[notifications] toast failed: {e}")
        return False


# ── Scheduler ───────────────────────────────────────────────────────────
_scheduler_started = False
_scheduler_lock = threading.Lock()


def _tick():
    for n in generate_due_reminders():
        show_toast(TOAST_TITLE, n["message"])   # one toast per project


def _loop():
    stop = threading.Event()
    while not stop.wait(0):          # first tick immediately = catch-up on launch
        try:
            _tick()
        except Exception as e:
            print(f"[notifications] tick failed: {e}")
        stop.wait(TICK_SECONDS)


def start_scheduler() -> None:
    """Start the background scheduler once per process (safe to call on
    every Streamlit rerun)."""
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        ensure_tables()
        threading.Thread(target=_loop, name="attendance-reminders", daemon=True).start()
        _scheduler_started = True
