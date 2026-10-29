"""views.py - the feature pages: dashboard, kanban board, month calendar, activity log, settings."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, QRectF, QPointF, QSize, QTimer, QEasingCurve, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QFontMetrics, QLinearGradient, QPainterPath
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame, QListWidget, QListWidgetItem,
                               QAbstractItemView, QStyledItemDelegate, QStyle, QSpinBox, QCheckBox, QTableWidgetItem)

import logic
import theme
from theme import P, qc, mix, paint_shadow, draw_icon, STATUS_KEYS
from widgets import (Card, Btn, Combo, Dot, HoverTable, TaskDelegate, GradCard, AccentSwatch, ROLE_ID, ROLE_STATE,
                     ROLE_PRIO, ROLE_PILL, _font, anim)

ROLE_TASK = 260
ASC = Qt.AlignmentFlag


def ltr(text):
    """Wrap text so digits / ranges keep their order inside RTL paragraphs."""
    return '\u202a' + text + '\u202c'


def put_rows(table, entries, mins=None):
    """entries: [{'id', 'state', 'prio', 'cells': [(text, pill_key_or_None), ...]}]"""
    table.setUpdatesEnabled(False)
    table.setRowCount(0)
    for e in entries:
        r = table.rowCount()
        table.insertRow(r)
        for c, (text, pill) in enumerate(e['cells']):
            it = QTableWidgetItem(str(text))
            if c == 0 and e.get('id') is not None:
                it.setData(ROLE_ID, e['id'])
            it.setData(ROLE_STATE, e.get('state', 'scheduled'))
            it.setData(ROLE_PRIO, e.get('prio', 1))
            it.setData(ROLE_PILL, pill or 'scheduled')
            table.setItem(r, c, it)
    table.setUpdatesEnabled(True)
    table.fit_columns(mins)


def page_scroll(inner: QWidget) -> QScrollArea:
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setFrameShape(QFrame.Shape.NoFrame)
    s.setWidget(inner)
    inner.setAutoFillBackground(False)
    s.viewport().setAutoFillBackground(False)
    s.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    return s


def title_label(text, name='cardTitle'):
    l = QLabel(text)
    l.setObjectName(name)
    return l


# =========================================================================== charts
def smooth_path(pts, lo, hi):
    path = QPainterPath(pts[0])
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        c1 = QPointF(p1.x() + (p2.x() - p0.x()) / 6, max(lo, min(hi, p1.y() + (p2.y() - p0.y()) / 6)))
        c2 = QPointF(p2.x() - (p3.x() - p1.x()) / 6, max(lo, min(hi, p2.y() - (p3.y() - p1.y()) / 6)))
        path.cubicTo(c1, c2, p2)
    return path


class WorkloadChart(QWidget):
    """Stacked horizontal bars per person: done / waiting / late."""
    COLORS = (('منجزة', '#10B981'), ('قيد الانتظار', '#6366F1'), ('متأخرة', '#F43F5E'))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self._t = 1.0
        self.setMinimumHeight(190)
        self._ta = anim(self, 900)
        self._ta.setStartValue(0.0)
        self._ta.setEndValue(1.0)
        self._ta.valueChanged.connect(self._on_t)
        theme.signals.changed.connect(self.update)

    def _on_t(self, v): self._t = float(v); self.update()

    def replay(self):
        self._ta.stop(); self._t = 0.0; self._ta.start()

    def set_data(self, rows):
        rows = [tuple(r) for r in rows]
        if rows == self.rows:
            return
        self.rows = rows
        self.setMinimumHeight(max(190, 50 + len(rows) * 38))
        self.replay()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W = self.width()
        rtl = self.isRightToLeft()

        def X(x, w):
            return W - x - w if rtl else x
        lead = ASC.AlignRight if rtl else ASC.AlignLeft
        # legend
        p.setFont(_font(self.font(), 12))
        off = 0
        for label, col in self.COLORS:
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(col))
            p.drawEllipse(QPointF(X(off, 10) + 5, 12), 5, 5)
            p.setPen(QColor(P['text_muted']))
            p.drawText(QRectF(X(off + 16, 86), 2, 86, 20), lead | ASC.AlignVCenter, label)
            off += 104
        if not self.rows:
            p.setPen(QColor(P['text_faint'])); p.setFont(_font(self.font(), 14, QFont.Weight.DemiBold))
            p.drawText(self.rect(), ASC.AlignCenter, 'لا توجد بيانات للفريق بعد'); return
        name_w, num_w = 150, 44
        bw = max(80.0, W - name_w - num_w - 24)
        mx = max(1, max(sum(r[1:]) for r in self.rows))
        ease = QEasingCurve(QEasingCurve.Type.OutCubic)
        for i, (name, done, wait, late) in enumerate(self.rows):
            y = 40 + i * 38
            c1, c2 = theme.avatar_gradient(name)
            av = QRectF(X(0, 26), y, 26, 26)
            g = QLinearGradient(av.topLeft(), av.bottomRight()); g.setColorAt(0, c1); g.setColorAt(1, c2)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(g)); p.drawEllipse(av)
            p.setPen(QColor('#FFFFFF')); p.setFont(_font(self.font(), 13, QFont.Weight.Bold))
            p.drawText(av, ASC.AlignCenter, (name.strip()[:1] or '?').upper())
            p.setPen(QColor(P['text'])); p.setFont(_font(self.font(), 13, QFont.Weight.Medium))
            p.drawText(QRectF(X(34, name_w - 40), y, name_w - 40, 26), lead | ASC.AlignVCenter,
                       QFontMetrics(p.font()).elidedText(name, Qt.TextElideMode.ElideRight, name_w - 44))
            track = QRectF(X(name_w, bw), y + 7, bw, 12)
            p.setBrush(qc(P['border_strong'], 0.45)); p.drawRoundedRect(track, 6, 6)
            clip = QPainterPath(); clip.addRoundedRect(track, 6, 6)
            p.save(); p.setClipPath(clip)
            acc = 0.0
            for val, (_l, col) in zip((done, wait, late), self.COLORS):
                if not val:
                    continue
                w = bw * val / mx * ease.valueForProgress(self._t)
                p.setBrush(QColor(col))
                p.drawRect(QRectF(X(name_w + acc, w), y + 7, w, 12))
                acc += w
            p.restore()
            p.setPen(QColor(P['text_muted'])); p.setFont(_font(self.font(), 13, QFont.Weight.Bold))
            p.drawText(QRectF(X(name_w + bw + 8, num_w - 8), y, num_w - 8, 26), lead | ASC.AlignVCenter, str(done + wait + late))


class TrendChart(QWidget):
    """Smooth area/line chart with several series and hover read-out."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.labels, self.series = [], []
        self._t, self._hover = 1.0, -1
        self.setMinimumHeight(240)
        self.setMouseTracking(True)
        self._ta = anim(self, 1100)
        self._ta.setStartValue(0.0)
        self._ta.setEndValue(1.0)
        self._ta.valueChanged.connect(self._on_t)
        theme.signals.changed.connect(self.update)

    def _on_t(self, v): self._t = float(v); self.update()

    def replay(self):
        self._ta.stop(); self._t = 0.0; self._ta.start()

    def set_data(self, labels, series):
        labels, series = list(labels), [(n, list(v), c) for n, v, c in series]
        changed = labels != self.labels or series != self.series
        self.labels, self.series = labels, series
        if changed:
            self._hover = -1; self.replay()
        else:
            self.update()

    def _geom(self):
        return 34, 36, max(1, self.width() - 34 - 16), max(1, self.height() - 36 - 30)

    def mouseMoveEvent(self, e):
        n = len(self.labels)
        if n < 2:
            return
        ml, mt, cw, ch = self._geom()
        i = int(round((e.position().x() - ml) / cw * (n - 1)))
        i = i if 0 <= i < n else -1
        if i != self._hover:
            self._hover = i; self.update()

    def leaveEvent(self, e): self._hover = -1; self.update(); super().leaveEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ml, mt, cw, ch = self._geom()
        n = len(self.labels)
        muted = QColor(P['text_muted']); grid = qc(P['border_strong'], 0.55)
        # legend
        p.setFont(_font(self.font(), 12))
        off, W = 0, self.width()
        rtl = self.isRightToLeft()
        for name, _v, col in self.series:
            x0 = W - 14 - off - 110 if rtl else 14 + off
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(col))
            p.drawRoundedRect(QRectF(x0 + (100 if rtl else 0), 10, 10, 10), 3, 3)
            p.setPen(muted)
            p.drawText(QRectF(x0 if rtl else x0 + 16, 4, 94, 22), (ASC.AlignRight if rtl else ASC.AlignLeft) | ASC.AlignVCenter, name)
            off += 124
        allv = [v for _n, vals, _c in self.series for v in vals]
        if n < 2 or not allv or max(allv) == 0:
            p.setPen(QColor(P['text_faint'])); p.setFont(_font(self.font(), 14, QFont.Weight.DemiBold))
            p.drawText(self.rect(), ASC.AlignCenter, 'لا توجد بيانات كافية بعد'); return
        maxv = max(allv); step = max(1, math.ceil(maxv / 4)); top = step * math.ceil(maxv / step)
        p.setFont(_font(self.font(), 11))
        for tick in range(0, top + 1, step):
            y = mt + ch - ch * tick / top
            p.setPen(QPen(grid, 1, Qt.PenStyle.DashLine if tick else Qt.PenStyle.SolidLine)); p.drawLine(ml, int(y), ml + cw, int(y))
            p.setPen(muted); p.drawText(QRectF(0, y - 9, ml - 8, 18), ASC.AlignRight | ASC.AlignVCenter, str(tick))
        xs = [ml + cw * i / (n - 1) for i in range(n)]
        p.save()
        p.setClipRect(QRectF(0, 0, ml + (self.width() - ml) * self._t + 2, self.height()))
        for name, vals, col in self.series:
            pts = [QPointF(xs[i], mt + ch - ch * v / top) for i, v in enumerate(vals)]
            line = smooth_path(pts, mt, mt + ch)
            area = QPainterPath(line); area.lineTo(xs[-1], mt + ch); area.lineTo(xs[0], mt + ch); area.closeSubpath()
            g = QLinearGradient(0, mt, 0, mt + ch); g.setColorAt(0, qc(col, 0.30)); g.setColorAt(1, qc(col, 0.0))
            p.fillPath(area, g)
            pen = QPen(QColor(col), 3); pen.setCapStyle(Qt.PenCapStyle.RoundCap); pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(line)
        p.restore()
        k = max(1, math.ceil(n / max(1, int(cw / 46))))
        p.setFont(_font(self.font(), 10)); p.setPen(muted)
        for i, lab in enumerate(self.labels):
            if i % k == 0:
                p.drawText(QRectF(xs[i] - 24, mt + ch + 8, 48, 18), ASC.AlignCenter, lab)
        if 0 <= self._hover < n:
            hx = xs[self._hover]
            p.setPen(QPen(qc(P['primary'], 0.5), 1, Qt.PenStyle.DashLine)); p.drawLine(int(hx), mt, int(hx), mt + ch)
            lines = []
            for name, vals, col in self.series:
                yy = mt + ch - ch * vals[self._hover] / top
                p.setPen(QPen(QColor(P['surface']), 2)); p.setBrush(QColor(col)); p.drawEllipse(QPointF(hx, yy), 5.5, 5.5)
                lines.append(f'{name}: {vals[self._hover]}')
            f = _font(self.font(), 12, QFont.Weight.DemiBold); fm = QFontMetrics(f)
            bw = max(fm.horizontalAdvance(s) for s in lines + [self.labels[self._hover]]) + 24; bh = 22 * (len(lines) + 1) + 10
            bx = max(2.0, min(self.width() - bw - 2, hx - bw / 2)); by = mt + 4
            bub = QRectF(bx, by, bw, bh)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(P['tooltip_bg'])); p.drawRoundedRect(bub, 10, 10)
            p.setPen(QColor(P['tooltip_fg'])); p.setFont(f)
            for j, s in enumerate([self.labels[self._hover]] + lines):
                p.drawText(QRectF(bx, by + 5 + j * 22, bw, 22), ASC.AlignCenter, s)


