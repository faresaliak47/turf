"""Smart parsing and project-scoped records for plant supplier deliveries."""
import re
import unicodedata
from datetime import datetime

from sqlalchemy import func
from database.db import get_db
from database.models import PlantDelivery, PlantDeliveryLine, PlantItem, PlantSupplier


_DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')
_DATE_RE = re.compile(r'(?<!\d)(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})(?!\d)')
_QUANTITY_RE = re.compile(r'^\s*(\d+(?:[.,]\d+)?)\s+(.+?)\s*$')
_ARABIC_MARKS = re.compile(r'[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]')


def normalize_name(value: str) -> str:
    """Normalize harmless Arabic spelling/spacing differences for exact matching."""
    value = unicodedata.normalize('NFKC', str(value or '')).translate(_DIGITS)
    value = _ARABIC_MARKS.sub('', value).replace('ـ', '')
    value = value.translate(str.maketrans({
        'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ى': 'ي',
        'ة': 'ه', 'ؤ': 'و', 'ئ': 'ي',
    }))
    value = re.sub(r'[\u0640\s\-_.,،:؛()\[\]{}]+', ' ', value)
    return value.strip().casefold()


def parse_delivery_text(text: str) -> dict:
    """Parse a WhatsApp delivery note with a date, a ``من`` supplier line,
    and quantity/name lines. Dates are interpreted as DD/MM/YYYY.
    """
    result = {'date': None, 'supplier': '', 'items': [], 'errors': [], 'notes': ''}
    items_by_name = {}
    lines = [line.strip().lstrip('•*- ').strip() for line in (text or '').splitlines()]

    for line in lines:
        if not line:
            continue
        normalized_digits = line.translate(_DIGITS)
        date_match = _DATE_RE.search(normalized_digits)
        if date_match:
            day, month, year = map(int, date_match.groups())
            if year < 100:
                year += 2000
            try:
                result['date'] = datetime(year, month, day).date()
            except ValueError:
                result['errors'].append(f'تاريخ غير صحيح: {date_match.group(0)}')
            line = (normalized_digits[:date_match.start()] + ' ' + normalized_digits[date_match.end():]).strip(' -—:')
            if not line:
                continue

        supplier_match = re.match(r'^من\s*[:：]?\s*(.+)$', line)
        if supplier_match:
            result['supplier'] = supplier_match.group(1).strip(' :：')
            continue

        if re.search(r'توريد\s+يوم|توريد\s+بتاريخ', line):
            continue

        quantity_match = _QUANTITY_RE.match(line.translate(_DIGITS))
        if quantity_match:
            quantity = float(quantity_match.group(1).replace(',', '.'))
            item_name = quantity_match.group(2).strip(' -—:؛,،')
            if quantity <= 0 or not item_name:
                result['errors'].append(f'تعذر فهم السطر: {line}')
                continue
            key = normalize_name(item_name)
            if key in items_by_name:
                items_by_name[key]['quantity'] += quantity
            else:
                items_by_name[key] = {'name': item_name, 'quantity': quantity}
        elif line:
            result['errors'].append(f'السطر غير مفهوم: {line}')

    result['items'] = list(items_by_name.values())
    if not result['date']:
        result['errors'].append('أضف تاريخ التوريد بصيغة يوم/شهر/سنة، مثل 03/10/2026.')
    if not result['supplier']:
        result['errors'].append('أضف اسم المورد في سطر يبدأ بكلمة «من»، مثل: من محمد مبروك.')
    if not result['items']:
        result['errors'].append('لم أجد أصنافًا. اكتب كل صنف في سطر بالشكل: الكمية ثم اسم الصنف.')
    return result


def preview_delivery(parsed: dict, project_id: int) -> dict:
    """Mark supplier/items as existing or new without changing the database."""
    db = get_db()
    try:
        supplier_key = normalize_name(parsed.get('supplier'))
        supplier = db.query(PlantSupplier).filter(
            PlantSupplier.project_id == project_id,
            PlantSupplier.normalized_name == supplier_key,
        ).first()
        item_map = {
            item.normalized_name: item
            for item in db.query(PlantItem).filter(PlantItem.project_id == project_id).all()
        }
        items = []
        for row in parsed.get('items', []):
            item = item_map.get(normalize_name(row['name']))
            items.append({
                **row,
                'existing': bool(item),
                'catalog_name': item.name if item else row['name'],
            })
        return {
            'supplier_existing': bool(supplier),
            'supplier_catalog_name': supplier.name if supplier else parsed.get('supplier', ''),
            'items': items,
        }
    finally:
        db.close()


