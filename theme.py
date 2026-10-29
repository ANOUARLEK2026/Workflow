"""theme.py - design system for منظّم الفريق.

Everything visual that is *global* lives here:
  * light / dark palettes (vibrant indigo-violet-pink family)
  * font loading (drop Cairo / Tajawal .ttf files into ./fonts to use them)
  * vector icon set drawn with QPainter (crisp at any DPI, theme aware)
  * the application stylesheet (QSS) built from the active palette
  * small paint helpers (soft layered shadows, colour mixing)
"""
from __future__ import annotations

import math
import re
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QObject, Signal, QPointF, QRectF
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QPainter, QPen, QBrush, QPixmap,
                           QLinearGradient, QPainterPath, QPolygonF, QIcon)

# --------------------------------------------------------------------------- palettes
LIGHT = dict(
    name='light',
    bg0='#F3F5FF', bg1='#FAF3FF',
    surface='#FFFFFF', surface_alt='#F6F7FE',
    border='#E4E7F7', border_strong='#C7CCEB',
    text='#1B1E4B', text_muted='#6A6F96', text_faint='#A0A5C6',
    primary='#6366F1', primary_dark='#4338CA', primary_soft='#ECEEFF', primary_soft2='#DDE0FF',
    accent='#8B5CF6', pink='#EC4899', cyan='#06B6D4',
    success='#10B981', warning='#F59E0B', danger='#F43F5E', info='#0EA5E9',
    input_bg='#FBFBFF', tooltip_bg='#1B1E4B', tooltip_fg='#FFFFFF', scroll='#9AA3D6',
    shadow='#4338CA', shadow_alpha=0.20,
    glow_a='#6366F1', glow_b='#EC4899', glow_alpha=0.16,
    hero_a='#4F46E5', hero_b='#7C3AED', hero_c='#DB2777',
)
DARK = dict(
    name='dark',
    bg0='#0B1020', bg1='#1A1236',
    surface='#161B33', surface_alt='#1D2342',
    border='#2A3157', border_strong='#3B4375',
    text='#ECEEFF', text_muted='#9AA2CF', text_faint='#6B7399',
    primary='#818CF8', primary_dark='#A5B4FC', primary_soft='#252B55', primary_soft2='#313970',
    accent='#A78BFA', pink='#F472B6', cyan='#22D3EE',
    success='#34D399', warning='#FBBF24', danger='#FB7185', info='#38BDF8',
    input_bg='#10152B', tooltip_bg='#ECEEFF', tooltip_fg='#1B1E4B', scroll='#5F6AA8',
    shadow='#000000', shadow_alpha=0.55,
    glow_a='#6366F1', glow_b='#EC4899', glow_alpha=0.22,
    hero_a='#4F46E5', hero_b='#7C3AED', hero_c='#DB2777',
)

ACCENTS = {   # name: (primary, accent, glow, (hero a, b, c))
    'aurora': ('#6366F1', '#8B5CF6', '#EC4899', ('#4F46E5', '#7C3AED', '#DB2777')),
    'ocean': ('#0EA5E9', '#6366F1', '#06B6D4', ('#0284C7', '#2563EB', '#7C3AED')),
    'sunset': ('#F97316', '#EC4899', '#F43F5E', ('#F59E0B', '#F43F5E', '#9333EA')),
    'forest': ('#10B981', '#0EA5E9', '#34D399', ('#059669', '#0D9488', '#2563EB')),
}
ACCENT_LABELS = {'aurora': 'الشفق', 'ocean': 'المحيط', 'sunset': 'الغروب', 'forest': 'الغابة'}
_state = {'accent': 'aurora'}

P: dict = dict(LIGHT)          # live palette - mutated in place, so `from theme import P` stays valid
_ICONS: dict = {}              # paths of generated png icons used by the stylesheet


class _Signals(QObject):
    changed = Signal()         # emitted after the palette / stylesheet changed


signals = _Signals()


def mode() -> str:
    return P['name']