# =========================================================================== month calendar
class MonthGrid(QWidget):
    daySelected = Signal(object)
    dayActivated = Signal(object)
    HEAD = 34

    def __init__(self, parent=None):
        super().__init__(parent)
        t = date.today()
        self.year, self.month = t.year, t.month
        self.week_start, self.weekend = 6, (4, 5)
        self.by_date = {}
        self.selected, self.hover = t, None
        self.setMouseTracking(True)
        self.setMinimumHeight(520)
        theme.signals.changed.connect(self.update)

    def set_month(self, year, month, by_date, week_start, weekend):
        self.year, self.month, self.by_date, self.week_start, self.weekend = year, month, by_date, week_start, weekend
        self.update()

    def _cells(self):
        weeks = logic.month_weeks(self.year, self.month, self.week_start)
        rows = len(weeks)
        W, H = self.width(), self.height()
        cw, ch = W / 7, (H - self.HEAD) / rows
        out = []
        for r, wk in enumerate(weeks):
            for c, d in enumerate(wk):
                x = W - (c + 1) * cw if self.isRightToLeft() else c * cw
                out.append((d, QRectF(x + 3, self.HEAD + r * ch + 3, cw - 6, ch - 6)))
        return out

    def _hit(self, pos):
        for d, r in self._cells():
            if r.contains(pos):
                return d
        return None

    def mouseMoveEvent(self, e):
        d = self._hit(e.position())
        if d != self.hover:
            self.hover = d; self.update()

    def leaveEvent(self, e): self.hover = None; self.update(); super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        d = self._hit(e.position())
        if d:
            self.selected = d; self.update(); self.daySelected.emit(d)

    def mouseDoubleClickEvent(self, e):
        d = self._hit(e.position())
        if d:
            self.dayActivated.emit(d)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W = self.width(); cw = W / 7; rtl = self.isRightToLeft()
        p.setFont(_font(self.font(), 13, QFont.Weight.Bold))
        for c in range(7):
            wd = (self.week_start + c) % 7
            x = W - (c + 1) * cw if rtl else c * cw
            p.setPen(QColor(P['danger']) if wd in self.weekend else QColor(P['text_muted']))
            p.drawText(QRectF(x, 0, cw, self.HEAD), ASC.AlignCenter, logic.WEEKDAYS[wd])
        today = date.today(); now = datetime.now()
        for d, r in self._cells():
            in_month = d.month == self.month
            fill = QColor(P['surface']); fill.setAlphaF(1.0 if in_month else 0.45)
            if d.weekday() in self.weekend:
                fill = mix(fill, QColor(P['danger']), 0.05)
            if d == self.hover:
                fill = mix(fill, QColor(P['primary']), 0.10)
            p.setPen(QPen(QColor(P['primary']) if d == self.selected else qc(P['border'], 1.0), 2 if d == self.selected else 1))
            p.setBrush(fill); p.drawRoundedRect(r, 14, 14)
            # day number
            nr = QRectF(r.right() - 36 if rtl else r.left() + 8, r.top() + 7, 28, 28)
            if d == today:
                g = QLinearGradient(nr.topLeft(), nr.bottomRight()); g.setColorAt(0, QColor(P['primary'])); g.setColorAt(1, QColor(P['accent']))
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(g)); p.drawEllipse(nr)
                p.setPen(QColor('#FFFFFF'))
            else:
                p.setPen(QColor(P['text'] if in_month else P['text_faint']))
            p.setFont(_font(self.font(), 13, QFont.Weight.Bold)); p.drawText(nr, ASC.AlignCenter, str(d.day))
            tasks = self.by_date.get(d.isoformat(), [])
            if not tasks:
                continue
            fit = max(1, int((r.height() - 46) / 20))
            shown = tasks if len(tasks) <= fit else tasks[:max(1, fit - 1)]
            y = r.top() + 40
            p.setFont(_font(self.font(), 11, QFont.Weight.DemiBold))
            for t in shown:
                st = logic.task_state(t, now)
                key = 'late' if st == 'late' else STATUS_KEYS.get(t['status'], 'scheduled')
                fg, bg, _dot = theme.status_colors(key)
                chip = QRectF(r.left() + 6, y, r.width() - 12, 17)
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(bg); p.drawRoundedRect(chip, 6, 6)
                p.setPen(fg)
                txt = f"{t['start_time']} {t['title']}"
                p.drawText(chip.adjusted(6, 0, -6, 0), (ASC.AlignRight if rtl else ASC.AlignLeft) | ASC.AlignVCenter,
                           QFontMetrics(p.font()).elidedText(txt, Qt.TextElideMode.ElideRight, int(chip.width() - 12)))
                y += 20
            if len(tasks) > len(shown):
                p.setPen(QColor(P['primary_dark'])); p.setFont(_font(self.font(), 11, QFont.Weight.Bold))
                p.drawText(QRectF(r.left() + 6, y, r.width() - 12, 17), (ASC.AlignRight if rtl else ASC.AlignLeft) | ASC.AlignVCenter, f'+{len(tasks) - len(shown)} أخرى')