def save_delivery(parsed: dict, project_id: int) -> int:
    """Create/reuse supplier and item catalog entries and save dated quantities."""
    if parsed.get('errors'):
        raise ValueError('لا يمكن حفظ النص قبل تصحيح الأخطاء الظاهرة في المعاينة.')
    db = get_db()
    try:
        supplier_key = normalize_name(parsed['supplier'])
        supplier = db.query(PlantSupplier).filter(
            PlantSupplier.project_id == project_id,
            PlantSupplier.normalized_name == supplier_key,
        ).first()
        if not supplier:
            supplier = PlantSupplier(
                name=parsed['supplier'].strip(), normalized_name=supplier_key,
                project_id=project_id,
            )
            db.add(supplier)
            db.flush()

        delivery = PlantDelivery(
            supplier_id=supplier.id, date=parsed['date'], project_id=project_id,
            source_text=parsed.get('source_text', ''), notes=parsed.get('notes', ''),
        )
        db.add(delivery)
        db.flush()

        for row in parsed['items']:
            key = normalize_name(row['name'])
            item = db.query(PlantItem).filter(
                PlantItem.project_id == project_id,
                PlantItem.normalized_name == key,
            ).first()
            if not item:
                item = PlantItem(name=row['name'].strip(), normalized_name=key, project_id=project_id)
                db.add(item)
                db.flush()
            db.add(PlantDeliveryLine(
                delivery_id=delivery.id, item_id=item.id,
                item_name_snapshot=item.name, quantity=float(row['quantity']),
            ))
        db.commit()
        return delivery.id
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def add_supplier(name: str, project_id: int) -> tuple[bool, str]:
    """Add a supplier to the selected project's catalog without a delivery."""
    name = str(name or '').strip()
    key = normalize_name(name)
    if not name:
        return False, 'اكتب اسم المورد أولاً.'
    if not key:
        return False, 'اسم المورد غير صالح.'
    db = get_db()
    try:
        existing = db.query(PlantSupplier).filter(
            PlantSupplier.project_id == project_id,
            PlantSupplier.normalized_name == key,
        ).first()
        if existing:
            return False, f'المورد «{existing.name}» مسجل بالفعل في هذا المشروع.'
        db.add(PlantSupplier(name=name, normalized_name=key, project_id=project_id))
        db.commit()
        return True, f'تمت إضافة المورد «{name}» إلى القائمة.'
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def list_delivery_rows(project_id: int, date_from=None, date_to=None) -> list[dict]:
    """Flatten delivery lines for the ledger and Excel report."""
    db = get_db()
    try:
        query = (
            db.query(PlantDelivery, PlantSupplier, PlantDeliveryLine, PlantItem)
            .join(PlantSupplier, PlantDelivery.supplier_id == PlantSupplier.id)
            .join(PlantDeliveryLine, PlantDeliveryLine.delivery_id == PlantDelivery.id)
            .join(PlantItem, PlantDeliveryLine.item_id == PlantItem.id)
            .filter(PlantDelivery.project_id == project_id)
        )
        if date_from:
            query = query.filter(PlantDelivery.date >= date_from)
        if date_to:
            query = query.filter(PlantDelivery.date <= date_to)
        query = query.order_by(PlantDelivery.date.desc(), PlantDelivery.id.desc(), PlantDeliveryLine.id)
        return [{
            'delivery_id': delivery.id,
            'date': delivery.date,
            'supplier': supplier.name,
            'item': line.item_name_snapshot or item.name,
            'quantity': line.quantity,
            'notes': delivery.notes or '',
        } for delivery, supplier, line, item in query.all()]
    finally:
        db.close()


def list_catalog(project_id: int) -> tuple[list[dict], list[dict]]:
    db = get_db()
    try:
        suppliers = db.query(PlantSupplier).filter(
            PlantSupplier.project_id == project_id
        ).order_by(PlantSupplier.name).all()
        items = db.query(PlantItem).filter(
            PlantItem.project_id == project_id
        ).order_by(PlantItem.name).all()
        supplier_counts = dict(db.query(
            PlantDelivery.supplier_id, func.count(PlantDelivery.id)
        ).filter(
            PlantDelivery.project_id == project_id
        ).group_by(PlantDelivery.supplier_id).all())
        item_quantities = dict(db.query(
            PlantDeliveryLine.item_id, func.sum(PlantDeliveryLine.quantity)
        ).join(
            PlantDelivery, PlantDelivery.id == PlantDeliveryLine.delivery_id
        ).filter(
            PlantDelivery.project_id == project_id
        ).group_by(PlantDeliveryLine.item_id).all())
        return (
            [{'المورد': row.name, 'عدد التوريدات': supplier_counts.get(row.id, 0)} for row in suppliers],
            [{'الصنف': row.name, 'إجمالي الوارد': item_quantities.get(row.id, 0) or 0} for row in items],
        )
    finally:
        db.close()
