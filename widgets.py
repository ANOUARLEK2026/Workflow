"""widgets.py - animated, gradient-rich building blocks used by main.py.

All painting is done with QPainter (no extra dependencies) and every colour comes from theme.P,
so the whole UI re-skins instantly when the light / dark theme is switched.
"""
from __future__ import annotations

import math

from PySide6.QtCore import (Qt, QDate, QTime, QRectF, QPointF, QPoint, QSize, QEvent, QObject, QTimer, QEasingCurve, QVariantAnimation,
                            QPropertyAnimation, Signal)
from PySide6.QtGui import (QGuiApplication, QIntValidator, QIcon, QColor, QPainter, QPen, QBrush, QFont, QFontMetrics, QLinearGradient, QRadialGradient,
                           QPainterPath)
from PySide6.QtWidgets import (QWidget, QPushButton, QLabel, QVBoxLayout, QHBoxLayout, QStackedWidget,
                               QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QTableWidget, QStyledItemDelegate,
                               QStyle, QStyleOptionViewItem, QMessageBox, QToolTip, QSlider, QComboBox, QListView, QDialog,
                               QFrame, QSizePolicy, QSpinBox, QLineEdit, QCalendarWidget, QCheckBox, QListWidget, QListWidgetItem)

import theme
from theme import P, qc, mix, paint_shadow, draw_icon

# item-data roles used by the table delegate (256 == Qt.UserRole)
ROLE_ID = 256
ROLE_STATE = 257      # row state: done / cancel / late / progress / scheduled
ROLE_PRIO = 258       # priority 1..10
ROLE_PILL = 259       # status-pill key for a cell

_OUT_CUBIC = QEasingCurve.Type.OutCubic


def anim(parent, duration=200, curve=_OUT_CUBIC) -> QVariantAnimation:
    a = QVariantAnimation(parent)
    a.setDuration(duration)
    a.setEasingCurve(curve)
    return a


def _retarget(a: QVariantAnimation, current: float, target: float):
    a.stop()
    a.setStartValue(float(current))
    a.setEndValue(float(target))
    a.start()


def _font(base: QFont, px: int, weight=QFont.Weight.Normal) -> QFont:
    f = QFont(base)
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


# =========================================================================== surfaces
class Backdrop(QWidget):
    """Window background: soft gradient + three large 'light' glows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        theme.signals.changed.connect(self.update)

    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        g = QLinearGradient(0, 0, r.width(), r.height())
        g.setColorAt(0, QColor(P['bg0']))
        g.setColorAt(1, QColor(P['bg1']))
        p.fillRect(r, g)
        for fx, fy, rad, col in ((0.12, 0.0, 0.55, P['glow_a']), (0.96, 1.0, 0.60, P['glow_b']), (0.88, 0.08, 0.35, P['cyan'])):
            c = qc(col, P['glow_alpha'])
            rg = QRadialGradient(QPointF(r.width() * fx, r.height() * fy), max(r.width(), r.height()) * rad)
            rg.setColorAt(0, c)
            rg.setColorAt(1, qc(col, 0.0))
            p.fillRect(r, QBrush(rg))


class Card(QWidget):
    """Rounded surface with a soft layered shadow. Put children in `card.body` (a QVBoxLayout)."""
    M = 16

    def __init__(self, parent=None, padding=16):
        super().__init__(parent)
        m = self.M
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(m + padding, m - 6 + padding, m + padding, m + 6 + padding)
        self.body.setSpacing(12)
        theme.signals.changed.connect(self.update)

    def visible_rect(self) -> QRectF:
        m = self.M
        return QRectF(self.rect()).adjusted(m, m - 6, -m, -(m + 6))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.visible_rect()
        paint_shadow(p, r, 20, qc(P['shadow'], P['shadow_alpha']), spread=14, dy=6)
        p.setPen(QPen(QColor(P['border']), 1))
        p.setBrush(QColor(P['surface']))
        p.drawRoundedRect(r, 20, 20)


# =========================================================================== buttons
class Btn(QPushButton):
    """Animated button. variants: primary | success | danger | soft | ghost | glass.
    Hover = colour blend + lift + glow, press = squash, keyboard focus = ring."""
    PAD_X, PAD_TOP, PAD_BOT = 6, 3, 9

    def __init__(self, text='', variant='soft', icon=None, parent=None):
        super().__init__(text, parent)
        self.variant = variant
        self.icon_kind = icon
        self.dot = None
        self._h = 0.0
        self._pr = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFont(_font(self.font(), 13, QFont.Weight.DemiBold))
        self._ha = anim(self, 180)
        self._ha.valueChanged.connect(self._set_h)
        self._pa = anim(self, 90, QEasingCurve.Type.OutQuad)
        self._pa.valueChanged.connect(self._set_p)
        theme.signals.changed.connect(self.update)

    def _set_h(self, v): self._h = float(v); self.update()
    def _set_p(self, v): self._pr = float(v); self.update()

    def enterEvent(self, e): _retarget(self._ha, self._h, 1.0); super().enterEvent(e)
    def leaveEvent(self, e): _retarget(self._ha, self._h, 0.0); super().leaveEvent(e)

    def mousePressEvent(self, e):
        super().mousePressEvent(e)
        _retarget(self._pa, self._pr, 1.0)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        _retarget(self._pa, self._pr, 0.0)

    def sizeHint(self):
        fm = QFontMetrics(self.font())
        t = self.text()
        w = fm.horizontalAdvance(t)
        if self.icon_kind or self.dot:
            w += 18 + (8 if t else 0)
        w += 36 if t else 22
        return QSize(max(w, 88 if t else 44) + 2 * self.PAD_X, 40 + self.PAD_TOP + self.PAD_BOT)

    def minimumSizeHint(self):
        return self.sizeHint()

    def _style(self, h):
        """-> (colour1, colour2, foreground, border or None, glow or None)"""
        v = self.variant
        if v in ('primary', 'success', 'danger'):
            pairs = {'primary': (P['primary'], P['accent']), 'success': ('#10B981', '#14B8A6'), 'danger': ('#F43F5E', '#F97316')}
            a, b = (QColor(x) for x in pairs[v])
            a, b = mix(a, a.lighter(118), h), mix(b, b.lighter(118), h)
            return a, b, QColor('#FFFFFF'), None, a
        if v == 'glass':
            bg = qc('#FFFFFF', 0.16 + 0.14 * h)
            return bg, bg, QColor('#FFFFFF'), qc('#FFFFFF', 0.30 + 0.20 * h), None
        if v == 'ghost':
            bg = mix(qc(P['primary_soft'], 0.0), QColor(P['primary_soft']), h)
            return bg, bg, mix(P['text_muted'], P['primary_dark'], h), None, None
        bg = mix(P['surface'], P['primary_soft'], h)
        return bg, bg, mix(P['text'], P['primary_dark'], h), mix(P['border'], P['primary'], h), None

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        enabled = self.isEnabled()
        h = self._h if enabled else 0.0
        r = QRectF(self.rect()).adjusted(self.PAD_X, self.PAD_TOP, -self.PAD_X, -self.PAD_BOT)
        c1, c2, fg, border, glow = self._style(h)
        if not enabled:
            c1 = c2 = QColor(P['surface_alt'])
            fg = QColor(P['text_faint'])
            border, glow = QColor(P['border']), None
        if glow is not None:
            paint_shadow(p, r, 12, qc(glow, 0.36 + 0.16 * h), spread=8, dy=3 + 2 * h)
        s = 1.0 - 0.035 * self._pr
        c = r.center()
        p.translate(c)
        p.scale(s, s)
        p.translate(-c.x(), -c.y() - 1.5 * h)
        path = QPainterPath()
        path.addRoundedRect(r, 12, 12)
        if c1 != c2:
            g = QLinearGradient(r.left(), r.top(), r.right(), r.bottom())
            g.setColorAt(0, c1)
            g.setColorAt(1, c2)
            p.fillPath(path, g)
            gloss = QLinearGradient(0, r.top(), 0, r.bottom())
            gloss.setColorAt(0, QColor(255, 255, 255, 46))
            gloss.setColorAt(0.55, QColor(255, 255, 255, 0))
            p.fillPath(path, gloss)
        else:
            p.fillPath(path, c1)
        if border is not None:
            p.setPen(QPen(border, 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        # content (icon + text, centred, mirrored in RTL)
        p.setFont(self.font())
        text = self.text()
        tw = QFontMetrics(self.font()).horizontalAdvance(text)
        iw = 18 if (self.icon_kind or self.dot) else 0
        gap = 8 if (iw and text) else 0
        total = iw + gap + tw
        x0 = r.center().x() - total / 2
        rtl = self.isRightToLeft()
        ix = x0 + total - iw if rtl else x0
        tx = x0 if rtl else x0 + iw + gap
        if self.icon_kind:
            draw_icon(p, self.icon_kind, QRectF(ix, r.center().y() - 9, 18, 18), fg, 2.1)
        elif self.dot:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self.dot)
            p.drawEllipse(QPointF(ix + 9, r.center().y()), 5.5, 5.5)
        if text:
            p.setPen(fg)
            p.drawText(QRectF(tx, r.top(), tw + 4, r.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        if self.hasFocus() and enabled:
            p.setPen(QPen(qc(P['primary'], 0.7), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(-2, -2, 2, 2), 14, 14)


class Combo(QComboBox):
    """QComboBox with a styleable popup list (rounded, transparent frame)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setView(QListView())
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMaxVisibleItems(8)
        try:
            w = self.view().window()
            w.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
            w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        except Exception:
            pass