# =========================================================================== kanban
class KanbanDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(220, 124)

    def paint(self, p, option, index):
        t = index.data(ROLE_TASK)
        if not t:
            return
        p.save(); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rtl = option.direction == Qt.LayoutDirection.RightToLeft
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver); selected = bool(option.state & QStyle.StateFlag.State_Selected)
        r = QRectF(option.rect).adjusted(5, 5, -5, -5)
        paint_shadow(p, r, 14, qc(P['shadow'], P['shadow_alpha'] * (1.5 if hovered else 0.9)), spread=6, dy=2 + (2 if hovered else 0))
        path = QPainterPath(); path.addRoundedRect(r, 14, 14)
        p.fillPath(path, QColor(P['surface']))
        p.setPen(QPen(QColor(P['primary']) if (hovered or selected) else QColor(P['border']), 1.5 if (hovered or selected) else 1)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(path)
        c1, c2 = theme.priority_colors(t['priority'])
        bar = QRectF(r.right() - 6 if rtl else r.left() + 2, r.top() + 12, 4, r.height() - 24)
        g = QLinearGradient(bar.topLeft(), bar.bottomLeft()); g.setColorAt(0, c1); g.setColorAt(1, c2)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(g)); p.drawRoundedRect(bar, 2, 2)
        inner = r.adjusted(16 if not rtl else 12, 10, -12 if not rtl else -16, -10)
        al = (ASC.AlignRight if rtl else ASC.AlignLeft) | ASC.AlignVCenter

        def lx(off, w):
            return inner.right() - off - w if rtl else inner.left() + off
        state = logic.task_state(t)
        f = _font(option.font, 14, QFont.Weight.DemiBold); f.setStrikeOut(state in ('done', 'cancel')); p.setFont(f)
        p.setPen(QColor(P['text_muted'] if state in ('done', 'cancel') else P['text']))
        p.drawText(QRectF(inner.left(), inner.top(), inner.width(), 22), al, QFontMetrics(f).elidedText(t['title'], Qt.TextElideMode.ElideRight, int(inner.width())))
        # person
        a1, a2 = theme.avatar_gradient(t['person_name'])
        av = QRectF(lx(0, 22), inner.top() + 28, 22, 22)
        g2 = QLinearGradient(av.topLeft(), av.bottomRight()); g2.setColorAt(0, a1); g2.setColorAt(1, a2)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(g2)); p.drawEllipse(av)
        p.setPen(QColor('#FFFFFF')); p.setFont(_font(option.font, 12, QFont.Weight.Bold)); p.drawText(av, ASC.AlignCenter, (t['person_name'].strip()[:1] or '?'))
        p.setPen(QColor(P['text_muted'])); p.setFont(_font(option.font, 12, QFont.Weight.Medium))
        p.drawText(QRectF(lx(30, inner.width() - 30), inner.top() + 28, inner.width() - 30, 22), al, t['person_name'])
        # when
        draw_icon(p, 'clock', QRectF(lx(0, 16), inner.top() + 56, 16, 16), P['text_faint'], 2.0)
        p.setPen(QColor(P['text_muted'])); p.setFont(_font(option.font, 12))
        p.drawText(QRectF(lx(24, inner.width() - 24), inner.top() + 54, inner.width() - 24, 20), al, ltr(f"{t['task_date']}   {t['start_time']} – {t['end_time']}"))
        # chips
        y = inner.top() + 80
        off = 0
        chips = [(f"أولوية {t['priority']}", c2, 0.16)]
        if t.get('category'):
            chips.append((t['category'], QColor(P['primary']), 0.14))
        done, total = t.get('sub', (0, 0))
        if total:
            chips.append((f'{done}/{total} ✓', QColor('#10B981'), 0.16))
        if state == 'late':
            chips.append(('متأخرة', QColor(P['danger']), 0.16))
        p.setFont(_font(option.font, 11, QFont.Weight.Bold))
        fm = QFontMetrics(p.font())
        for text, col, a in chips:
            w = fm.horizontalAdvance(text) + 18
            if off + w > inner.width():
                break
            cr = QRectF(lx(off, w), y, w, 20)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(qc(col, a)); p.drawRoundedRect(cr, 10, 10)
            p.setPen(QColor(col).darker(115) if P['name'] == 'light' else QColor(col).lighter(120)); p.drawText(cr, ASC.AlignCenter, text)
            off += w + 6
        p.restore()


