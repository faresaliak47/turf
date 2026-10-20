"""
Shared Arabic employee-name matching utilities.

Used by every place in the app that has to match a free-typed Arabic
employee name (smart-paste attendance, smart-paste bulk overtime, and
any future free-text employee lookup — e.g. Excel import, if it ever
needs to match employees by name instead of by code) against the
`Employee.name` values already stored in the database, WITHOUT ever
changing what's stored in the database.

Handles, on both sides of the comparison:
  - Arabic diacritics (tashkeel) — شَرِيف == شريف
  - Alef variants (أ / إ / آ / ٱ) unified to bare ا — أبو == ابو,
    أحمد == احمد
  - Tatweel/kashida (ـ) stripped
  - Extra / leading / trailing whitespace collapsed

Deliberately does NOT: change ي/ى or ة/ه endings, since the task only
asked for alef variants + "أبو"/"ابو" + spacing + diacritics, and going
further risks collapsing genuinely different names together.

The match function never guesses between multiple equally-plausible
candidates — an ambiguous input returns no match at all, matching the
project's requirement not to pick one at random.
"""
import re
import unicodedata

# Arabic diacritics (tashkeel) — fatha, damma, kasra, sukun, shadda,
# tanwin, and related combining marks.
_TASHKEEL_RE = re.compile(
    r'[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]'
)

# Tatweel / kashida (ـ), used purely for visual stretching, never
# semantically meaningful.
_TATWEEL_RE = re.compile(r'\u0640')

# Alef variants (أ إ آ ٱ) → bare alef (ا). This alone is what makes
# "أبو" and "ابو" compare equal, since أ → ا turns "أبو" into "ابو".
_ALEF_VARIANTS = str.maketrans({
    '\u0623': '\u0627',  # أ -> ا
    '\u0625': '\u0627',  # إ -> ا
    '\u0622': '\u0627',  # آ -> ا
    '\u0671': '\u0627',  # ٱ -> ا
})


def normalize_arabic_name(name: str) -> str:
    """Normalize an Arabic (or mixed) name for matching purposes only.

    Never call this on a value before saving it to the database — the
    original, user-entered name must always be preserved as-is; this
    normalized form exists purely to compare two names for equality.
    """
    if not name:
        return ''
    name = unicodedata.normalize('NFC', str(name))
    name = _TASHKEEL_RE.sub('', name)
    name = _TATWEEL_RE.sub('', name)
    name = name.translate(_ALEF_VARIANTS)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def build_employee_name_index(employees) -> dict:
    """Map normalized-name -> list of Employee objects.

    A list (not a single employee) per key on purpose: if two employees
    normalize to the same name, that key is inherently ambiguous and
    match_employee_by_name() below must refuse to auto-pick one of
    them.
    """
    index = {}
    for emp in employees:
        key = normalize_arabic_name(emp.name)
        if not key:
            continue
        index.setdefault(key, []).append(emp)
    return index


def match_employee_by_name(input_name: str, employees=None, name_index: dict = None):
    """
    Find the single employee whose stored name matches `input_name`,
    tolerating diacritics, alef variants, and extra/leading/trailing
    whitespace (see normalize_arabic_name).

    Pass either `employees` (a list of Employee objects — an index is
    built internally) or a pre-built `name_index` (from
    build_employee_name_index), e.g. when matching many names in a
    batch and the index should only be built once.

    Returns (employee_or_None, status) where status is one of:
      'matched'    — exactly one confident match found; use its
                     `.id` for the rest of the write path (never the
                     name itself).
      'ambiguous'  — more than one employee is a plausible match;
                     NEVER auto-picked, so the caller must treat this
                     as unresolved and ask a human to disambiguate
                     (e.g. by code) instead of guessing.
      'unmatched'  — no employee matches at all.
    """
    if name_index is None:
        name_index = build_employee_name_index(employees or [])

    norm_input = normalize_arabic_name(input_name)
    if not norm_input:
        return None, 'unmatched'

    # 1) Exact normalized match — the common case.
    exact = name_index.get(norm_input)
    if exact:
        if len(exact) == 1:
            return exact[0], 'matched'
        return None, 'ambiguous'

    # 2) Fuzzy fallback: one name fully contains the other (handles a
    #    partially-typed name, e.g. "شريف" matching "شريف أبو العزم").
    #    Only resolves if exactly ONE distinct employee qualifies —
    #    two or more candidates is treated as ambiguous, never guessed.
    candidates = {}
    for norm_name, emps in name_index.items():
        if norm_input in norm_name or norm_name in norm_input:
            for e in emps:
                candidates[e.id] = e

    if len(candidates) == 1:
        return next(iter(candidates.values())), 'matched'
    if len(candidates) > 1:
        return None, 'ambiguous'

    return None, 'unmatched'
