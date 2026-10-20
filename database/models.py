from sqlalchemy import (
    Column, Integer, String, Float, Date, Text, UniqueConstraint, Boolean,
    DateTime, ForeignKey, Index,
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


class Project(Base):
    """
    A project (site/job) that all operational data — employees, attendance,
    overtime, advances, payroll, expenses — can be scoped to. Added to
    support multiple concurrent projects inside a single installation; every
    other table gets a nullable `project_id` FK pointing here (see below and
    database/db.py's migration for how existing single-project data is
    backfilled into an automatically-created default project).
    """
    __tablename__ = 'projects'
    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(150), unique=True, nullable=False)
    code       = Column(String(30))
    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = 'users'
    id           = Column(Integer, primary_key=True, autoincrement=True)
    username     = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name    = Column(String(100), nullable=False)
    role         = Column(String(20), default='viewer')   # admin | hr | accountant | viewer
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=datetime.utcnow)
    # Remembers the last project this user had selected in the sidebar, so
    # it can be restored automatically the next time they log in (nullable —
    # existing users get this backfilled to NULL and simply fall back to the
    # default project on first login after the upgrade).
    last_project_id = Column(Integer, ForeignKey('projects.id'), nullable=True)


class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id = Column(Integer, primary_key=True, autoincrement=True)
    occurred_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    username = Column(String(100), nullable=False, default='غير معروف')
    action = Column(String(20), nullable=False)
    table_name = Column(String(100), nullable=False, index=True)
    record_id = Column(String(100))
    changes_json = Column(Text)


class Employee(Base):
    __tablename__ = 'employees'
    id          = Column(Integer, primary_key=True, autoincrement=True)
    code        = Column(String(20), nullable=False)
    name        = Column(String(100), nullable=False)
    job_title   = Column(String(100))
    department  = Column(String(100))
    salary      = Column(Float, default=0.0)
    daily_rate  = Column(Float, default=0.0)
    phone       = Column(String(20))
    national_id = Column(String(20))
    area        = Column(String(100))
    hire_date   = Column(Date)
    status      = Column(String(20), default='Active')
    # Which project this employee belongs to. Nullable at the DB level only
    # because SQLite can't retroactively add a NOT NULL constraint to an
    # existing table (see database/db.py) — every employee is always
    # assigned a project at the application layer, and the migration
    # backfills every pre-existing row into an auto-created default project.
    project_id  = Column(Integer, ForeignKey('projects.id'), index=True)
    __table_args__ = (
        UniqueConstraint('code', 'project_id', name='uq_employee_code_project'),
    )

    # ── Relationships ────────────────────────────────────────────────
    # cascade="all, delete-orphan" makes SQLAlchemy itself walk these
    # collections and delete the child rows whenever an Employee is
    # deleted through the ORM (session.delete(...)), so the delete
    # button in page_modules/employees.py can no longer leave orphaned
    # attendance/overtime/advance/payroll rows behind. This works
    # independently of whatever the underlying SQLite file's physical
    # schema looks like (see note in database/db.py about FK
    # enforcement on already-existing databases), so it protects data
    # integrity on both old and freshly-created databases.
    attendances = relationship(
        'Attendance', back_populates='employee',
        cascade='all, delete-orphan',
    )
    overtimes = relationship(
        'Overtime', back_populates='employee',
        cascade='all, delete-orphan',
    )
    advances = relationship(
        'Advance', back_populates='employee',
        cascade='all, delete-orphan',
    )
    discounts = relationship(
        'Discount', back_populates='employee',
        cascade='all, delete-orphan',
    )
    payroll_entries = relationship(
        'PayrollCache', back_populates='employee',
        cascade='all, delete-orphan',
    )