class KanbanList(QListWidget):
    dropped = Signal(int, str)

    def __init__(self, status, parent=None):
        super().__init__(parent)
        self.status = status
        self.setItemDelegate(KanbanDelegate(self))
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)

    def dropEvent(self, e):
        src = e.source()
        if isinstance(src, KanbanList) and src is not self and src.currentItem() is not None:
            self.dropped.emit(int(src.currentItem().data(ROLE_ID)), self.status)
        e.setDropAction(Qt.DropAction.IgnoreAction)   # the page rebuilds the columns itself
        e.accept()


class KanbanPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        top = Card(padding=8); bar = QHBoxLayout(); bar.setSpacing(10)
        self.person = Combo(); self.person.addItem('كل الأفراد', None)
        hint = QLabel('اسحب البطاقة إلى عمود آخر لتغيير حالتها • انقر نقرًا مزدوجًا للتعديل'); hint.setObjectName('muted')
        new = Btn('مهمة جديدة', 'primary', 'plus'); new.clicked.connect(lambda: win.new_task())
        bar.addWidget(self.person); bar.addWidget(hint); bar.addStretch(); bar.addWidget(new); top.body.addLayout(bar); lay.addWidget(top)
        cols = QHBoxLayout(); cols.setSpacing(0); self.lists, self.counts = {}, {}
        for status in logic.STATUSES:
            card = Card(padding=10); head = QHBoxLayout(); head.setSpacing(8)
            fg, bg, dot = theme.status_colors(STATUS_KEYS[status])
            head.addWidget(Dot(dot, 12)); head.addWidget(title_label(status)); head.addStretch()
            cnt = QLabel('0'); cnt.setObjectName('chip'); head.addWidget(cnt); card.body.addLayout(head)
            lst = KanbanList(status); lst.dropped.connect(self.on_drop); lst.itemDoubleClicked.connect(lambda it: win.edit_task_id(it.data(ROLE_ID)))
            card.body.addWidget(lst, 1); cols.addWidget(card, 1); self.lists[status] = lst; self.counts[status] = cnt
        lay.addLayout(cols, 1)
        self.person.currentIndexChanged.connect(self.refresh)

    def on_drop(self, tid, status):
        QTimer.singleShot(0, lambda: self.win.set_status(tid, status))

    def refresh(self, *_):
        db = self.win.db
        cur = self.person.currentData()
        self.person.blockSignals(True); self.person.clear(); self.person.addItem('كل الأفراد', None)
        for pr in db.people(active_only=True): self.person.addItem(pr['name'], pr['id'])
        self.person.setCurrentIndex(max(0, self.person.findData(cur))); self.person.blockSignals(False)
        pid = self.person.currentData(); subs = db.subtask_counts()
        tasks = [t for t in db.tasks(search=self.win.search.text()) if pid is None or t['person_id'] == pid]
        for status, lst in self.lists.items():
            lst.clear(); n = 0
            for t in sorted((x for x in tasks if x['status'] == status), key=lambda x: (-x['priority'], x['task_date'], x['start_time'])):
                d = dict(t); d['sub'] = subs.get(t['id'], (0, 0))
                it = QListWidgetItem(); it.setData(ROLE_ID, t['id']); it.setData(ROLE_TASK, d); it.setSizeHint(QSize(220, 124)); lst.addItem(it); n += 1
            self.counts[status].setText(str(n))