class FocusGlow(QObject):
    """Animated primary-colour glow around a line edit while it has focus."""

    def __init__(self, widget):
        super().__init__(widget)
        self.fx = QGraphicsDropShadowEffect(widget)
        self.fx.setOffset(0, 0)
        self.fx.setBlurRadius(0)
        self.fx.setColor(qc(P['primary'], 0.55))
        widget.setGraphicsEffect(self.fx)
        self.a = QPropertyAnimation(self.fx, b'blurRadius', self)
        self.a.setDuration(220)
        widget.installEventFilter(self)

    def eventFilter(self, o, e):
        t = e.type()
        if t == QEvent.Type.FocusIn:
            self.fx.setColor(qc(P['primary'], 0.55))
            self._go(18)
        elif t == QEvent.Type.FocusOut:
            self._go(0)
        return False

    def _go(self, v):
        self.a.stop()
        self.a.setStartValue(self.fx.blurRadius())
        self.a.setEndValue(float(v))
        self.a.start()


class SearchGrow(QObject):
    """Header search box smoothly widens when focused."""

    def __init__(self, edit, narrow=300, wide=440):
        super().__init__(edit)
        self.edit, self.narrow, self.wide = edit, narrow, wide
        self.a = QPropertyAnimation(edit, b'maximumWidth', self)
        self.a.setDuration(260)
        self.a.setEasingCurve(_OUT_CUBIC)
        edit.installEventFilter(self)

    def eventFilter(self, o, e):
        t = e.type()
        if t in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self.a.stop()
            self.a.setStartValue(self.edit.maximumWidth())
            self.a.setEndValue(self.wide if t == QEvent.Type.FocusIn else self.narrow)
            self.a.start()
        return False