class Attendance(Base):
    __tablename__ = 'attendance'
    id              = Column(Integer, primary_key=True, autoincrement=True)
    employee_id     = Column(
        Integer, ForeignKey('employees.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    attendance_date = Column(Date, nullable=False, index=True)
    status          = Column(Integer, default=1, index=True)
    # Real headcount represented by this row (e.g. "5 عمال أشرف" -> 5).
    # Separate from `status`, which stays the 1-per-day attendance "credit"
    # used by payroll (services/payroll_service.py counts ROWS, not this
    # value, so payroll/day-credit logic is unaffected by this field).
    workers_count   = Column(Float, default=1.0)
    project_id      = Column(Integer, ForeignKey('projects.id'), index=True)
    __table_args__  = (
        UniqueConstraint('employee_id', 'attendance_date', 'project_id', name='uq_emp_date_project'),
        # Speeds up the very common "month + status" filter used by
        # payroll_service.calculate_payroll() / attendance_service /
        # the monthly attendance matrix, on top of the single-column
        # indexes above.
        Index('ix_attendance_date_status', 'attendance_date', 'status'),
    )

    employee = relationship('Employee', back_populates='attendances')


class Overtime(Base):
    __tablename__ = 'overtime'
    id           = Column(Integer, primary_key=True, autoincrement=True)
    employee_id  = Column(
        Integer, ForeignKey('employees.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    date         = Column(Date, nullable=False, index=True)
    hours        = Column(Float, default=0.0)
    rate_per_hour = Column(Float, default=0.0)
    amount       = Column(Float, default=0.0)
    notes        = Column(Text)
    project_id   = Column(Integer, ForeignKey('projects.id'), index=True)

    employee = relationship('Employee', back_populates='overtimes')


class Advance(Base):
    __tablename__ = 'advances'
    id          = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(
        Integer, ForeignKey('employees.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    date        = Column(Date, nullable=False, index=True)
    amount      = Column(Float, default=0.0)
    notes       = Column(Text)
    project_id  = Column(Integer, ForeignKey('projects.id'), index=True)

    employee = relationship('Employee', back_populates='advances')


class Discount(Base):
    """
    A salary discount/deduction applied to one employee for a given date.

    `discount_type` drives how `amount` (the final EGP value deducted from
    payroll) is computed at creation time — see services/discount_service.py:
      - 'amount':    a fixed EGP value entered directly by HR.
      - 'half_day':  half of the employee's daily rate (salary ÷ 30 ÷ 2,
                     or emp.daily_rate ÷ 2 when set).
      - 'hours':     `hours` × the employee's hourly rate (see
                     services/rates.py:calc_hourly_rate — the same formula
                     already used by Overtime, so a discounted hour and an
                     overtime hour are always priced consistently).

    `hourly_rate`/`daily_rate_snapshot` freeze the rate that was actually
    used at creation time, so a later change to the employee's salary
    doesn't silently rewrite the EGP value of a discount that's already
    been applied to a past payroll period.
    """
    __tablename__ = 'discounts'
    id             = Column(Integer, primary_key=True, autoincrement=True)
    employee_id    = Column(
        Integer, ForeignKey('employees.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    date           = Column(Date, nullable=False, index=True)
    discount_type  = Column(String(20), nullable=False, default='amount')  # amount | half_day | hours
    hours          = Column(Float, default=0.0)   # only meaningful when discount_type == 'hours'
    rate_snapshot  = Column(Float, default=0.0)   # hourly or daily rate used to compute `amount`, frozen at creation
    amount         = Column(Float, default=0.0)   # final EGP value deducted — always populated, read by payroll_service
    notes          = Column(Text)
    created_by     = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)
    project_id     = Column(Integer, ForeignKey('projects.id'), index=True)

    employee = relationship('Employee', back_populates='discounts')


class PayrollCache(Base):
    __tablename__ = 'payroll_cache'
    id              = Column(Integer, primary_key=True, autoincrement=True)
    employee_id     = Column(
        Integer, ForeignKey('employees.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    month           = Column(Integer, nullable=False)
    year            = Column(Integer, nullable=False)
    attendance_days = Column(Integer, default=0)
    daily_rate      = Column(Float, default=0.0)
    base_salary     = Column(Float, default=0.0)
    overtime        = Column(Float, default=0.0)
    advances        = Column(Float, default=0.0)
    discounts       = Column(Float, default=0.0)
    net_salary      = Column(Float, default=0.0)
    project_id      = Column(Integer, ForeignKey('projects.id'), index=True)
    __table_args__  = (UniqueConstraint('employee_id', 'month', 'year', name='uq_payroll'),)

    employee = relationship('Employee', back_populates='payroll_entries')


class Expense(Base):
    """
    Petty-cash expenses entered on the Expenses page (Smart Paste or the
    manual-entry form), excluding employee advances — those are tracked
    separately in `Advance`, which already has its own table and is tied
    into payroll.

    Previously these rows lived only in st.session_state and were wiped
    on every page refresh / Streamlit rerun. This table makes them
    durable across sessions and restarts.
    """
    __tablename__ = 'expenses'
    id          = Column(Integer, primary_key=True, autoincrement=True)
    date        = Column(Date, nullable=False, index=True)
    description = Column(String(255), nullable=False, default='مصروف')
    category    = Column(String(50), default='أخرى', index=True)
    amount      = Column(Float, default=0.0)
    notes       = Column(Text)
    created_at  = Column(DateTime, default=datetime.utcnow)
    project_id  = Column(Integer, ForeignKey('projects.id'), index=True)


class ReceivedFund(Base):
    """
    Income / petty-cash funding records (bank transfers, cash handed to
    the site, etc.) from the "صندوق الوارد" tab of the Expenses page.

    Stored for the same reason as `Expense`: without a table, the
    received-funds list reset on every refresh, which made the balance
    report on that page unreliable.
    """
    __tablename__ = 'received_funds'
    id         = Column(Integer, primary_key=True, autoincrement=True)
    date       = Column(Date, nullable=False, index=True)
    amount     = Column(Float, default=0.0)
    tax        = Column(Float, default=0.0)
    net_amount = Column(Float, default=0.0)
    source     = Column(String(100))
    notes      = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    project_id = Column(Integer, ForeignKey('projects.id'), index=True)


class CheckRecord(Base):
    """A project-scoped cheque and its related invoice/supporting files."""
    __tablename__ = 'check_records'
    id = Column(Integer, primary_key=True, autoincrement=True)
    check_number = Column(String(80), nullable=False, index=True)
    company = Column(String(180))
    invoice_number = Column(String(80))
    area = Column(String(120))
    settlement_number = Column(String(100))
    contract = Column(String(120))
    recipient = Column(String(150))
    receipt_date = Column(Date, index=True)
    check_date = Column(Date, nullable=False, index=True)
    amount = Column(Float, nullable=False, default=0.0)
    bank = Column(String(150))
    status = Column(String(40), nullable=False, default='تم الصرف', index=True)
    check_attachment = Column(String(500))
    invoice_attachment = Column(String(500))
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False, index=True)


class AccountantHandover(Base):
    """A dated handover of paperwork to the legal accountant."""
    __tablename__ = 'accountant_handovers'
    id = Column(Integer, primary_key=True, autoincrement=True)
    handover_date = Column(Date, nullable=False, index=True)
    accountant_name = Column(String(180), nullable=False)
    receipt_number = Column(String(100))
    papers_description = Column(Text, nullable=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False, index=True)
    attachments = relationship(
        'AccountantHandoverAttachment', back_populates='handover',
        cascade='all, delete-orphan',
    )


class AccountantHandoverAttachment(Base):
    """Receipt PDF or scanned papers attached to a handover."""
    __tablename__ = 'accountant_handover_attachments'
    id = Column(Integer, primary_key=True, autoincrement=True)
    handover_id = Column(Integer, ForeignKey('accountant_handovers.id', ondelete='CASCADE'), nullable=False, index=True)
    kind = Column(String(30), nullable=False)  # receipt | scanned_papers
    original_name = Column(String(255), nullable=False)
    file_path = Column(String(600), nullable=False)
    handover = relationship('AccountantHandover', back_populates='attachments')


class PlantSupplier(Base):
    """A plant supplier recorded separately for each project."""
    __tablename__ = 'plant_suppliers'
    id              = Column(Integer, primary_key=True, autoincrement=True)
    name            = Column(String(150), nullable=False)
    normalized_name = Column(String(180), nullable=False)
    project_id      = Column(Integer, ForeignKey('projects.id'), nullable=False, index=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    __table_args__  = (
        UniqueConstraint('normalized_name', 'project_id', name='uq_plant_supplier_name_project'),
    )


class PlantItem(Base):
    """A plant/item catalog, scoped to the selected project."""
    __tablename__ = 'plant_items'
    id              = Column(Integer, primary_key=True, autoincrement=True)
    name            = Column(String(150), nullable=False)
    normalized_name = Column(String(180), nullable=False)
    project_id      = Column(Integer, ForeignKey('projects.id'), nullable=False, index=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    __table_args__  = (
        UniqueConstraint('normalized_name', 'project_id', name='uq_plant_item_name_project'),
    )


class PlantDelivery(Base):
    """One dated supplier delivery imported from a message or entered manually."""
    __tablename__ = 'plant_deliveries'
    id          = Column(Integer, primary_key=True, autoincrement=True)
    supplier_id = Column(Integer, ForeignKey('plant_suppliers.id'), nullable=False, index=True)
    date        = Column(Date, nullable=False, index=True)
    notes       = Column(Text)
    source_text = Column(Text)
    project_id  = Column(Integer, ForeignKey('projects.id'), nullable=False, index=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    lines       = relationship('PlantDeliveryLine', back_populates='delivery', cascade='all, delete-orphan')
    supplier    = relationship('PlantSupplier')


class PlantDeliveryLine(Base):
    """Quantity of one plant item in a dated delivery."""
    __tablename__ = 'plant_delivery_lines'
    id                = Column(Integer, primary_key=True, autoincrement=True)
    delivery_id       = Column(Integer, ForeignKey('plant_deliveries.id', ondelete='CASCADE'), nullable=False, index=True)
    item_id           = Column(Integer, ForeignKey('plant_items.id'), nullable=False, index=True)
    item_name_snapshot = Column(String(150), nullable=False)
    quantity          = Column(Float, nullable=False, default=0.0)
    delivery          = relationship('PlantDelivery', back_populates='lines')
    item              = relationship('PlantItem')
