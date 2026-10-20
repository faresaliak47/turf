"""
Centralized SVG icon set — replaces raw emoji in the reusable UI
components (cards.py, layout.py) with clean, brand-colored line icons.

Design: every icon is a simple 24x24 stroke-based SVG using
stroke="currentColor", so it automatically takes on whatever CSS
`color` the surrounding element already sets (no per-call color
plumbing needed). Falls back to the original emoji untouched for any
icon not in the map below — so nothing breaks if a page uses an emoji
that isn't mapped yet.

Only cards.py and layout.py need to import this; every page_module
that calls section_card()/kpi_card()/render_topbar()/etc. picks up the
new icons automatically, with zero changes to any page_module file.
"""

_ICONS = {
    # Navigation / page icons
    "📊": '<line x1="6" y1="20" x2="6" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="18" y1="20" x2="18" y2="13"/>',
    "👥": '<circle cx="9" cy="8" r="3"/><path d="M4 20c0-3 2-5 5-5s5 2 5 5"/><circle cx="17" cy="9" r="2.3"/><path d="M15.2 20c0-2.4 1-4 3.3-4.2"/>',
    "📅": '<rect x="3" y="5" width="18" height="16" rx="2"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="8" y1="3" x2="8" y2="7"/><line x1="16" y1="3" x2="16" y2="7"/>',
    "⏱": '<circle cx="12" cy="12" r="9"/><line x1="12" y1="12" x2="12" y2="7"/><line x1="12" y1="12" x2="16" y2="14"/>',
    "💰": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.5"/>',
    "💼": '<rect x="3" y="8" width="18" height="12" rx="2"/><path d="M8 8V6a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="3" y1="13" x2="21" y2="13"/>',
    "📈": '<polyline points="4,17 10,11 14,15 20,7"/><polyline points="14,7 20,7 20,13"/>',
    "💵": '<rect x="3" y="7" width="18" height="10" rx="2"/><circle cx="12" cy="12" r="2.5"/>',
    "📋": '<rect x="6" y="4" width="12" height="17" rx="2"/><rect x="9" y="2" width="6" height="4" rx="1"/><line x1="9" y1="10" x2="15" y2="10"/><line x1="9" y1="14" x2="15" y2="14"/>',

    # Actions / status
    "🔐": '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "🔑": '<circle cx="8" cy="15" r="4"/><path d="M11 12 20 3"/><path d="M16 7 19 10"/>',
    "✅": '<circle cx="12" cy="12" r="9"/><polyline points="8,12.5 11,15.5 16,9"/>',
    "❌": '<circle cx="12" cy="12" r="9"/><line x1="9" y1="9" x2="15" y2="15"/><line x1="15" y1="9" x2="9" y2="15"/>',
    "⚠️": '<path d="M12 4 22 20H2Z"/><line x1="12" y1="10" x2="12" y2="15"/><circle cx="12" cy="18" r="0.6" fill="currentColor" stroke="none"/>',
    "🗑️": '<line x1="4" y1="7" x2="20" y2="7"/><path d="M6 7V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v2"/><path d="M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>',
    "➕": '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    "⚙️": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>',
    "🔍": '<circle cx="10" cy="10" r="6"/><line x1="15" y1="15" x2="20" y2="20"/>',
    "💡": '<path d="M9 18h6M10 22h4M12 2a6 6 0 0 0-3 11.2c.6.4 1 1.1 1 1.8v1h4v-1c0-.7.4-1.4 1-1.8A6 6 0 0 0 12 2Z"/>',
    "🏦": '<path d="M3 10 12 4l9 6"/><line x1="5" y1="10" x2="5" y2="19"/><line x1="10" y1="10" x2="10" y2="19"/><line x1="14" y1="10" x2="14" y2="19"/><line x1="19" y1="10" x2="19" y2="19"/><line x1="3" y1="21" x2="21" y2="21"/>',
    "🏢": '<rect x="5" y="3" width="14" height="18" rx="2"/><line x1="9" y1="8" x2="9" y2="8.01"/><line x1="15" y1="8" x2="15" y2="8.01"/><line x1="9" y1="12" x2="9" y2="12.01"/><line x1="15" y1="12" x2="15" y2="12.01"/><path d="M10 21v-4h4v4"/>',
    "🕐": '<circle cx="12" cy="12" r="9"/><line x1="12" y1="12" x2="12" y2="7"/><line x1="12" y1="12" x2="16" y2="14"/>',
    "🔔": '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4Z"/><path d="M10 21a2 2 0 0 0 4 0"/>',
    "➖": '<line x1="5" y1="12" x2="19" y2="12"/>',
    "👤": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.5-6 8-6s8 2 8 6"/>',
    "⏱⏱": '<circle cx="12" cy="12" r="9"/><line x1="12" y1="12" x2="12" y2="7"/><line x1="12" y1="12" x2="16" y2="14"/>',
    "📥": '<path d="M12 4v10"/><polyline points="8,10 12,14 16,10"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>',
    "📤": '<path d="M12 14V4"/><polyline points="8,8 12,4 16,8"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>',
    "✏️": '<path d="M4 20h4L19 9a2.1 2.1 0 0 0-3-3L5 17Z"/><line x1="14" y1="7" x2="17" y2="10"/>',
    "ℹ️": '<circle cx="12" cy="12" r="9"/><line x1="12" y1="11" x2="12" y2="16"/><circle cx="12" cy="8" r="0.6" fill="currentColor" stroke="none"/>',
    "🧠": '<path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8Z"/><path d="M18 15l.7 1.8 1.8.7-1.8.7L18 20l-.7-1.8-1.8-.7 1.8-.7Z"/>',
    "🔁": '<path d="M4 12a7 7 0 0 1 12-4.9L19 10"/><polyline points="19,5 19,10 14,10"/><path d="M20 12a7 7 0 0 1-12 4.9L5 14"/><polyline points="5,19 5,14 10,14"/>',
    "🏆": '<path d="M8 4h8v5a4 4 0 0 1-8 0Z"/><path d="M8 6H5a2 2 0 0 0 0 4h3M16 6h3a2 2 0 0 1 0 4h-3"/><line x1="12" y1="13" x2="12" y2="17"/><line x1="8" y1="20" x2="16" y2="20"/>',
    "📉": '<polyline points="4,7 10,13 14,9 20,17"/><polyline points="14,17 20,17 20,11"/>',
    "📌": '<path d="M9 4h6l-1 6 3 3H7l3-3Z"/><line x1="12" y1="13" x2="12" y2="21"/>',
    "📝": '<path d="M6 3h9l4 4v14H6Z"/><polyline points="15,3 15,7 19,7"/><line x1="9" y1="12" x2="16" y2="12"/><line x1="9" y1="16" x2="14" y2="16"/>',
    "🗂️": '<rect x="4" y="4" width="7" height="7" rx="1"/><rect x="13" y="4" width="7" height="7" rx="1"/><rect x="4" y="13" width="7" height="7" rx="1"/><rect x="13" y="13" width="7" height="7" rx="1"/>',
    "🧮": '<rect x="5" y="3" width="14" height="18" rx="2"/><rect x="8" y="6" width="8" height="3"/><line x1="9" y1="13" x2="9" y2="13.01"/><line x1="12" y1="13" x2="12" y2="13.01"/><line x1="15" y1="13" x2="15" y2="13.01"/><line x1="9" y1="17" x2="9" y2="17.01"/><line x1="12" y1="17" x2="12" y2="17.01"/><line x1="15" y1="17" x2="15" y2="17.01"/>',
    "🧾": '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2Z"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="9" y1="12" x2="15" y2="12"/>',
    "🏧": '<rect x="3" y="6" width="18" height="12" rx="2"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="7" y1="15" x2="11" y2="15"/>',
    "⚡": '<path d="M13 3 5 13h6l-1 8 8-10h-6Z"/>',
    "📂": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
    "📄": '<path d="M6 3h9l4 4v14H6Z"/><polyline points="15,3 15,7 19,7"/>',
    "⏭️": '<polygon points="5,5 13,12 5,19"/><polygon points="12,5 20,12 12,19"/>',
    "📭": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M3 8l9 6 9-6"/>',
}


def render_icon(icon: str, size: int = 18, extra_style: str = "") -> str:
    """
    Return an inline-HTML snippet for `icon`: an SVG line-icon if it's in
    the map above (inherits color via currentColor), otherwise the
    original emoji wrapped in a sized span (safe fallback — never breaks
    a caller passing an icon we haven't mapped yet).
    """
    icon = (icon or "").strip()
    path = _ICONS.get(icon)
    if not path:
        # No emojis in the UI: unmapped icons fall back to a neutral dot.
        return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="currentColor" '
                f'style="display:block;{extra_style}"><circle cx="12" cy="12" r="3"/></svg>')
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round" style="display:block;{extra_style}">{path}</svg>'
    )