# =========================================================================== calendar page
class CalendarPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.cur = date.today().replace(day=1)
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        top = Card(padding=8); bar = QHBoxLayout(); bar.setSpacing(8)
        prev = Btn('', 'soft', 'chevron_right'); prev.clicked.connect(lambda: self.shift(-1))
        nxt = Btn('', 'soft', 'chevron_left'); nxt.clicked.connect(lambda: self.shift(1))
        today = Btn('اليوم', 'soft', 'calendar'); today.clicked.connect(self.go_today)
        self.title = QLabel(''); self.title.setObjectName('cardTitle'); self.title.setStyleSheet('font-size:20px;font-weight:800;')
        bar.addWidget(prev); bar.addWidget(self.title); bar.addWidget(nxt); bar.addStretch(); bar.addWidget(today)
        top.body.addLayout(bar); lay.addWidget(top)
        row = QHBoxLayout(); row.setSpacing(0)
        gc = Card(padding=10); self.grid = MonthGrid(); self.grid.daySelected.connect(self.show_day); self.grid.dayActivated.connect(lambda d: win.new_task(d))
        gc.body.addWidget(self.grid); row.addWidget(gc, 3)
        dc = Card(); self.day_title = title_label(''); dc.body.addWidget(self.day_title)
        self.day_table = HoverTable(0, 3); self.day_table.setHorizontalHeaderLabels(['الوقت', 'المهمة', 'الحالة'])
        self.day_table.setItemDelegate(TaskDelegate(self.day_table, {0: 'muted', 1: 'title', 2: 'pill'})); self.day_table.set_empty_text('لا توجد مهام في هذا اليوم')
        self.day_table.cellDoubleClicked.connect(lambda r, c: self.edit_row(r)); dc.body.addWidget(self.day_table, 1)
        add = Btn('إضافة مهمة لهذا اليوم', 'primary', 'plus'); add.clicked.connect(lambda: win.new_task(self.grid.selected)); dc.body.addWidget(add)
        row.addWidget(dc, 1); lay.addLayout(row, 1)

    def shift(self, n):
        self.cur = logic.add_months(self.cur, n).replace(day=1); self.refresh()

    def go_today(self):
        self.cur = date.today().replace(day=1); self.grid.selected = date.today(); self.refresh()

    def edit_row(self, r):
        it = self.day_table.item(r, 0)
        if it: self.win.edit_task_id(it.data(ROLE_ID))

    def refresh(self, *_):
        cfg = self.win.cfg; ws = cfg.get('week_start'); weekend = logic.WEEKEND_PRESETS.get(cfg.get('weekend'), (4, 5))
        weeks = logic.month_weeks(self.cur.year, self.cur.month, ws)
        tasks = self.win.db.report_tasks(weeks[0][0].isoformat(), weeks[-1][-1].isoformat())
        by = {}
        for t in tasks: by.setdefault(t['task_date'], []).append(t)
        for v in by.values(): v.sort(key=lambda x: x['start_time'])
        self.title.setText(f'{logic.MONTHS[self.cur.month - 1]} {self.cur.year}')
        self.grid.set_month(self.cur.year, self.cur.month, by, ws, weekend); self.show_day(self.grid.selected)

    def show_day(self, d):
        self.day_title.setText(f'{logic.WEEKDAYS[d.weekday()]}  {d.day} {logic.MONTHS[d.month - 1]}')
        now = datetime.now(); entries = []
        for t in self.win.db.day_tasks(d.isoformat()):
            entries.append(dict(id=t['id'], state=logic.task_state(t, now), prio=t['priority'],
                                cells=[(ltr(f"{t['start_time']}–{t['end_time']}"), None), (t['title'], None), (t['status'], STATUS_KEYS.get(t['status']))]))
        put_rows(self.day_table, entries, {0: 120, 1: 150})