# =========================================================================== header
class HeaderBanner(QWidget):
    """Floating gradient hero banner with slowly drifting light blobs. Populate `self.lay`."""
    M = 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(138)
        self._phase = 0.0
        self._compact = False
        m = self.M
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(m + 24, m - 6 + 10, m + 22, m + 6 + 10)
        self.lay.setSpacing(12)
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

    def showEvent(self, e): self._timer.start(); super().showEvent(e)
    def hideEvent(self, e): self._timer.stop(); super().hideEvent(e)

    def set_compact(self, on):
        """Short banner for small screens (gives the pages more room)."""
        on = bool(on)
        if on == self._compact:
            return
        self._compact = on
        m = self.M
        if on:
            self.setFixedHeight(104)
            self.lay.setContentsMargins(m + 24, 10, m + 22, 18)
        else:
            self.setFixedHeight(138)
            self.lay.setContentsMargins(m + 24, m - 6 + 10, m + 22, m + 6 + 10)
        self.update()

    def _tick(self):
        self._phase = (self._phase + 0.004) % 1.0
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        m = self.M
        vr = QRectF(self.rect()).adjusted(m, m - 6, -m, -(m + 6))
        paint_shadow(p, vr, 26, qc(P['hero_b'], 0.42), spread=14, dy=8)
        path = QPainterPath()
        path.addRoundedRect(vr, 26, 26)
        p.setClipPath(path)
        g = QLinearGradient(vr.left(), vr.top(), vr.right(), vr.bottom())
        g.setColorAt(0.0, QColor(P['hero_a']))
        g.setColorAt(0.55, QColor(P['hero_b']))
        g.setColorAt(1.0, QColor(P['hero_c']))
        p.fillPath(path, g)
        ph = self._phase * 2 * math.pi
        for fx, fy, rad, off, a in ((0.15, 0.2, 260, 0.0, 70), (0.55, 0.9, 300, 2.1, 48), (0.92, 0.15, 220, 4.2, 60)):
            cx = vr.left() + vr.width() * (fx + 0.05 * math.cos(ph + off))
            cy = vr.top() + vr.height() * (fy + 0.22 * math.sin(ph * 1.3 + off))
            rg = QRadialGradient(QPointF(cx, cy), rad)
            rg.setColorAt(0, QColor(255, 255, 255, a))
            rg.setColorAt(1, QColor(255, 255, 255, 0))
            p.fillRect(vr, QBrush(rg))
        p.setPen(QPen(QColor(255, 255, 255, 30), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for k, rad in enumerate((70, 110, 150)):
            p.drawEllipse(QPointF(vr.left() + 40, vr.bottom() + 20), rad, rad)
        gl = QLinearGradient(0, vr.top(), 0, vr.bottom())
        gl.setColorAt(0, QColor(255, 255, 255, 44))
        gl.setColorAt(0.55, QColor(255, 255, 255, 0))
        p.fillPath(path, gl)


class LogoBadge(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(60, 60)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(2, 2, 56, 56)
        p.setPen(QPen(QColor(255, 255, 255, 120), 1.5))
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor(255, 255, 255, 80))
        g.setColorAt(1, QColor(255, 255, 255, 28))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(r, 18, 18)
        draw_icon(p, 'tasks', QRectF(15, 15, 30, 30), '#FFFFFF', 2.0)


# =========================================================================== navigation
class PillNav(QWidget):
    """Segmented navigation with a gradient indicator that glides between tabs."""
    currentChanged = Signal(int)
    M = 14

    def __init__(self, labels, icons=None, parent=None):
        super().__init__(parent)
        self.labels = list(labels)
        self.icons = list(icons) if icons else [None] * len(self.labels)
        self._idx = 0
        self._mode = 0
        self._hover = -1
        self._t = 1.0
        self._from = None
        self._ia = anim(self, 340, QEasingCurve.Type.OutBack)
        self._ia.setStartValue(0.0)
        self._ia.setEndValue(1.0)
        self._ia.valueChanged.connect(self._on_t)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(_font(self.font(), 14, QFont.Weight.DemiBold))
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        theme.signals.changed.connect(self.update)

    def _on_t(self, v): self._t = float(v); self.update()

    def _widths_for(self, mode):
        """mode 0: full, 1: tighter padding, 2: icon only except for the selected tab."""
        fm = QFontMetrics(self.font())
        pad = 40 if mode == 0 else 22
        out = []
        for i, (t, ic) in enumerate(zip(self.labels, self.icons)):
            show = mode < 2 or i == self._idx
            icon_w = (26 if show else 18) if ic else 0
            out.append((fm.horizontalAdvance(t) if show else 0) + icon_w + pad)
        return out

    def _calc_mode(self):
        avail = self.width() - 2 * self.M - 12
        if avail <= 0:
            return 0
        for mode in (0, 1, 2):
            if sum(self._widths_for(mode)) <= avail:
                return mode
        return 2

    def _show_label(self, i):
        return self._mode < 2 or i == self._idx

    def _item_widths(self):
        return self._widths_for(self._mode)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        mode = self._calc_mode()
        if mode != self._mode:
            self._mode = mode
            self.update()

    def sizeHint(self):
        return QSize(int(sum(self._widths_for(0)) + 2 * self.M + 12), 62)

    def minimumSizeHint(self):
        return QSize(int(sum(self._widths_for(2)) + 2 * self.M + 12), 62)

    def _rects(self):
        ws = self._item_widths()
        box = self._box()
        x = box.right() - 5 if self.isRightToLeft() else box.left() + 5
        out = []
        for w in ws:
            if self.isRightToLeft():
                out.append(QRectF(x - w, box.top() + 5, w, box.height() - 10))
                x -= w
            else:
                out.append(QRectF(x, box.top() + 5, w, box.height() - 10))
                x += w
        return out

    def _box(self):
        return QRectF(self.M, 4, sum(self._item_widths()) + 10, 50)

    def _ind_rect(self):
        target = self._rects()[self._idx]
        if self._from is None or self._t >= 1.0:
            return target
        f, t = self._from, target
        k = self._t
        return QRectF(f.x() + (t.x() - f.x()) * k, f.y(), f.width() + (t.width() - f.width()) * k, f.height())

    def currentIndex(self): return self._idx

    def setCurrentIndex(self, i, animate=True):
        if i == self._idx or not (0 <= i < len(self.labels)):
            return
        self._from = self._ind_rect()
        self._idx = i
        if animate:
            self._t = 0.0
            self._ia.stop()
            self._ia.start()
        else:
            self._t = 1.0
        self.currentChanged.emit(i)
        self.update()

    def _index_at(self, pos):
        for i, r in enumerate(self._rects()):
            if r.contains(pos):
                return i
        return -1

    def mouseMoveEvent(self, e):
        i = self._index_at(e.position())
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, e): self._hover = -1; self.update(); super().leaveEvent(e)

    def event(self, e):
        if e.type() == QEvent.Type.ToolTip:
            i = self._index_at(QPointF(e.pos()))
            if i >= 0 and not self._show_label(i):
                QToolTip.showText(e.globalPos(), self.labels[i], self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    def mouseReleaseEvent(self, e):
        i = self._index_at(e.position())
        if i >= 0:
            self.setCurrentIndex(i)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = self._box()
        paint_shadow(p, box, 25, qc(P['shadow'], P['shadow_alpha'] * 0.8), spread=10, dy=4)
        p.setPen(QPen(QColor(P['border']), 1))
        p.setBrush(QColor(P['surface']))
        p.drawRoundedRect(box, 25, 25)
        ind = self._ind_rect()
        gpath = QPainterPath()
        gpath.addRoundedRect(ind, 20, 20)
        paint_shadow(p, ind, 20, qc(P['primary'], 0.42), spread=7, dy=3)
        g = QLinearGradient(ind.left(), ind.top(), ind.right(), ind.bottom())
        g.setColorAt(0, QColor(P['primary']))
        g.setColorAt(1, QColor(P['accent']))
        p.fillPath(gpath, g)
        gloss = QLinearGradient(0, ind.top(), 0, ind.bottom())
        gloss.setColorAt(0, QColor(255, 255, 255, 50))
        gloss.setColorAt(0.6, QColor(255, 255, 255, 0))
        p.fillPath(gpath, gloss)
        p.setFont(self.font())
        fm = QFontMetrics(self.font())
        for i, r in enumerate(self._rects()):
            overlap = max(0.0, min(r.right(), ind.right()) - max(r.left(), ind.left())) / r.width()
            k = max(0.0, min(1.0, (overlap - 0.35) / 0.3))
            base = mix(P['text_muted'], P['primary_dark'], 1.0 if i == self._hover else 0.0)
            col = mix(base, '#FFFFFF', k)
            ic = self.icons[i]
            show = self._show_label(i)
            tw = fm.horizontalAdvance(self.labels[i]) if show else 0
            iw = 18 if ic else 0
            gap = 8 if (ic and show) else 0
            total = iw + gap + tw
            x0 = r.center().x() - total / 2
            rtl = self.isRightToLeft()
            ix = x0 + total - iw if rtl else x0
            tx = x0 if rtl else x0 + iw + gap
            if ic:
                draw_icon(p, ic, QRectF(ix, r.center().y() - 9, 18, 18), col, 2.1)
            p.setPen(col)
            if show:
                p.drawText(QRectF(tx, r.top(), tw + 4, r.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.labels[i])


class FadeStack(QStackedWidget):
    """QStackedWidget that cross-fades to the incoming page."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._anim = None

    def set_index_animated(self, i):
        if i == self.currentIndex():
            return
        self.setCurrentIndex(i)
        new = self.currentWidget()
        if new is None:
            return
        fx = QGraphicsOpacityEffect(new)
        fx.setOpacity(0.0)
        new.setGraphicsEffect(fx)
        a = QPropertyAnimation(fx, b'opacity', self)
        a.setDuration(280)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(_OUT_CUBIC)
        a.finished.connect(lambda w=new: QTimer.singleShot(0, lambda: w.setGraphicsEffect(None)))
        self._anim = a
        a.start()


# =========================================================================== gradient cards
class GradCard(QWidget):
    """Gradient tile. numeric=True -> KPI with count-up number; numeric=False -> big clickable action tile."""
    clicked = Signal()
    M = 14

    def __init__(self, title, icon, c1, c2, numeric=True, subtitle='', clickable=False, parent=None, suffix=''):
        super().__init__(parent)
        self.title, self.icon, self.subtitle, self.suffix = title, icon, subtitle, suffix
        self.c1, self.c2 = QColor(c1), QColor(c2)
        self.numeric, self.clickable = numeric, clickable
        self._value = 0
        self._shown = 0.0
        self._h = 0.0
        self.setFixedHeight(122 if numeric else 112)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._va = anim(self, 800)
        self._va.valueChanged.connect(self._on_shown)
        self._ha = anim(self, 200)
        self._ha.valueChanged.connect(self._on_h)

    def _on_shown(self, v): self._shown = float(v); self.update()
    def _on_h(self, v): self._h = float(v); self.update()

    def set_value(self, v):
        v = int(v)
        if v == self._value and int(round(self._shown)) == v:
            return
        self._value = v
        _retarget(self._va, self._shown, v)

    def replay(self):
        self._shown = 0.0
        _retarget(self._va, 0.0, self._value)

    def enterEvent(self, e): _retarget(self._ha, self._h, 1.0); super().enterEvent(e)
    def leaveEvent(self, e): _retarget(self._ha, self._h, 0.0); super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if self.clickable and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        m, h = self.M, self._h
        vr = QRectF(self.rect()).adjusted(m, m - 4, -m, -(m + 4)).adjusted(-3 * h, -3 * h, 3 * h, 3 * h)
        paint_shadow(p, vr, 22, qc(self.c2, 0.42 + 0.16 * h), spread=12, dy=7 + 3 * h)
        path = QPainterPath()
        path.addRoundedRect(vr, 22, 22)
        p.setClipPath(path)
        g = QLinearGradient(vr.left(), vr.top(), vr.right(), vr.bottom())
        g.setColorAt(0, self.c1)
        g.setColorAt(1, self.c2)
        p.fillPath(path, g)
        rtl = self.isRightToLeft()
        # decorative circles on the trailing side
        cx = vr.left() + 30 if rtl else vr.right() - 30
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 30))
        p.drawEllipse(QPointF(cx, vr.top() + 6 - 8 * h), 78, 78)
        p.setBrush(QColor(255, 255, 255, 22))
        p.drawEllipse(QPointF(cx + (-46 if rtl else 46), vr.bottom() + 18), 62, 62)
        gloss = QLinearGradient(0, vr.top(), 0, vr.bottom())
        gloss.setColorAt(0, QColor(255, 255, 255, 52))
        gloss.setColorAt(0.5, QColor(255, 255, 255, 0))
        p.fillPath(path, gloss)
        # icon badge (trailing)
        bs = 46 if self.numeric else 52
        bx = vr.left() + 18 if rtl else vr.right() - 18 - bs
        badge = QRectF(bx, vr.top() + 16, bs, bs)
        p.setPen(QPen(QColor(255, 255, 255, 70), 1))
        p.setBrush(QColor(255, 255, 255, 52))
        p.drawRoundedRect(badge, 15, 15)
        draw_icon(p, self.icon, badge.adjusted(11, 11, -11, -11), '#FFFFFF', 2.0)
        # text (leading)
        align = Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft
        tx = QRectF(vr.left() + 20, 0, vr.width() - 40 - bs - 10, 0)
        if rtl:
            tx.setLeft(vr.left() + 18 + bs + 10)
            tx.setRight(vr.right() - 20)
        else:
            tx.setLeft(vr.left() + 20)
            tx.setRight(vr.right() - 18 - bs - 10)
        if self.numeric:
            p.setPen(QColor(255, 255, 255, 225))
            p.setFont(_font(self.font(), 13, QFont.Weight.DemiBold))
            p.drawText(QRectF(tx.left(), vr.top() + 16, tx.width(), 22), align | Qt.AlignmentFlag.AlignVCenter, self.title)
            p.setPen(QColor('#FFFFFF'))
            p.setFont(_font(self.font(), 38, QFont.Weight.ExtraBold))
            p.drawText(QRectF(tx.left(), vr.top() + 40, tx.width(), 52), align | Qt.AlignmentFlag.AlignVCenter, str(int(round(self._shown))) + self.suffix)
        else:
            p.setPen(QColor('#FFFFFF'))
            p.setFont(_font(self.font(), 18, QFont.Weight.Bold))
            p.drawText(QRectF(tx.left(), vr.top() + 18, tx.width(), 30), align | Qt.AlignmentFlag.AlignVCenter, self.title)
            p.setPen(QColor(255, 255, 255, 215))
            p.setFont(_font(self.font(), 12))
            p.drawText(QRectF(tx.left(), vr.top() + 50, tx.width(), 20), align | Qt.AlignmentFlag.AlignVCenter, self.subtitle)
            ax = vr.left() + 18 if rtl else vr.right() - 18 - 30
            arect = QRectF(ax, vr.bottom() - 18 - 30 + 3 * (1 - h), 30, 30)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, int(46 + 50 * h)))
            p.drawEllipse(arect)
            draw_icon(p, 'download', arect.adjusted(7, 7, -7, -7), '#FFFFFF', 2.2)


# =========================================================================== charts
class PlanningChart(QWidget):
    """Animated gradient bar chart with hover bubble and 'today' highlight."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self.setMouseTracking(True)
        self.labels, self.values = [], []
        self.highlight = -1
        self._hover = -1
        self._t = 1.0
        self._ta = anim(self, 900)
        self._ta.setStartValue(0.0)
        self._ta.setEndValue(1.0)
        self._ta.valueChanged.connect(self._on_t)
        self.setAccessibleName('مخطط توزيع المهام')
        theme.signals.changed.connect(self.update)

    def _on_t(self, v): self._t = float(v); self.update()

    def replay(self):
        self._ta.stop()
        self._t = 0.0
        self._ta.start()

    def set_data(self, labels, values, highlight=-1):
        labels, values = list(labels), list(values)
        changed = (labels != self.labels or values != self.values)
        self.labels, self.values, self.highlight = labels, values, highlight
        if changed:
            self._hover = -1
            self.replay()
        else:
            self.update()

    def _geom(self):
        w, h = self.width(), self.height()
        ml, mr, mt, mb = 34, 12, 26, 30
        cw, ch = max(1, w - ml - mr), max(1, h - mt - mb)
        return ml, mt, cw, ch

    def mouseMoveEvent(self, e):
        if not self.values:
            return
        ml, mt, cw, ch = self._geom()
        slot = cw / len(self.values)
        i = int((e.position().x() - ml) // slot) if e.position().x() >= ml else -1
        if i >= len(self.values):
            i = -1
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, e): self._hover = -1; self.update(); super().leaveEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        ml, mt, cw, ch = self._geom()
        muted, grid = QColor(P['text_muted']), qc(P['border_strong'], 0.55)
        if not self.values or sum(self.values) == 0:
            p.setPen(QPen(grid, 1, Qt.PenStyle.DashLine))
            p.drawLine(ml, mt + ch, ml + cw, mt + ch)
            p.setPen(QColor(P['text_faint']))
            p.setFont(_font(self.font(), 14, QFont.Weight.DemiBold))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'لا توجد مهام في هذه الفترة')
            return
        maxv = max(self.values)
        step = max(1, math.ceil(maxv / 4))
        top = step * math.ceil(maxv / step)
        p.setFont(_font(self.font(), 11))
        for tick in range(0, top + 1, step):
            y = mt + ch - ch * tick / top
            p.setPen(QPen(grid, 1, Qt.PenStyle.DashLine if tick else Qt.PenStyle.SolidLine))
            p.drawLine(ml, int(y), ml + cw, int(y))
            p.setPen(muted)
            p.drawText(QRectF(0, y - 9, ml - 8, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(tick))
        n = len(self.values)
        slot = cw / n
        bar_w = max(6.0, min(36.0, slot * 0.56))
        stag = 0.55
        ease = QEasingCurve(_OUT_CUBIC)
        label_step = max(1, math.ceil(n / max(1, int(cw / 46))))
        hover_info = None
        for i, (label, val) in enumerate(zip(self.labels, self.values)):
            local = ease.valueForProgress(max(0.0, min(1.0, self._t * (1 + stag) - i / n * stag)))
            x = ml + i * slot + (slot - bar_w) / 2
            bh = ch * val / top * local
            y = mt + ch - bh
            rect = QRectF(x, y, bar_w, max(4.0, bh))
            rect.moveBottom(mt + ch)
            is_hl, is_hover = (i == self.highlight), (i == self._hover)
            if val:
                top_c, bot_c = (QColor('#F472B6'), QColor('#FB923C')) if is_hl else (QColor(P['accent']), QColor(P['cyan']))
                if is_hover:
                    top_c, bot_c = top_c.lighter(112), bot_c.lighter(112)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(qc(top_c, 0.22))
                    p.drawRoundedRect(rect.adjusted(-4, -4, 4, 4), 10, 10)
                g = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
                g.setColorAt(0, top_c)
                g.setColorAt(1, bot_c)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(g))
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(qc(P['border_strong'], 0.6))
                rect = QRectF(x, mt + ch - 5, bar_w, 5)
            p.drawRoundedRect(rect, min(bar_w / 2, 8), min(bar_w / 2, 8))
            if val and n <= 16 and not is_hover and local > 0.95:
                p.setPen(QColor(P['text']))
                p.setFont(_font(self.font(), 11, QFont.Weight.Bold))
                p.drawText(QRectF(x - 10, rect.top() - 20, bar_w + 20, 18), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, str(val))
            if i % label_step == 0:
                short = label if len(label) <= 7 else label[-5:]
                p.setPen(QColor(P['primary_dark']) if is_hl else muted)
                p.setFont(_font(self.font(), 10, QFont.Weight.Bold if is_hl else QFont.Weight.Normal))
                p.drawText(QRectF(ml + i * slot - 14, mt + ch + 6, slot + 28, 18), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, short)
            if is_hover:
                hover_info = (rect, val, label)
        if hover_info:
            rect, val, label = hover_info
            text = f'{val} مهمة  •  {label}'
            fm = QFontMetrics(_font(self.font(), 12, QFont.Weight.DemiBold))
            bw, bh2 = fm.horizontalAdvance(text) + 24, 30
            bx = max(2.0, min(w - bw - 2, rect.center().x() - bw / 2))
            by = max(2.0, rect.top() - bh2 - 10)
            bub = QRectF(bx, by, bw, bh2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(P['tooltip_bg']))
            p.drawRoundedRect(bub, 10, 10)
            p.setPen(QColor(P['tooltip_fg']))
            p.setFont(_font(self.font(), 12, QFont.Weight.DemiBold))
            p.drawText(bub, Qt.AlignmentFlag.AlignCenter, text)


class DonutChart(QWidget):
    """Animated donut with hover pop-out, centre read-out and legend."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(240)
        self.setMouseTracking(True)
        self.items = []
        self._hover = -1
        self._t = 1.0
        self._ta = anim(self, 1000)
        self._ta.setStartValue(0.0)
        self._ta.setEndValue(1.0)
        self._ta.valueChanged.connect(self._on_t)
        theme.signals.changed.connect(self.update)

    def _on_t(self, v): self._t = float(v); self.update()

    def replay(self):
        self._ta.stop()
        self._t = 0.0
        self._ta.start()

    def set_data(self, items):
        items = [(str(l), int(v), str(c)) for l, v, c in items]
        if items == self.items:
            return
        self.items = items
        self._hover = -1
        self.replay()

    def _geom(self):
        legend_h = 52
        d = max(60.0, min(self.width() - 60.0, self.height() - legend_h - 30.0))
        cx, cy = self.width() / 2, 14 + d / 2 + 8
        return QPointF(cx, cy), d, max(14.0, d * 0.16), legend_h

    def mouseMoveEvent(self, e):
        total = sum(v for _, v, _ in self.items)
        if not total:
            return
        c, d, thick, _ = self._geom()
        dx, dy = e.position().x() - c.x(), e.position().y() - c.y()
        dist = math.hypot(dx, dy)
        idx = -1
        if d / 2 - thick - 6 <= dist <= d / 2 + 10:
            ang = math.degrees(math.atan2(dx, -dy)) % 360
            acc = 0.0
            for i, (_, v, _c) in enumerate(self.items):
                acc += v / total * 360
                if ang <= acc:
                    idx = i if v else -1
                    break
        if idx != self._hover:
            self._hover = idx
            self.update()

    def leaveEvent(self, e): self._hover = -1; self.update(); super().leaveEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c, d, thick, legend_h = self._geom()
        total = sum(v for _, v, _ in self.items)
        rect = QRectF(c.x() - d / 2, c.y() - d / 2, d, d).adjusted(thick / 2 + 6, thick / 2 + 6, -thick / 2 - 6, -thick / 2 - 6)
        track = QPen(qc(P['border'], 0.9), thick)
        track.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(track)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)
        nonzero = sum(1 for _, v, _c in self.items if v)
        gap = 3.0 if nonzero > 1 else 0.0
        if total:
            visible = self._t * 360.0
            acc = 0.0
            for i, (label, v, color) in enumerate(self.items):
                if not v:
                    continue
                sweep = v / total * 360.0
                draw = max(0.0, min(sweep, visible - acc))
                if draw > 0:
                    pen = QPen(QColor(color), thick + (7 if i == self._hover else 0))
                    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                    p.setPen(pen)
                    p.drawArc(rect, int((90 - acc - gap / 2) * 16), int(-max(0.5, draw - gap) * 16))
                acc += sweep
        # centre read-out
        p.setPen(QColor(P['text']))
        if self._hover >= 0 and total:
            label, v, color = self.items[self._hover]
            p.setPen(QColor(color))
            p.setFont(_font(self.font(), 30, QFont.Weight.ExtraBold))
            p.drawText(QRectF(c.x() - 60, c.y() - 28, 120, 40), Qt.AlignmentFlag.AlignCenter, str(v))
            p.setPen(QColor(P['text_muted']))
            p.setFont(_font(self.font(), 12, QFont.Weight.DemiBold))
            p.drawText(QRectF(c.x() - 60, c.y() + 10, 120, 20), Qt.AlignmentFlag.AlignCenter, label)
        else:
            p.setFont(_font(self.font(), 32, QFont.Weight.ExtraBold))
            p.drawText(QRectF(c.x() - 60, c.y() - 28, 120, 40), Qt.AlignmentFlag.AlignCenter, str(int(round(total * min(1.0, self._t * 1.2)))))
            p.setPen(QColor(P['text_muted']))
            p.setFont(_font(self.font(), 12, QFont.Weight.DemiBold))
            p.drawText(QRectF(c.x() - 60, c.y() + 10, 120, 20), Qt.AlignmentFlag.AlignCenter, 'إجمالي المهام' if total else 'لا توجد مهام')
        # legend (2 columns)
        p.setFont(_font(self.font(), 12))
        colw = (self.width() - 24) / 2
        for i, (label, v, color) in enumerate(self.items):
            col, row = i % 2, i // 2
            if self.isRightToLeft():
                x = self.width() - 12 - (col + 1) * colw
            else:
                x = 12 + col * colw
            y = self.height() - legend_h + 4 + row * 24
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            dot_x = x + colw - 14 if self.isRightToLeft() else x + 8
            p.drawEllipse(QPointF(dot_x, y + 10), 5, 5)
            p.setPen(QColor(P['text']) if i != self._hover else QColor(color))
            p.drawText(QRectF(x + (8 if self.isRightToLeft() else 20), y, colw - 30, 20),
                       (Qt.AlignmentFlag.AlignRight if self.isRightToLeft() else Qt.AlignmentFlag.AlignLeft) | Qt.AlignmentFlag.AlignVCenter,
                       f'{label}  {v}')


# =========================================================================== table
class HoverTable(QTableWidget):
    """Borderless table with animated row hover and an empty-state message."""

    def __init__(self, rows=0, cols=0, parent=None):
        super().__init__(rows, cols, parent)
        self.hover_row, self.hover_t = -1, 0.0
        self._ha = anim(self, 150)
        self._ha.setStartValue(0.0)
        self._ha.setEndValue(1.0)
        self._ha.valueChanged.connect(self._tick)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.viewport().installEventFilter(self)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(50)
        hh = self.horizontalHeader()
        hh.setStretchLastSection(True)
        hh.setHighlightSections(False)
        hh.setMinimumSectionSize(70)
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeading | Qt.AlignmentFlag.AlignVCenter)
        self._empty = QLabel('', self.viewport())
        self._empty.setObjectName('empty')
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._empty.hide()

    def set_empty_text(self, text):
        self._empty.setText(text)
        self.refresh_empty()

    def refresh_empty(self):
        self._empty.setGeometry(self.viewport().rect())
        self._empty.setVisible(self.rowCount() == 0 and bool(self._empty.text()))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._empty.setGeometry(self.viewport().rect())

    def fit_columns(self, mins=None):
        self.resizeColumnsToContents()
        for c, w in (mins or {}).items():
            if self.columnWidth(c) < w:
                self.setColumnWidth(c, w)
        self.refresh_empty()

    def eventFilter(self, obj, ev):
        if obj is self.viewport():
            t = ev.type()
            if t == QEvent.Type.MouseMove:
                self._set_hover(self.rowAt(int(ev.position().y())))
            elif t == QEvent.Type.Leave:
                self._set_hover(-1)
        return super().eventFilter(obj, ev)

    def _set_hover(self, r):
        if r == self.hover_row:
            return
        old, self.hover_row = self.hover_row, r
        self._ha.stop()
        self.hover_t = 0.0
        self._repaint_row(old)
        if r >= 0:
            self._ha.start()
        self._repaint_row(r)

    def _tick(self, v):
        self.hover_t = float(v)
        self._repaint_row(self.hover_row)

    def _repaint_row(self, r):
        if 0 <= r < self.rowCount():
            self.viewport().update(0, self.rowViewportPosition(r), self.viewport().width(), self.rowHeight(r))


class TaskDelegate(QStyledItemDelegate):
    """Paints task rows: tinted backgrounds, avatar chips, status pills, priority meters.
    `kinds` maps column -> 'text' | 'title' | 'muted' | 'person' | 'pill' | 'priority'."""

    def __init__(self, table, kinds):
        super().__init__(table)
        self.table, self.kinds = table, kinds

    def sizeHint(self, option, index):
        kind = self.kinds.get(index.column(), 'text')
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or '')
        f = QFont(option.font)
        if kind == 'title':
            f.setWeight(QFont.Weight.DemiBold)
        w = QFontMetrics(f).horizontalAdvance(text)
        extra = {'text': 30, 'muted': 30, 'title': 34, 'person': 30 + 38, 'pill': 28 + 26, 'chip': 28 + 22}.get(kind, 30)
        if kind == 'priority':
            return QSize(124, 50)
        if kind == 'progress':
            return QSize(118, 50)
        return QSize(w + extra, 50)

    def paint(self, p, option, index):
        kind = self.kinds.get(index.column(), 'text')
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        rect = QRectF(opt.rect)
        row, col = index.row(), index.column()
        state = index.data(ROLE_STATE) or 'scheduled'
        rtl = opt.direction == Qt.LayoutDirection.RightToLeft
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # ---- row background
        if row % 2:
            p.fillRect(rect, qc(P['surface_alt'], 0.55))
        if state == 'late':
            p.fillRect(rect, qc(P['danger'], 0.10))
        elif state == 'done':
            p.fillRect(rect, qc(P['success'], 0.08))
        if row == self.table.hover_row and not selected:
            p.fillRect(rect, qc(P['primary'], 0.10 * max(0.25, self.table.hover_t)))
        if selected:
            p.fillRect(rect, qc(P['primary'], 0.17))
            if col == 0:
                bar = QRectF(rect.right() - 4 if rtl else rect.left(), rect.top() + 7, 4, rect.height() - 14)
                g = QLinearGradient(bar.topLeft(), bar.bottomLeft())
                g.setColorAt(0, QColor(P['primary']))
                g.setColorAt(1, QColor(P['accent']))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(g))
                p.drawRoundedRect(bar, 2, 2)
        else:
            p.setPen(QPen(qc(P['border'], 0.7), 1))
            p.drawLine(QPointF(rect.left(), rect.bottom() - 0.5), QPointF(rect.right(), rect.bottom() - 0.5))
        inner = rect.adjusted(14, 0, -14, 0)
        dim = state in ('done', 'cancel')
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or '')
        align = opt.displayAlignment | Qt.AlignmentFlag.AlignVCenter

        def lead(offset, width):
            return inner.right() - offset - width if rtl else inner.left() + offset

        if kind == 'pill':
            fg, bg, dot = theme.status_colors(index.data(ROLE_PILL) or 'scheduled')
            f = _font(opt.font, 12, QFont.Weight.DemiBold)
            p.setFont(f)
            tw = QFontMetrics(f).horizontalAdvance(text)
            pw = tw + 36
            pr = QRectF(lead(0, pw), rect.center().y() - 13, pw, 26)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(pr, 13, 13)
            p.setBrush(dot)
            dx = pr.right() - 13 if rtl else pr.left() + 13
            p.drawEllipse(QPointF(dx, pr.center().y()), 3.5, 3.5)
            p.setPen(fg)
            tr = QRectF(pr.left() + (10 if rtl else 22), pr.top(), pr.width() - 32, pr.height())
            p.drawText(tr, Qt.AlignmentFlag.AlignCenter, text)
        elif kind == 'priority':
            v = int(index.data(ROLE_PRIO) or 1)
            c1, c2 = theme.priority_colors(v)
            bw = 62.0
            bx = lead(0, bw)
            track = QRectF(bx, rect.center().y() - 4, bw, 8)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc(P['border_strong'], 0.55))
            p.drawRoundedRect(track, 4, 4)
            fill = QRectF(track)
            fill.setWidth(bw * v / 10)
            if rtl:
                fill.moveRight(track.right())
            g = QLinearGradient(fill.left(), 0, fill.right(), 0)
            g.setColorAt(0, c1)
            g.setColorAt(1, c2)
            p.setBrush(QBrush(g))
            p.drawRoundedRect(fill, 4, 4)
            p.setPen(c2)
            p.setFont(_font(opt.font, 13, QFont.Weight.Bold))
            p.drawText(QRectF(lead(bw + 8, 26), rect.top(), 26, rect.height()), Qt.AlignmentFlag.AlignCenter, str(v))
        elif kind == 'person':
            c1, c2 = theme.avatar_gradient(text)
            d = 30.0
            ar = QRectF(lead(0, d), rect.center().y() - d / 2, d, d)
            g = QLinearGradient(ar.topLeft(), ar.bottomRight())
            g.setColorAt(0, c1)
            g.setColorAt(1, c2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(ar)
            p.setPen(QColor('#FFFFFF'))
            p.setFont(_font(opt.font, 14, QFont.Weight.Bold))
            p.drawText(ar, Qt.AlignmentFlag.AlignCenter, (text.strip()[:1] or '?').upper())
            f = _font(opt.font, 13, QFont.Weight.Medium)
            p.setFont(f)
            p.setPen(QColor(P['text_muted'] if dim else P['text']))
            tr = QRectF(inner.left() + (0 if rtl else d + 10), rect.top(), inner.width() - d - 10, rect.height())
            if rtl:
                tr.setRight(inner.right() - d - 10)
            p.drawText(tr, align, QFontMetrics(f).elidedText(text, Qt.TextElideMode.ElideRight, int(tr.width())))
        elif kind == 'chip':
            if text:
                f = _font(opt.font, 12, QFont.Weight.DemiBold)
                p.setFont(f)
                pw = min(QFontMetrics(f).horizontalAdvance(text) + 22, inner.width())
                pr = QRectF(lead(0, pw), rect.center().y() - 12, pw, 24)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(qc(P['primary'], 0.14))
                p.drawRoundedRect(pr, 12, 12)
                p.setPen(QColor(P['primary_dark']))
                p.drawText(pr, Qt.AlignmentFlag.AlignCenter, QFontMetrics(f).elidedText(text, Qt.TextElideMode.ElideRight, int(pw - 10)))
        elif kind == 'progress':
            try:
                d, tt = [int(x) for x in text.split('/')]
            except ValueError:
                d, tt = 0, 0
            if tt == 0:
                p.setPen(QColor(P['text_faint']))
                p.setFont(_font(opt.font, 13))
                p.drawText(QRectF(lead(0, 40), rect.top(), 40, rect.height()), Qt.AlignmentFlag.AlignCenter, '—')
            else:
                bw = 56.0
                track = QRectF(lead(0, bw), rect.center().y() - 4, bw, 8)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(qc(P['border_strong'], 0.55))
                p.drawRoundedRect(track, 4, 4)
                fill = QRectF(track)
                fill.setWidth(max(6.0, bw * d / tt) if d else 0.0)
                if rtl:
                    fill.moveRight(track.right())
                g = QLinearGradient(fill.left(), 0, fill.right(), 0)
                g.setColorAt(0, QColor('#34D399'))
                g.setColorAt(1, QColor('#10B981'))
                p.setBrush(QBrush(g))
                if d:
                    p.drawRoundedRect(fill, 4, 4)
                p.setPen(QColor(P['text_muted']))
                p.setFont(_font(opt.font, 12, QFont.Weight.DemiBold))
                p.drawText(QRectF(lead(bw + 8, 34), rect.top(), 34, rect.height()), Qt.AlignmentFlag.AlignCenter, f'{d}/{tt}')
        else:
            f = QFont(opt.font)
            f.setPixelSize(13)
            if kind == 'title':
                f.setWeight(QFont.Weight.DemiBold)
                f.setStrikeOut(state in ('done', 'cancel'))
            p.setFont(f)
            color = P['text_muted'] if (dim or kind == 'muted') else P['text']
            p.setPen(QColor(color))
            p.drawText(inner, align, QFontMetrics(f).elidedText(text, Qt.TextElideMode.ElideRight, int(inner.width())))
        p.restore()


# =========================================================================== toast
class Toast(QWidget):
    """Slide-up notification pill, drawn manually (gradient + shadow)."""
    M = 18
    KINDS = {'success': ('#10B981', '#14B8A6', 'check_circle'), 'info': ('#6366F1', '#8B5CF6', 'check_circle'),
             'warn': ('#F59E0B', '#F97316', 'alert'), 'error': ('#F43F5E', '#FB7185', 'alert')}

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._text, self._kind = '', 'success'
        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(0.0)
        self.setGraphicsEffect(self._fx)
        self._oa = QPropertyAnimation(self._fx, b'opacity', self)
        self._pa = QPropertyAnimation(self, b'pos', self)
        self._oa.finished.connect(self._after)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._out)
        self.hide()

    def show_message(self, text, kind='success'):
        self._text, self._kind = text, kind if kind in self.KINDS else 'info'
        f = _font(self.font(), 14, QFont.Weight.DemiBold)
        w = QFontMetrics(f).horizontalAdvance(text) + 96 + 2 * self.M
        h = 56 + 2 * self.M
        self.resize(w, h)
        pw, ph = self.parentWidget().width(), self.parentWidget().height()
        x, y = (pw - w) // 2, ph - h - 22
        self._timer.stop()
        self._oa.stop()
        self._pa.stop()
        self.move(x, y + 20)
        self.show()
        self.raise_()
        self.update()
        self._oa.setDuration(220)
        self._oa.setStartValue(self._fx.opacity())
        self._oa.setEndValue(1.0)
        self._pa.setDuration(320)
        self._pa.setEasingCurve(QEasingCurve.Type.OutBack)
        self._pa.setStartValue(self.pos())
        self._pa.setEndValue(QPoint(x, y))
        self._oa.start()
        self._pa.start()
        self._timer.start(2800)

    def _out(self):
        self._oa.stop()
        self._oa.setDuration(320)
        self._oa.setStartValue(self._fx.opacity())
        self._oa.setEndValue(0.0)
        self._oa.start()

    def _after(self):
        if self._fx.opacity() < 0.01:
            self.hide()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c1, c2, icon = self.KINDS[self._kind]
        vr = QRectF(self.rect()).adjusted(self.M, self.M, -self.M, -self.M)
        paint_shadow(p, vr, vr.height() / 2, qc(c2, 0.45), spread=14, dy=6)
        path = QPainterPath()
        path.addRoundedRect(vr, vr.height() / 2, vr.height() / 2)
        g = QLinearGradient(vr.left(), 0, vr.right(), 0)
        g.setColorAt(0, QColor(c1))
        g.setColorAt(1, QColor(c2))
        p.fillPath(path, g)
        rtl = self.isRightToLeft()
        ic = QRectF((vr.right() - 14 - 30) if rtl else (vr.left() + 14), vr.center().y() - 15, 30, 30)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 60))
        p.drawEllipse(ic)
        draw_icon(p, icon, ic.adjusted(6, 6, -6, -6), '#FFFFFF', 2.2)
        tr = QRectF(vr.left() + (22 if rtl else 56), vr.top(), vr.width() - 78, vr.height())
        p.setPen(QColor('#FFFFFF'))
        p.setFont(_font(self.font(), 14, QFont.Weight.DemiBold))
        p.drawText(tr, Qt.AlignmentFlag.AlignCenter, self._text)


# =========================================================================== dialogs
class DialogHeader(QWidget):
    def __init__(self, title, subtitle='', icon='tasks', parent=None):
        super().__init__(parent)
        self.title, self.subtitle, self.icon = title, subtitle, icon
        self.setFixedHeight(92)
        theme.signals.changed.connect(self.update)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor(P['hero_a']))
        g.setColorAt(0.6, QColor(P['hero_b']))
        g.setColorAt(1, QColor(P['hero_c']))
        p.fillRect(r, g)
        p.setPen(QPen(QColor(255, 255, 255, 34), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        rtl = self.isRightToLeft()
        ex = r.left() + 30 if rtl else r.right() - 30
        for rad in (60, 100, 140):
            p.drawEllipse(QPointF(ex, r.bottom() + 10), rad, rad)
        gl = QLinearGradient(0, 0, 0, r.height())
        gl.setColorAt(0, QColor(255, 255, 255, 40))
        gl.setColorAt(0.6, QColor(255, 255, 255, 0))
        p.fillRect(r, gl)
        bx = r.right() - 24 - 52 if rtl else r.left() + 24
        badge = QRectF(bx, r.center().y() - 26, 52, 52)
        p.setPen(QPen(QColor(255, 255, 255, 110), 1.2))
        p.setBrush(QColor(255, 255, 255, 52))
        p.drawRoundedRect(badge, 17, 17)
        draw_icon(p, self.icon, badge.adjusted(13, 13, -13, -13), '#FFFFFF', 2.0)
        align = Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft
        tx = QRectF(r.left() + 24, 0, r.width() - 48 - 52 - 14, 0)
        if rtl:
            tx.moveLeft(r.left() + 24)
        else:
            tx.moveLeft(r.left() + 24 + 52 + 14)
        p.setPen(QColor('#FFFFFF'))
        p.setFont(_font(self.font(), 20, QFont.Weight.ExtraBold))
        p.drawText(QRectF(tx.left(), r.center().y() - 28, tx.width(), 32), align | Qt.AlignmentFlag.AlignVCenter, self.title)
        if self.subtitle:
            p.setPen(QColor(255, 255, 255, 215))
            p.setFont(_font(self.font(), 12))
            p.drawText(QRectF(tx.left(), r.center().y() + 4, tx.width(), 22), align | Qt.AlignmentFlag.AlignVCenter, self.subtitle)


def fit_dialog_to_screen(dlg, margin_w=40, margin_h=70):
    """Shrink a dialog that is bigger than the screen and keep it fully visible (it stays resizable by the user)."""
    scr = dlg.screen() or QGuiApplication.primaryScreen()
    if scr is None:
        return
    g = scr.availableGeometry()
    max_w, max_h = max(320, g.width() - margin_w), max(300, g.height() - margin_h)
    dlg.setMinimumWidth(min(dlg.minimumWidth(), max_w))
    dlg.resize(min(dlg.width(), max_w), min(dlg.height(), max_h))
    fg = dlg.frameGeometry()
    x = max(g.left(), min(fg.left(), g.right() - fg.width() + 1))
    y = max(g.top(), min(fg.top(), g.bottom() - fg.height() + 1))
    dlg.move(x, y)


class FancyDialog(QDialog):
    """Dialog shell: gradient title strip, content area (`self.cl`), fade-in on first show."""

    def __init__(self, title, subtitle='', icon='tasks', parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(DialogHeader(title, subtitle, icon))
        self.content = QWidget()
        self.cl = QVBoxLayout(self.content)
        self.cl.setContentsMargins(26, 22, 26, 22)
        self.cl.setSpacing(14)
        root.addWidget(self.content, 1)
        self._faded = False
        self._fade = None

    def showEvent(self, e):
        super().showEvent(e)
        if not self._faded:
            self._faded = True
            fit_dialog_to_screen(self)
            self.setWindowOpacity(0.0)
            a = QPropertyAnimation(self, b'windowOpacity', self)
            a.setDuration(220)
            a.setStartValue(0.0)
            a.setEndValue(1.0)
            a.setEasingCurve(_OUT_CUBIC)
            self._fade = a
            a.start()


class PriorityEdit(QWidget):
    """Slider + coloured badge, drop-in replacement for the priority QSpinBox."""
    valueChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, 10)
        self.slider.setValue(5)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.badge = QLabel()
        self.badge.setFixedWidth(66)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.badge)
        self.slider.valueChanged.connect(self._sync)
        self._sync(5)

    def value(self): return self.slider.value()
    def setValue(self, v): self.slider.setValue(int(v))

    def _sync(self, v):
        c1, c2 = theme.priority_colors(v)
        self.badge.setText(f'{v}/10')
        self.badge.setStyleSheet(f'background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {c1.name()},stop:1 {c2.name()});'
                                 'color:white;border-radius:12px;font-weight:700;padding:5px 0;')
        self.valueChanged.emit(v)


# =========================================================================== message helpers
def _box(parent, icon, title, text, buttons):
    box = QMessageBox(icon, title, text, QMessageBox.StandardButton.NoButton, parent)
    roles = {'accept': QMessageBox.ButtonRole.AcceptRole, 'reject': QMessageBox.ButtonRole.RejectRole,
             'destructive': QMessageBox.ButtonRole.DestructiveRole}
    made = []
    for label, role in buttons:
        b = box.addButton(label, roles[role])
        if role == 'reject':
            b.setProperty('secondary', True)
        elif role == 'destructive':
            b.setProperty('danger', True)
        made.append(b)
    box.exec()
    clicked = box.clickedButton()
    return made.index(clicked) if clicked in made else -1


def info(parent, title, text):
    _box(parent, QMessageBox.Icon.Information, title, text, [('حسنًا', 'accept')])


def warn(parent, title, text):
    _box(parent, QMessageBox.Icon.Warning, title, text, [('حسنًا', 'accept')])


def error(parent, title, text):
    _box(parent, QMessageBox.Icon.Critical, title, text, [('إغلاق', 'accept')])


def ask(parent, title, text, yes='نعم', no='إلغاء', danger=False) -> bool:
    return _box(parent, QMessageBox.Icon.Question, title, text,
                [(yes, 'destructive' if danger else 'accept'), (no, 'reject')]) == 0


def ask_choice(parent, title, text, buttons) -> int:
    """buttons: [(label, 'accept'|'destructive'|'reject'), ...] -> index of clicked button or -1."""
    return _box(parent, QMessageBox.Icon.Question, title, text, buttons)


# =========================================================================== date / time inputs
# Qt's QTimeEdit / QDateEdit reorder their sections in right-to-left apps (21:26 -> 26:21).
# These replacements are always laid out left-to-right and never flip.
class _TimePart(QLineEdit):
    """Two-digit number box (hours or minutes) built on a plain QLineEdit.

    A QLineEdit is used instead of a QSpinBox because the style sheet's spin-box button rules collapsed the
    spin box's edit area, so the digits were not drawn. Up/Down keys and the mouse wheel step the value."""

    def __init__(self, maximum, parent=None):
        super().__init__(parent)
        self._max = maximum
        self.setMaxLength(2)
        self.setValidator(QIntValidator(0, maximum, self))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setText('00')

    def value(self):
        try:
            return min(max(int(self.text() or 0), 0), self._max)
        except ValueError:
            return 0

    def setValue(self, v):
        self.setText(f'{min(max(int(v), 0), self._max):02d}')

    def _step(self, d):
        self.setValue((self.value() + d) % (self._max + 1))
        self.selectAll()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Up:
            self._step(1)
        elif e.key() == Qt.Key.Key_Down:
            self._step(-1)
        else:
            super().keyPressEvent(e)

    def wheelEvent(self, e):
        if self.hasFocus():
            self._step(1 if e.angleDelta().y() > 0 else -1)
            e.accept()
        else:
            e.ignore()

    def focusInEvent(self, e):
        super().focusInEvent(e)
        QTimer.singleShot(0, self.selectAll)

    def focusOutEvent(self, e):
        self.setValue(self.value())                 # pad to two digits and clamp (e.g. "7" -> "07", empty -> "00")
        super().focusOutEvent(e)


class TimeBox(QWidget):
    """HH : mm editor (two plain number boxes). API: time() / setTime(QTime)."""

    def __init__(self, t=None, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.h, self.m = _TimePart(23), _TimePart(59)
        for s in (self.h, self.m):
            s.setObjectName('timePart')
        colon = QLabel(':')
        colon.setObjectName('timeColon')
        lay.addWidget(self.h)
        lay.addWidget(colon)
        lay.addWidget(self.m)
        self.setTime(t if t is not None else QTime.currentTime())

    def time(self):
        return QTime(self.h.value(), self.m.value())

    def setTime(self, t):
        if t is not None and t.isValid():
            self.h.setValue(t.hour())
            self.m.setValue(t.minute())


class DateBox(QWidget):
    """yyyy-MM-dd field with a calendar pop-up. API: date() / setDate(QDate) / dateChanged."""
    dateChanged = Signal(QDate)

    def __init__(self, date=None, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._date = QDate(date) if date is not None else QDate.currentDate()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setReadOnly(True)
        self.edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit.setCursor(Qt.CursorShape.PointingHandCursor)
        act = self.edit.addAction(QIcon(theme.icon_pixmap('calendar', P['text_muted'], 18)), QLineEdit.ActionPosition.TrailingPosition)
        act.triggered.connect(self.open_popup)
        self.edit.installEventFilter(self)
        lay.addWidget(self.edit)
        self.cal = QCalendarWidget(self)
        self.cal.setWindowFlags(Qt.WindowType.Popup)
        self.cal.clicked.connect(self._picked)
        self._sync()

    def _sync(self):
        self.edit.setText(self._date.toString('yyyy-MM-dd'))

    def date(self):
        return self._date

    def setDate(self, d):
        if d is None or not d.isValid() or d == self._date:
            return
        self._date = QDate(d)
        self._sync()
        self.dateChanged.emit(self._date)

    def eventFilter(self, o, e):
        if o is self.edit and e.type() == QEvent.Type.MouseButtonRelease:
            self.open_popup()
            return True
        return False

    def open_popup(self, *_):
        self.cal.setSelectedDate(self._date)
        pos = self.mapToGlobal(QPoint(0, self.height() + 4))
        scr = self.screen() or QGuiApplication.primaryScreen()
        if scr is not None:                                  # keep the calendar fully on screen
            g = scr.availableGeometry()
            size = self.cal.sizeHint().expandedTo(self.cal.size())
            if pos.y() + size.height() > g.bottom():
                pos.setY(self.mapToGlobal(QPoint(0, -4)).y() - size.height())
            pos.setX(max(g.left(), min(pos.x(), g.right() - size.width())))
            pos.setY(max(g.top(), pos.y()))
        self.cal.move(pos)
        self.cal.show()

    def _picked(self, d):
        self.setDate(d)
        self.cal.hide()


# =========================================================================== extra inputs / helpers
class Dot(QWidget):
    def __init__(self, color, size=12, parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self.setFixedSize(size, size)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.color)
        p.drawEllipse(QRectF(self.rect()).adjusted(1, 1, -1, -1))


class ChecklistEditor(QWidget):
    """Editable sub-task list: [checkbox][text][remove]. items() -> [(title, done)]."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(6)
        lay.addLayout(self.rows)
        self._rows = []
        bar = QHBoxLayout()
        add = Btn('إضافة بند', 'ghost', 'plus')
        add.clicked.connect(lambda _=False: self.add_row(focus=True))
        bar.addWidget(add)
        bar.addStretch()
        lay.addLayout(bar)

    def add_row(self, title='', done=False, focus=False):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        cb = QCheckBox()
        cb.setChecked(bool(done))
        ed = QLineEdit(title)
        ed.setPlaceholderText('بند جديد...')
        rm = Btn('', 'ghost', 'trash')
        rm.clicked.connect(lambda _=False, w=w: self._remove(w))
        h.addWidget(cb)
        h.addWidget(ed, 1)
        h.addWidget(rm)
        self.rows.addWidget(w)
        self._rows.append((w, cb, ed))
        if focus:
            ed.setFocus()

    def _remove(self, w):
        self._rows = [r for r in self._rows if r[0] is not w]
        self.rows.removeWidget(w)
        w.deleteLater()

    def items(self):
        return [(ed.text().strip(), cb.isChecked()) for _, cb, ed in self._rows if ed.text().strip()]

    def set_items(self, items):
        for w, _, _ in list(self._rows):
            self._remove(w)
        for title, done in items:
            self.add_row(title, done)


class AccentSwatch(QWidget):
    """Round gradient colour-theme picker."""
    clicked = Signal(str)

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.name = name
        self._h = 0.0
        self.setFixedSize(84, 96)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._ha = anim(self, 180)
        self._ha.valueChanged.connect(self._on_h)
        theme.signals.changed.connect(self.update)

    def _on_h(self, v): self._h = float(v); self.update()
    def enterEvent(self, e): _retarget(self._ha, self._h, 1.0); super().enterEvent(e)
    def leaveEvent(self, e): _retarget(self._ha, self._h, 0.0); super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if self.rect().contains(e.position().toPoint()):
            self.clicked.emit(self.name)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c1, c2, glow, _hero = theme.ACCENTS[self.name]
        d = 46 + 6 * self._h
        c = QPointF(self.width() / 2, 34)
        r = QRectF(c.x() - d / 2, c.y() - d / 2, d, d)
        paint_shadow(p, r, d / 2, qc(c2, 0.35 + 0.15 * self._h), spread=8, dy=3)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor(c1))
        g.setColorAt(1, QColor(c2))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(r)
        sel = theme.current_accent() == self.name
        if sel:
            p.setPen(QPen(QColor(P['text']), 2.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(r.adjusted(-5, -5, 5, 5))
            draw_icon(p, 'check', r.adjusted(13, 13, -13, -13), '#FFFFFF', 2.6)
        p.setPen(QColor(P['text'] if sel else P['text_muted']))
        p.setFont(_font(self.font(), 12, QFont.Weight.Bold if sel else QFont.Weight.Medium))
        p.drawText(QRectF(0, 66, self.width(), 24), Qt.AlignmentFlag.AlignCenter, theme.ACCENT_LABELS[self.name])


class CommandPalette(QDialog):
    """Ctrl+K quick launcher. actions: [(label, hint, callable)]."""

    def __init__(self, actions, parent=None):
        super().__init__(parent)
        self.setObjectName('palette')
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.actions = actions
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)
        self.input = QLineEdit()
        self.input.setObjectName('paletteInput')
        self.input.setPlaceholderText('اكتب أمرًا...  (مثال: مهمة جديدة)')
        self.list = QListWidget()
        self.list.setObjectName('paletteList')
        lay.addWidget(self.input)
        lay.addWidget(self.list)
        self.resize(560, 420)
        fit_dialog_to_screen(self)
        self.input.textChanged.connect(self._fill)
        self.input.installEventFilter(self)
        self.list.itemClicked.connect(self._run)
        self._fill('')

    def _fill(self, text):
        self.list.clear()
        q = text.strip().lower()
        for i, (label, hint, _fn) in enumerate(self.actions):
            if q in label.lower():
                it = QListWidgetItem(f'{label}        {hint}' if hint else label)
                it.setData(256, i)
                self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    def eventFilter(self, o, e):
        if o is self.input and e.type() == QEvent.Type.KeyPress:
            k = e.key()
            if k in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                row = self.list.currentRow() + (1 if k == Qt.Key.Key_Down else -1)
                self.list.setCurrentRow(max(0, min(self.list.count() - 1, row)))
                return True
            if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._run(self.list.currentItem())
                return True
        return False

    def _run(self, item):
        if item is None:
            return
        fn = self.actions[item.data(256)][2]
        self.accept()
        QTimer.singleShot(0, fn)

    def showEvent(self, e):
        super().showEvent(e)
        par = self.parentWidget()
        if par is not None:
            g = par.geometry()
            self.move(par.mapToGlobal(QPoint(0, 0)) + QPoint((g.width() - self.width()) // 2, int(g.height() * 0.16)))
        self.input.setFocus()