# --------------------------------------------------------------------------- colour helpers
def qc(color, alpha: float | None = None) -> QColor:
    """QColor from anything, with optional alpha in 0..1."""
    c = QColor(color)
    if alpha is not None:
        c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


def mix(a, b, t: float) -> QColor:
    """Linear blend of two colours (alpha included)."""
    a, b = QColor(a), QColor(b)
    t = max(0.0, min(1.0, t))
    return QColor.fromRgbF(a.redF() + (b.redF() - a.redF()) * t,
                           a.greenF() + (b.greenF() - a.greenF()) * t,
                           a.blueF() + (b.blueF() - a.blueF()) * t,
                           a.alphaF() + (b.alphaF() - a.alphaF()) * t)


def paint_shadow(p: QPainter, rect: QRectF, radius: float, color, spread: int = 14, dy: float = 6.0):
    """Soft layered drop shadow painted *around* `rect` (no QGraphicsEffect needed, so it is cheap
    and safe to use on cards that contain tables). `color.alphaF()` is the strength at the edge."""
    color = QColor(color)
    total = color.alphaF()
    if total <= 0:
        return
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(spread, 0, -1):
        fall = (1.0 - (i - 1) / spread) ** 2
        c = QColor(color)
        c.setAlphaF(min(1.0, total * 3.0 / spread * fall))
        p.setBrush(c)
        p.drawRoundedRect(rect.translated(0, dy).adjusted(-i, -i, i, i), radius + i, radius + i)
    p.restore()


# --------------------------------------------------------------------------- semantic colours
STATUS_KEYS = {'مجدولة': 'scheduled', 'قيد التنفيذ': 'progress', 'منجزة': 'done', 'ملغاة': 'cancel'}
_STATUS_BASE = {
    'scheduled': '#6366F1',   # indigo
    'progress': '#F59E0B',    # amber
    'done': '#10B981',        # emerald
    'cancel': '#94A3B8',      # slate
    'late': '#F43F5E',        # rose
    'ontime': '#0EA5E9',      # sky
}


def status_colors(key: str):
    """(foreground, soft background, dot) for a status key."""
    base = QColor(_STATUS_BASE.get(key, '#6366F1'))
    dark = P['name'] == 'dark'
    fg = base.lighter(125) if dark else base.darker(135)
    bg = QColor(base)
    bg.setAlphaF(0.22 if dark else 0.13)
    return fg, bg, base


def priority_colors(v: int):
    v = int(v)
    if v <= 3:
        return QColor('#34D399'), QColor('#10B981')
    if v <= 6:
        return QColor('#FBBF24'), QColor('#F59E0B')
    if v <= 8:
        return QColor('#FB923C'), QColor('#F97316')
    return QColor('#FB7185'), QColor('#F43F5E')


_AVATARS = [('#6366F1', '#8B5CF6'), ('#0EA5E9', '#06B6D4'), ('#10B981', '#14B8A6'), ('#F59E0B', '#F97316'),
            ('#EC4899', '#F43F5E'), ('#8B5CF6', '#D946EF'), ('#14B8A6', '#0EA5E9'), ('#F43F5E', '#FB923C')]


def avatar_gradient(name: str):
    i = sum(ord(ch) for ch in (name or '?')) % len(_AVATARS)
    return QColor(_AVATARS[i][0]), QColor(_AVATARS[i][1])


# --------------------------------------------------------------------------- fonts
PREFERRED_FONTS = ['Cairo', 'Tajawal', 'IBM Plex Sans Arabic', 'Noto Sans Arabic',
                   'Segoe UI Variable Text', 'Segoe UI', 'Tahoma', 'Arial']


def setup_fonts(app, base_dir) -> str:
    """Load optional fonts from ./fonts and set the application font (first available wins)."""
    fdir = Path(base_dir) / 'fonts'
    if fdir.is_dir():
        for f in sorted(list(fdir.glob('*.ttf')) + list(fdir.glob('*.otf'))):
            QFontDatabase.addApplicationFont(str(f))
    available = set(QFontDatabase.families())
    chosen = [f for f in PREFERRED_FONTS if f in available] or [app.font().family()]
    font = QFont(chosen[0])
    try:
        font.setFamilies(chosen)
    except Exception:
        pass
    font.setPointSizeF(10.0)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)
    return chosen[0]