# =========================================================================== dashboard
class DashboardPage(QScrollArea):
    def __init__(self, win):
        super().__init__()
        self.win = win
        page = QWidget(); lay = QVBoxLayout(page); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        kp = QHBoxLayout(); kp.setSpacing(0)
        self.k_today = GradCard('مهام اليوم', 'tasks', '#6366F1', '#8B5CF6'); self.k_late = GradCard('مهام متأخرة', 'alert', '#F43F5E', '#FB923C')
        self.k_week = GradCard('أُنجزت هذا الأسبوع', 'check_circle', '#10B981', '#14B8A6'); self.k_rate = GradCard('نسبة الإنجاز (30 يومًا)', 'chart', '#0EA5E9', '#06B6D4', suffix='%')
        for k in (self.k_today, self.k_late, self.k_week, self.k_rate): kp.addWidget(k)
        lay.addLayout(kp)
        r2 = QHBoxLayout(); r2.setSpacing(0)
        ac = Card(); head = QHBoxLayout(); head.addWidget(title_label('جدول اليوم')); head.addStretch()
        sm = Btn('نسخ ملخص اليوم', 'success', 'copy'); sm.clicked.connect(win.copy_day_summary); head.addWidget(sm)
        nw = Btn('مهمة جديدة', 'primary', 'plus'); nw.clicked.connect(lambda: win.new_task()); head.addWidget(nw); ac.body.addLayout(head)
        self.agenda = HoverTable(0, 4); self.agenda.setHorizontalHeaderLabels(['الوقت', 'المهمة', 'المسؤول', 'الحالة'])
        self.agenda.setItemDelegate(TaskDelegate(self.agenda, {0: 'muted', 1: 'title', 2: 'person', 3: 'pill'})); self.agenda.set_empty_text('لا توجد مهام لهذا اليوم - يوم هادئ 🎉')
        self.agenda.setMinimumHeight(300); self.agenda.cellDoubleClicked.connect(lambda r, c: self._edit(self.agenda, r)); ac.body.addWidget(self.agenda, 1); r2.addWidget(ac, 3)
        wc = Card(); wc.body.addWidget(title_label('عبء العمل لكل فرد')); self.workload = WorkloadChart(); wc.body.addWidget(self.workload, 1); r2.addWidget(wc, 2)
        lay.addLayout(r2)
        r3 = QHBoxLayout(); r3.setSpacing(0)
        tc = Card(); tc.body.addWidget(title_label('الإنجاز مقابل المستحق - آخر 14 يومًا')); self.trend = TrendChart(); tc.body.addWidget(self.trend, 1); r3.addWidget(tc, 3)
        uc = Card(); uc.body.addWidget(title_label('قادمة خلال 7 أيام'))
        self.upcoming = HoverTable(0, 4); self.upcoming.setHorizontalHeaderLabels(['التاريخ', 'المهمة', 'المسؤول', 'الأولوية'])
        self.upcoming.setItemDelegate(TaskDelegate(self.upcoming, {0: 'text', 1: 'title', 2: 'person', 3: 'priority'})); self.upcoming.set_empty_text('لا شيء قادم خلال الأسبوع')
        self.upcoming.setMinimumHeight(240); self.upcoming.cellDoubleClicked.connect(lambda r, c: self._edit(self.upcoming, r)); uc.body.addWidget(self.upcoming, 1); r3.addWidget(uc, 2)
        lay.addLayout(r3)
        self.setWidgetResizable(True); self.setFrameShape(QFrame.Shape.NoFrame); self.setWidget(page); page.setAutoFillBackground(False)
        self.viewport().setAutoFillBackground(False); self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def _edit(self, table, r):
        it = table.item(r, 0)
        if it: self.win.edit_task_id(it.data(ROLE_ID))

    def replay(self):
        for k in (self.k_today, self.k_late, self.k_week, self.k_rate): k.replay()
        self.workload.replay(); self.trend.replay()

    def refresh(self, *_):
        db, cfg = self.win.db, self.win.cfg
        today = date.today(); now = datetime.now()
        todays = [t for t in db.day_tasks(today.isoformat()) if t['status'] != 'ملغاة']
        win_tasks = db.report_tasks((today - timedelta(days=30)).isoformat(), (today + timedelta(days=30)).isoformat())
        alltasks = db.tasks()
        late = [t for t in alltasks if logic.task_state(t, now) == 'late']
        days_in_week = (today - logic.week_start_of(today, cfg.get('week_start'))).days + 1
        week_done = sum(c for _d, c in db.completed_per_day(days_in_week, today))
        last30 = [t for t in db.report_tasks((today - timedelta(days=30)).isoformat(), today.isoformat()) if t['status'] != 'ملغاة']
        self.k_today.set_value(len(todays)); self.k_late.set_value(len(late)); self.k_week.set_value(week_done)
        self.k_rate.set_value(logic.percent(sum(1 for t in last30 if t['status'] == 'منجزة'), len(last30)))
        entries = []
        for t in todays:
            entries.append(dict(id=t['id'], state=logic.task_state(t, now), prio=t['priority'], cells=[(ltr(f"{t['start_time']}–{t['end_time']}"), None), (t['title'], None), (t['person_name'], None), (t['status'], STATUS_KEYS.get(t['status']))]))
        put_rows(self.agenda, entries, {0: 130, 1: 200, 2: 150})
        up = [t for t in db.report_tasks((today + timedelta(days=1)).isoformat(), (today + timedelta(days=7)).isoformat()) if t['status'] not in ('منجزة', 'ملغاة')]
        up.sort(key=lambda t: (t['task_date'], t['start_time']))
        put_rows(self.upcoming, [dict(id=t['id'], state=logic.task_state(t, now), prio=t['priority'], cells=[(t['task_date'][5:], None), (t['title'], None), (t['person_name'], None), (f"{t['priority']}/10", None)]) for t in up], {1: 160, 2: 140})
        stats = {}
        for t in win_tasks:
            if t['status'] == 'ملغاة':
                continue
            s = stats.setdefault(t['person_name'], [0, 0, 0]); st = logic.task_state(t, now)
            s[0 if st == 'done' else (2 if st == 'late' else 1)] += 1
        self.workload.set_data(sorted(([n, *v] for n, v in stats.items()), key=lambda r: -sum(r[1:])))
        comp, due = db.completed_per_day(14, today), db.due_per_day(14, today)
        self.trend.set_data([d.strftime('%d/%m') for d, _ in comp], [('أُنجزت', [c for _, c in comp], '#10B981'), ('مستحقة', [c for _, c in due], P['primary'])])


