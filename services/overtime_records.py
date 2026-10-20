"""Small, Streamlit-free helpers for keeping overtime reports accurate."""


def unique_overtime_records(records):
    """Return overtime rows once when an identical record was saved twice.

    Historic bulk saves could write the same employee/date/hours/rate/amount
    record more than once. That is not two work sessions, and summing it makes
    a two-hour entry look like four hours in reports. Only *exact* copies are
    removed here: different hours, rates, amounts, or notes remain separate
    audit records and are still counted.
    """
    unique = []
    seen = set()
    for record in records:
        key = (
            record.employee_id,
            record.project_id,
            record.date,
            round(float(record.hours or 0.0), 4),
            round(float(record.rate_per_hour or 0.0), 4),
            round(float(record.amount or 0.0), 2),
            (record.notes or '').strip(),
        )
        if key not in seen:
            seen.add(key)
            unique.append(record)
    return unique