# --------------------------------------------------------------------------- vector icons (24x24 grid)
def _poly(p, pts):
    p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in pts]))


def _line(p, x1, y1, x2, y2):
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _rrect(p, x, y, w, h, r):
    p.drawRoundedRect(QRectF(x, y, w, h), r, r)


def _circ(p, cx, cy, r):
    p.drawEllipse(QPointF(cx, cy), r, r)


def _i_plus(p): _line(p, 12, 5, 12, 19); _line(p, 5, 12, 19, 12)
def _i_edit(p): _poly(p, [(15.5, 4), (20, 8.5), (8.5, 20), (3.5, 20.5), (4, 15.5), (15.5, 4)]); _line(p, 13, 6.5, 17.5, 11)
def _i_check(p): _poly(p, [(5, 12.5), (10, 17.5), (19, 7)])
def _i_check_circle(p): _circ(p, 12, 12, 9); _poly(p, [(7.8, 12.3), (10.8, 15.3), (16.3, 9.3)])
def _i_clock(p): _circ(p, 12, 12, 9); _poly(p, [(12, 7), (12, 12), (15.5, 14)])
def _i_alert(p): _poly(p, [(12, 3.5), (21.5, 20), (2.5, 20), (12, 3.5)]); _line(p, 12, 9.5, 12, 14); _line(p, 12, 17.2, 12, 17.3)
def _i_tasks(p): _rrect(p, 5, 4.5, 14, 17, 2.5); _rrect(p, 9, 2.5, 6, 4, 1.5); _poly(p, [(8.5, 13.5), (11, 16), (15.5, 10.5)])
def _i_calendar(p): _rrect(p, 3.5, 5, 17, 15.5, 3); _line(p, 3.5, 10, 20.5, 10); _line(p, 8, 3, 8, 7); _line(p, 16, 3, 16, 7)
def _i_archive(p): _rrect(p, 3, 4, 18, 4.5, 1.2); _poly(p, [(5, 8.5), (5, 19.5), (19, 19.5), (19, 8.5)]); _line(p, 10, 12.5, 14, 12.5)
def _i_trash(p): _line(p, 4, 7, 20, 7); _poly(p, [(6, 7), (7, 20), (17, 20), (18, 7)]); _poly(p, [(9, 7), (9, 4), (15, 4), (15, 7)]); _line(p, 10, 11, 10, 16); _line(p, 14, 11, 14, 16)
def _i_copy(p): _rrect(p, 9, 9, 11, 11, 2.2); _poly(p, [(9, 15), (4, 15), (4, 4), (15, 4), (15, 9)])
def _i_download(p): _poly(p, [(7, 10.5), (12, 15.5), (17, 10.5)]); _line(p, 12, 3.5, 12, 15.5); _line(p, 4.5, 20, 19.5, 20)
def _i_chev_l(p): _poly(p, [(15, 5), (8, 12), (15, 19)])
def _i_chev_r(p): _poly(p, [(9, 5), (16, 12), (9, 19)])
def _i_chev_d(p): _poly(p, [(5, 9), (12, 16), (19, 9)])
def _i_chev_u(p): _poly(p, [(5, 15), (12, 8), (19, 15)])
def _i_search(p): _circ(p, 11, 11, 6.5); _line(p, 16, 16, 21, 21)
def _i_chart(p): _line(p, 6, 20, 6, 12); _line(p, 12, 20, 12, 5); _line(p, 18, 20, 18, 9)
def _i_file(p): _poly(p, [(6, 3), (14, 3), (19, 8), (19, 21), (6, 21), (6, 3)]); _poly(p, [(14, 3), (14, 8), (19, 8)])
def _i_doc(p): _i_file(p); _line(p, 9.5, 13, 15.5, 13); _line(p, 9.5, 16.5, 15.5, 16.5)
def _i_sheet(p): _i_file(p); _line(p, 9, 13, 16, 13); _line(p, 9, 17, 16, 17); _line(p, 12.5, 11, 12.5, 19)