# =========================================================================== activity
class ActivityPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0)
        card = Card(); head = QHBoxLayout(); head.addWidget(title_label('سجل النشاط')); head.addStretch()
        self.count = QLabel('0'); self.count.setObjectName('chip'); head.addWidget(self.count); card.body.addLayout(head)
        self.table = HoverTable(0, 3); self.table.setHorizontalHeaderLabels(['الإجراء', 'المهمة', 'الوقت'])
        self.table.setItemDelegate(TaskDelegate(self.table, {0: 'pill', 1: 'title', 2: 'muted'})); self.table.set_empty_text('لا يوجد نشاط بعد')
        card.body.addWidget(self.table, 1); lay.addWidget(card, 1)

    def refresh(self, *_):
        now = datetime.now(); rows = self.win.db.activity(300)
        put_rows(self.table, [dict(id=r['task_id'], cells=[(r['action'], logic.ACTION_PILLS.get(r['action'], 'scheduled')), (r['detail'] or '—', None), (logic.human_ago(logic.utc_to_local(r['changed_at']), now), None)]) for r in rows], {0: 130, 1: 340})
        self.count.setText(f'{len(rows)} حدث')


# =========================================================================== settings
class SettingsPage(QWidget):
    changed = Signal(str)

    def __init__(self, win):
        super().__init__()
        self.win = win; cfg = win.cfg
        inner = QWidget(); lay = QVBoxLayout(inner); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        # appearance
        c1 = Card(); c1.body.addWidget(title_label('المظهر'))
        row = QHBoxLayout(); row.setSpacing(6)
        self.mode_btn = Btn('', 'soft', 'moon'); self.mode_btn.clicked.connect(win.toggle_theme); row.addWidget(self.mode_btn); row.addSpacing(18)
        self.swatches = []
        for name in theme.ACCENTS:
            sw = AccentSwatch(name); sw.clicked.connect(self.pick_accent); row.addWidget(sw); self.swatches.append(sw)
        row.addStretch(); c1.body.addLayout(row); lay.addWidget(c1)
        # schedule
        c2 = Card(); c2.body.addWidget(title_label('الجدول وساعات العمل'))
        form = QHBoxLayout(); form.setSpacing(10)
        self.week_start = Combo()
        for k, v in logic.WEEK_START_LABELS.items(): self.week_start.addItem(v, k)
        self.week_start.setCurrentIndex(max(0, self.week_start.findData(cfg.get('week_start'))))
        self.weekend = Combo()
        for k, v in logic.WEEKEND_LABELS.items(): self.weekend.addItem(v, k)
        self.weekend.setCurrentIndex(max(0, self.weekend.findData(cfg.get('weekend'))))
        self.day_start, self.day_end, self.default_rem = QSpinBox(), QSpinBox(), QSpinBox()
        for s, lo, hi, val, suf in ((self.day_start, 0, 22, cfg.get('day_start'), ' : 00'), (self.day_end, 1, 24, cfg.get('day_end'), ' : 00'), (self.default_rem, 0, 1440, cfg.get('default_reminder'), ' د')):
            s.setRange(lo, hi); s.setValue(val); s.setSuffix(suf); s.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        for label, w in (('بداية الأسبوع', self.week_start), ('أيام العطلة', self.weekend), ('بداية يوم العمل', self.day_start), ('نهاية يوم العمل', self.day_end), ('التذكير الافتراضي', self.default_rem)):
            col = QVBoxLayout(); col.setSpacing(4); l = QLabel(label); l.setObjectName('fieldLabel'); col.addWidget(l); col.addWidget(w); form.addLayout(col)
        form.addStretch(); c2.body.addLayout(form); lay.addWidget(c2)
        self.week_start.currentIndexChanged.connect(lambda: self.save('week_start', self.week_start.currentData()))
        self.weekend.currentIndexChanged.connect(lambda: self.save('weekend', self.weekend.currentData()))
        self.day_start.valueChanged.connect(lambda v: self.save('day_start', v)); self.day_end.valueChanged.connect(lambda v: self.save('day_end', v))
        self.default_rem.valueChanged.connect(lambda v: self.save('default_reminder', v))
        # data
        c3 = Card(); c3.body.addWidget(title_label('البيانات والنسخ الاحتياطي'))
        self.path_label = QLabel(f'قاعدة البيانات: {win.db.path}'); self.path_label.setObjectName('muted'); self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        c3.body.addWidget(self.path_label)
        br = QHBoxLayout(); br.setSpacing(4)
        for text, variant, icon, fn in (('نسخ احتياطي الآن', 'primary', 'download', win.backup_now), ('استعادة من نسخة', 'soft', 'restore', win.restore_backup),
                                        ('فتح مجلد البيانات', 'soft', 'archive', win.open_data_folder), ('تصدير كل المهام CSV', 'soft', 'sheet', win.export_all_csv)):
            b = Btn(text, variant, icon); b.clicked.connect(fn); br.addWidget(b)
        br.addStretch(); c3.body.addLayout(br)
        self.auto = QCheckBox('نسخ احتياطي تلقائي عند إغلاق البرنامج (يحتفظ بآخر 7 نسخ)'); self.auto.setChecked(cfg.get('auto_backup'))
        self.auto.toggled.connect(lambda v: self.save('auto_backup', v)); c3.body.addWidget(self.auto); lay.addWidget(c3)
        # shortcuts
        c4 = Card(); c4.body.addWidget(title_label('اختصارات لوحة المفاتيح'))
        sc = QLabel('Ctrl+K  لوحة الأوامر     •     Ctrl+N  مهمة جديدة     •     Ctrl+F  بحث     •     F5  تحديث\n'
                    'Ctrl+D  تبديل المظهر     •     Ctrl+1 … Ctrl+9  التنقل بين الصفحات'); sc.setObjectName('muted')
        sc.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); c4.body.addWidget(sc); lay.addWidget(c4); lay.addStretch()
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.addWidget(page_scroll(inner))
        theme.signals.changed.connect(self.sync_mode_icon); self.sync_mode_icon()

    def sync_mode_icon(self):
        dark = theme.mode() == 'dark'
        self.mode_btn.icon_kind = 'sun' if dark else 'moon'; self.mode_btn.setText('التبديل إلى المظهر الفاتح' if dark else 'التبديل إلى المظهر الداكن'); self.mode_btn.updateGeometry(); self.mode_btn.update()

    def pick_accent(self, name):
        self.win.cfg.set('accent', name); theme.apply(self.win.app(), theme.mode(), name); self.changed.emit('accent')

    def save(self, key, value):
        self.win.cfg.set(key, value); self.changed.emit(key)