def _i_users(p):
    _circ(p, 9, 8, 3.5)
    a = QPainterPath(); a.moveTo(2.5, 20); a.cubicTo(2.5, 13.5, 15.5, 13.5, 15.5, 20); p.drawPath(a)
    _circ(p, 17.5, 9, 2.5)
    b = QPainterPath(); b.moveTo(17.5, 14.2); b.cubicTo(20.5, 14.2, 22, 16, 22, 19); p.drawPath(b)


def _i_restore(p):
    p.drawArc(QRectF(5, 5, 14, 14), 90 * 16, 250 * 16)
    _poly(p, [(14.5, 2.5), (12, 5), (14.5, 7.5)])


def _i_moon(p):
    a = QPainterPath(); a.addEllipse(QPointF(12, 12), 8.5, 8.5)
    b = QPainterPath(); b.addEllipse(QPointF(16.5, 8), 7, 7)
    p.setBrush(p.pen().color()); p.drawPath(a.subtracted(b)); p.setBrush(Qt.BrushStyle.NoBrush)


def _i_sun(p):
    _circ(p, 12, 12, 4)
    for i in range(8):
        a = i * math.pi / 4
        _line(p, 12 + 7.2 * math.cos(a), 12 + 7.2 * math.sin(a), 12 + 9.8 * math.cos(a), 12 + 9.8 * math.sin(a))


def _i_board(p): _rrect(p, 3, 4, 5.5, 16, 1.6); _rrect(p, 9.7, 4, 5.5, 10, 1.6); _rrect(p, 16.4, 4, 4.6, 13, 1.6)
def _i_pulse(p): _poly(p, [(3, 12), (7, 12), (10, 5), (14, 19), (17, 12), (21, 12)])
def _i_sliders(p):
    for y, x in ((7, 9), (12, 15), (17, 8)):
        _line(p, 4, y, 20, y); p.setBrush(p.pen().color()); _circ(p, x, y, 2.2); p.setBrush(Qt.BrushStyle.NoBrush)
def _i_home(p): _poly(p, [(3, 11), (12, 3.5), (21, 11)]); _poly(p, [(5.5, 9.5), (5.5, 20.5), (18.5, 20.5), (18.5, 9.5)]); _poly(p, [(10, 20.5), (10, 14), (14, 14), (14, 20.5)])


ICONS = {
    'board': _i_board, 'pulse': _i_pulse, 'sliders': _i_sliders, 'home': _i_home,
    'plus': _i_plus, 'edit': _i_edit, 'check': _i_check, 'check_circle': _i_check_circle, 'clock': _i_clock,
    'alert': _i_alert, 'tasks': _i_tasks, 'calendar': _i_calendar, 'archive': _i_archive, 'trash': _i_trash,
    'copy': _i_copy, 'download': _i_download, 'chevron_left': _i_chev_l, 'chevron_right': _i_chev_r,
    'chev_down': _i_chev_d, 'chev_up': _i_chev_u, 'search': _i_search, 'chart': _i_chart, 'file': _i_file,
    'doc': _i_doc, 'sheet': _i_sheet, 'users': _i_users, 'restore': _i_restore, 'moon': _i_moon, 'sun': _i_sun,
}


def draw_icon(p: QPainter, kind: str, rect, color, width: float = 2.0):
    """Draw icon `kind` inside `rect` using `color` (stroke width is in 24-grid units)."""
    fn = ICONS.get(kind)
    if fn is None:
        return
    rect = QRectF(rect)
    s = min(rect.width(), rect.height()) / 24.0
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.translate(rect.center().x() - 12 * s, rect.center().y() - 12 * s)
    p.scale(s, s)
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    fn(p)
    p.restore()


def icon_pixmap(kind: str, color, size: int = 20) -> QPixmap:
    scale = 2
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(scale)
    p = QPainter(pm)
    draw_icon(p, kind, QRectF(0, 0, size, size), color)
    p.end()
    return pm


def app_icon() -> QIcon:
    """Gradient app icon (window + tray)."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0, 0, size, size)
        g.setColorAt(0, QColor('#4F46E5')); g.setColorAt(0.55, QColor('#8B5CF6')); g.setColorAt(1, QColor('#EC4899'))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(g))
        p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.24, size * 0.24)
        draw_icon(p, 'tasks', QRectF(size * 0.2, size * 0.2, size * 0.6, size * 0.6), '#FFFFFF', width=2.2)
        p.end()
        icon.addPixmap(pm)
    return icon


def _build_qss_icons():
    """Arrow images referenced by the stylesheet (QSS cannot draw arrows by itself)."""
    d = Path(tempfile.gettempdir()) / 'MounazzemAlFariq_ui' / P['name']
    d.mkdir(parents=True, exist_ok=True)
    specs = {'check_w': ('check', '#FFFFFF'), 'down': ('chev_down', P['text_muted']), 'up': ('chev_up', P['text_muted']),
             'cal_prev': ('chevron_right', '#FFFFFF'), 'cal_next': ('chevron_left', '#FFFFFF')}
    _ICONS.clear()
    for key, (kind, color) in specs.items():
        for scale, suffix in ((1, ''), (2, '@2x')):
            size = 14 * scale
            pm = QPixmap(size, size)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            draw_icon(p, kind, QRectF(0, 0, size, size), color, width=2.6)
            p.end()
            pm.save(str(d / f'{key}{suffix}.png'), 'PNG')
        _ICONS['ico_' + key] = (d / f'{key}.png').as_posix()


# --------------------------------------------------------------------------- stylesheet
_QSS = '''
* { outline: none; }
QMainWindow { background: @bg0@; }
QDialog { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 @bg0@, stop:1 @bg1@); }
QWidget { color: @text@; }
QLabel { background: transparent; }
QToolTip { background: @tooltip_bg@; color: @tooltip_fg@; border: 0; border-radius: 8px; padding: 7px 11px; }

QLabel#heroTitle { color: #FFFFFF; font-size: 26px; font-weight: 800; }
QLabel#heroSub { color: rgba(255,255,255,215); font-size: 13px; }
QLabel#cardTitle { font-size: 15px; font-weight: 700; }
QLabel#muted { color: @text_muted@; }
QLabel#fieldLabel { color: @text_muted@; font-weight: 600; font-size: 12px; }
QLabel#chip { background: @primary_soft@; color: @primary_dark@; border-radius: 13px; padding: 5px 14px; font-weight: 700; }
QLabel#empty { color: @text_faint@; font-size: 14px; font-weight: 600; }

QLineEdit#heroSearch { background: rgba(255,255,255,46); border: 1px solid rgba(255,255,255,90); border-radius: 15px;
    color: #FFFFFF; padding: 10px 16px; placeholder-text-color: rgba(255,255,255,175);
    selection-background-color: rgba(255,255,255,100); selection-color: #FFFFFF; }
QLineEdit#heroSearch:hover { background: rgba(255,255,255,62); }
QLineEdit#heroSearch:focus { background: rgba(255,255,255,80); border: 1px solid #FFFFFF; }

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QTimeEdit, QDateEdit, QComboBox {
    background: @input_bg@; border: 1px solid @border@; border-radius: 12px; padding: 9px 14px;
    selection-background-color: @primary@; selection-color: #FFFFFF; }
QTextEdit, QPlainTextEdit { padding: 8px 12px; }
QSpinBox, QTimeEdit, QDateEdit, QComboBox { padding: 8px 30px; min-height: 22px; }
QLineEdit:hover, QTextEdit:hover, QSpinBox:hover, QTimeEdit:hover, QDateEdit:hover, QComboBox:hover { border-color: @border_strong@; }
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QTimeEdit:focus, QDateEdit:focus, QComboBox:focus { border: 1px solid @primary@; background: @surface@; }

QAbstractSpinBox QLineEdit, QComboBox QLineEdit { background: transparent; border: 0; padding: 0; margin: 0; selection-background-color: @primary@; }
QLineEdit#timePart { padding: 8px 4px; min-width: 56px; max-width: 72px; font-size: 16px; font-weight: 700; }
QLabel#timeColon { font-weight: 800; color: @text_muted@; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 6px; border: 2px solid @border_strong@; background: @input_bg@; }
QCheckBox::indicator:hover { border-color: @primary@; }
QCheckBox::indicator:checked { border: 2px solid @primary@; background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 @primary@, stop:1 @accent@); image: url(@ico_check_w@); }
QListWidget { background: transparent; border: 0; }
QDialog#palette { background: @surface@; border: 1px solid @border_strong@; border-radius: 18px; }
QLineEdit#paletteInput { font-size: 16px; padding: 12px 16px; }
QListWidget#paletteList::item { padding: 10px 14px; border-radius: 10px; }
QListWidget#paletteList::item:selected { background: @primary_soft@; color: @primary_dark@; }
QComboBox { combobox-popup: 0; }
QComboBox::drop-down, QDateEdit::drop-down { subcontrol-origin: padding; subcontrol-position: center right; width: 30px; border: 0; background: transparent; }
QComboBox::down-arrow, QDateEdit::down-arrow { image: url(@ico_down@); width: 14px; height: 14px; }
QSpinBox::up-button, QTimeEdit::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 24px; border: 0; background: transparent; margin: 4px 4px 0 4px; }
QSpinBox::down-button, QTimeEdit::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 24px; border: 0; background: transparent; margin: 0 4px 4px 4px; }
QSpinBox::up-arrow, QTimeEdit::up-arrow { image: url(@ico_up@); width: 10px; height: 10px; }
QSpinBox::down-arrow, QTimeEdit::down-arrow { image: url(@ico_down@); width: 10px; height: 10px; }
QComboBox QAbstractItemView { background: @surface@; border: 1px solid @border@; border-radius: 12px; padding: 6px;
    selection-background-color: @primary_soft@; selection-color: @primary_dark@; outline: 0; }
QComboBox QAbstractItemView::item { padding: 8px 12px; border-radius: 8px; min-height: 24px; }
QComboBox QAbstractItemView::item:selected, QComboBox QAbstractItemView::item:hover { background: @primary_soft@; color: @primary_dark@; }

QCalendarWidget QWidget#qt_calendar_navigationbar { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 @primary@, stop:1 @accent@); border-top-left-radius: 10px; border-top-right-radius: 10px; }
QCalendarWidget QToolButton { color: #FFFFFF; background: transparent; border: 0; border-radius: 8px; padding: 5px 9px; font-weight: 700; }
QCalendarWidget QToolButton:hover { background: rgba(255,255,255,60); }
QCalendarWidget QToolButton#qt_calendar_prevmonth { qproperty-icon: url(@ico_cal_prev@); }
QCalendarWidget QToolButton#qt_calendar_nextmonth { qproperty-icon: url(@ico_cal_next@); }
QCalendarWidget QToolButton::menu-indicator { image: none; }
QCalendarWidget QMenu { background: @surface@; color: @text@; }
QCalendarWidget QSpinBox { background: rgba(255,255,255,40); color: #FFFFFF; border: 0; border-radius: 8px; padding: 2px 8px; }
QCalendarWidget QAbstractItemView:enabled { background: @surface@; color: @text@; selection-background-color: @primary@; selection-color: #FFFFFF; outline: 0; }
QCalendarWidget QAbstractItemView:disabled { color: @text_faint@; }

QScrollArea { background: transparent; border: 0; }
QScrollBar:vertical { background: rgba(120,130,190,30); width: 14px; margin: 4px 2px; border-radius: 7px; }
QScrollBar::handle:vertical { background: @scroll@; border-radius: 5px; min-height: 40px; margin: 2px; }
QScrollBar::handle:vertical:hover { background: @primary@; }
QScrollBar:horizontal { background: rgba(120,130,190,30); height: 14px; margin: 2px 4px; border-radius: 7px; }
QScrollBar::handle:horizontal { background: @scroll@; border-radius: 5px; min-width: 40px; margin: 2px; }
QScrollBar::handle:horizontal:hover { background: @primary@; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QTableWidget, QTableView { background: transparent; border: 0; gridline-color: transparent; }
QHeaderView { background: transparent; border: 0; }
QHeaderView::section { background: transparent; color: @text_muted@; border: 0; border-bottom: 2px solid @border@; padding: 10px 12px; font-weight: 700; font-size: 12px; }
QTableCornerButton::section { background: transparent; border: 0; }

QSlider::groove:horizontal { height: 8px; border-radius: 4px; background: @border@; }
QSlider::sub-page:horizontal { border-radius: 4px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 @info@, stop:1 @accent@); }
QSlider::add-page:horizontal { border-radius: 4px; background: @border@; }
QSlider::handle:horizontal { width: 12px; height: 12px; margin: -5px 0; border-radius: 9px; background: @surface@; border: 3px solid @primary@; }
QSlider::handle:horizontal:hover { border-color: @accent@; }

QProgressBar { background: @border@; border: 0; border-radius: 5px; max-height: 10px; min-height: 10px; }
QProgressBar::chunk { border-radius: 5px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 @info@, stop:1 @accent@); }

QStatusBar { background: transparent; color: @text_muted@; }
QStatusBar::item { border: 0; }

QMenu { background: @surface@; border: 1px solid @border@; border-radius: 12px; padding: 6px; }
QMenu::item { padding: 8px 22px; border-radius: 8px; }
QMenu::item:selected { background: @primary_soft@; color: @primary_dark@; }

QMessageBox { background: @surface@; }
QMessageBox QLabel { color: @text@; font-size: 14px; min-width: 280px; }
QMessageBox QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 @primary@, stop:1 @accent@); color: #FFFFFF;
    border: 0; border-radius: 11px; padding: 9px 22px; min-width: 88px; font-weight: 700; }
QMessageBox QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 @primary_dark@, stop:1 @primary@); }
QMessageBox QPushButton[secondary="true"] { background: @primary_soft@; color: @primary_dark@; }
QMessageBox QPushButton[secondary="true"]:hover { background: @primary_soft2@; }
QMessageBox QPushButton[danger="true"] { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 @danger@, stop:1 #F97316); }
'''


def build_qss() -> str:
    tokens = dict(P)
    tokens.update(_ICONS)
    return re.sub(r'@(\w+)@', lambda m: str(tokens.get(m.group(1), '#FF00FF')), _QSS)


def current_accent() -> str:
    return _state['accent']


def apply(app, which: str | None = None, accent: str | None = None):
    """Activate a palette ('light' / 'dark') + accent preset, rebuild icons + stylesheet, notify widgets."""
    dark = which == 'dark'
    if accent in ACCENTS:
        _state['accent'] = accent
    primary, second, glow, hero = ACCENTS[_state['accent']]
    P.clear()
    P.update(DARK if dark else LIGHT)
    pc, sc = QColor(primary), QColor(second)
    P['primary'] = pc.lighter(120).name() if dark else primary
    P['accent'] = sc.lighter(115).name() if dark else second
    P['primary_dark'] = (pc.lighter(150) if dark else pc.darker(150)).name()
    base = QColor(P['surface'])
    P['primary_soft'] = mix(base, pc, 0.22 if dark else 0.10).name()
    P['primary_soft2'] = mix(base, pc, 0.34 if dark else 0.20).name()
    P['glow_a'], P['glow_b'] = primary, glow
    P['hero_a'], P['hero_b'], P['hero_c'] = hero
    _build_qss_icons()
    app.setStyleSheet(build_qss())
    signals.changed.emit()
