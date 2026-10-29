import sys, os, sqlite3, subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QDate, QTime, QUrl
from PySide6.QtGui import QAction, QIcon, QShortcut, QKeySequence, QDesktopServices
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QTextEdit,
    QLabel, QTableWidgetItem, QFileDialog, QSystemTrayIcon, QMenu, QFrame, QScrollArea, QProgressBar, QSpinBox, QCheckBox)
from database import Database
from exports import export_pdf, export_docx, export_xlsx, export_csv
from config import Config
import logic
import theme
from theme import STATUS_KEYS
from widgets import (Backdrop, Card, Btn, Combo, FocusGlow, SearchGrow, HeaderBanner, LogoBadge, PillNav, FadeStack, TimeBox, DateBox,
    GradCard, PlanningChart, DonutChart, HoverTable, TaskDelegate, Toast, FancyDialog, PriorityEdit, ChecklistEditor, CommandPalette,
    ROLE_ID, ROLE_STATE, ROLE_PRIO, ROLE_PILL, info, warn, error, ask, ask_choice)
from views import DashboardPage, KanbanPage, CalendarPage, ActivityPage, SettingsPage, ltr, page_scroll

APP_NAME = 'منظّم الفريق'
STATUSES = logic.STATUSES
REMAINING_KEYS = {'منجزة': 'done', 'متأخرة': 'late', 'ملغاة': 'cancel', 'ضمن الوقت': 'ontime'}
DEFAULT_CATEGORIES = ['عام', 'اجتماع', 'متابعة', 'تقرير', 'ميداني', 'إداري']
TABS = [('الرئيسية', 'home'), ('المهام', 'tasks'), ('اللوحة', 'board'), ('التقويم', 'calendar'), ('التخطيط', 'chart'),
        ('الأرشيف', 'archive'), ('التقارير', 'file'), ('النشاط', 'pulse'), ('الإعدادات', 'sliders')]


def app_data_dir():
    root = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'MounazzemAlFariq'
    root.mkdir(parents=True, exist_ok=True)
    return root


def field_label(text):
    lbl = QLabel(text); lbl.setObjectName('fieldLabel'); return lbl


def to_qdate(d):
    return QDate(d.year, d.month, d.day) if isinstance(d, date) else d


# =========================================================================== dialogs
class TaskDialog(FancyDialog):
    def __init__(self, db, task=None, cfg=None, parent=None, day=None):
        super().__init__('تعديل مهمة' if task else 'مهمة جديدة',
                         'عدّل بيانات المهمة ثم احفظ' if task else 'أضف مهمة جديدة إلى جدول الفريق', 'edit' if task else 'plus', parent)
        self.db, self.task = db, task
        self.resize(660, 780); self.setMinimumWidth(560)
        self.title = QLineEdit(); self.title.setPlaceholderText('مثال: إعداد كشف مصاريف الورشة'); FocusGlow(self.title)
        self.person = Combo(); self.refresh_people()
        self.category = Combo(); self.category.setEditable(True)
        cats = ['']; cats += [c for c in DEFAULT_CATEGORIES + db.categories() if c not in cats]
        for c in dict.fromkeys(cats): self.category.addItem(c)
        self.category.lineEdit().setPlaceholderText('اختر فئة أو اكتب فئة جديدة'); self.category.setCurrentIndex(0)
        self.date = DateBox(to_qdate(day) if day else QDate.currentDate())
        self.start = TimeBox(QTime.currentTime()); self.end = TimeBox(QTime.currentTime().addSecs(3600))
        self.priority = PriorityEdit(); self.status = Combo(); self.status.addItems(STATUSES)
        self.details = QTextEdit(); self.details.setMaximumHeight(90)
        self.checklist = ChecklistEditor()
        self.remind = QSpinBox(); self.remind.setRange(0, 1440); self.remind.setValue(cfg.get('default_reminder') if cfg else 15); self.remind.setSuffix(' دقيقة قبل الموعد')
        self.repeat = Combo()
        for label, key in logic.REPEATS: self.repeat.addItem(label, key)
        self.repeat_end = DateBox(QDate.currentDate().addDays(30))
        inner = QWidget(); form = QFormLayout(inner); form.setSpacing(12); form.setHorizontalSpacing(18)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter); form.setContentsMargins(0, 0, 6, 0)
        times = QHBoxLayout(); times.setSpacing(10); times.addWidget(self.start); times.addWidget(QLabel('→')); times.addWidget(self.end); times.addStretch()
        form.addRow(field_label('عنوان المهمة'), self.title); form.addRow(field_label('المسؤول'), self.person); form.addRow(field_label('الفئة'), self.category)
        form.addRow(field_label('التاريخ'), self.date); form.addRow(field_label('الوقت (من → إلى)'), times); form.addRow(field_label('الأولوية'), self.priority)
        form.addRow(field_label('الحالة'), self.status); form.addRow(field_label('التفاصيل'), self.details); form.addRow(field_label('قائمة الخطوات'), self.checklist)
        form.addRow(field_label('التذكير'), self.remind); form.addRow(field_label('التكرار'), self.repeat); form.addRow(field_label('إنهاء التكرار بتاريخ'), self.repeat_end)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame); scroll.setWidget(inner)
        inner.setAutoFillBackground(False); scroll.viewport().setAutoFillBackground(False); self.cl.addWidget(scroll, 1)
        row = QHBoxLayout(); row.setSpacing(10)
        save = Btn('حفظ', 'primary', 'check'); save.setDefault(True); save.clicked.connect(self.accept)
        cancel = Btn('إلغاء', 'soft'); cancel.clicked.connect(self.reject)
        row.addWidget(save); row.addWidget(cancel); row.addStretch(); self.cl.addLayout(row)
        if task:
            self.title.setText(task['title']); self.person.setCurrentIndex(max(0, self.person.findData(task['person_id'])))
            self.category.setCurrentText(task['category'] or '')
            self.date.setDate(QDate.fromString(task['task_date'], 'yyyy-MM-dd')); self.start.setTime(QTime.fromString(task['start_time'], 'HH:mm')); self.end.setTime(QTime.fromString(task['end_time'], 'HH:mm'))
            self.priority.setValue(task['priority']); self.status.setCurrentText(task['status']); self.details.setPlainText(task['details'] or '')
            self.remind.setValue(task['reminder_minutes']); self.checklist.set_items([(s['title'], bool(s['done'])) for s in db.subtasks(task['id'])])
            self.repeat.setEnabled(False); self.repeat_end.setEnabled(False)
    def refresh_people(self):
        for p in self.db.people(active_only=True): self.person.addItem(p['name'], p['id'])
    def payload(self):
        return dict(title=self.title.text().strip(), person_id=self.person.currentData(), task_date=self.date.date().toString('yyyy-MM-dd'),
                    start_time=self.start.time().toString('HH:mm'), end_time=self.end.time().toString('HH:mm'), priority=self.priority.value(),
                    status=self.status.currentText(), details=self.details.toPlainText().strip(), reminder_minutes=self.remind.value(),
                    category=self.category.currentText().strip(), subtasks=self.checklist.items(),
                    repeat=self.repeat.currentData(), repeat_end=self.repeat_end.date().toString('yyyy-MM-dd'))
    def split_payload(self):
        d = self.payload(); subs = d.pop('subtasks'); repeat = d.pop('repeat'); end = d.pop('repeat_end'); return d, subs, repeat, end
    def accept(self):
        d = self.payload()
        if not d['title']: warn(self, 'بيانات ناقصة', 'يرجى إدخال عنوان المهمة.'); return
        if not d['person_id']: warn(self, 'لا يوجد أفراد', 'أضف فردًا واحدًا على الأقل أولًا.'); return
        if d['end_time'] <= d['start_time']: warn(self, 'وقت غير صحيح', 'وقت النهاية يجب أن يكون بعد وقت البداية في اليوم نفسه.'); return
        if d['status'] not in ('منجزة', 'ملغاة'):
            clash = self.db.conflicts(d['person_id'], d['task_date'], d['start_time'], d['end_time'], self.task['id'] if self.task else None)
            if clash:
                names = '\n'.join(f"• {c['title']}  ({c['start_time']}–{c['end_time']})" for c in clash)
                if not ask(self, 'تعارض في المواعيد', f"لدى {self.person.currentText()} مهام متداخلة مع هذا الوقت:\n{names}\n\nهل تريد المتابعة رغم ذلك؟", yes='متابعة', no='رجوع'): return
        super().accept()


class StatusDialog(FancyDialog):
    """One-click status picker."""
    def __init__(self, current, parent=None):
        super().__init__('حالة المهمة', 'اختر الحالة الجديدة بنقرة واحدة', 'check_circle', parent)
        self.setMinimumWidth(400); self.choice = None
        for s in STATUSES:
            fg, bg, dot = theme.status_colors(STATUS_KEYS[s])
            b = Btn(s, 'primary' if s == current else 'soft', 'check' if s == current else None)
            if s != current: b.dot = dot
            b.setMinimumHeight(52); b.clicked.connect(lambda _=False, s=s: self.pick(s)); self.cl.addWidget(b)
    def pick(self, status): self.choice = status; self.accept()


class PeopleDialog(FancyDialog):
    def __init__(self, db, parent=None):
        super().__init__('إدارة أفراد الفريق', 'حتى 10 أفراد نشطين', 'users', parent)
        self.db = db; self.resize(560, 580)
        self.table = HoverTable(0, 2); self.table.setHorizontalHeaderLabels(['الاسم', 'الحالة'])
        self.table.setItemDelegate(TaskDelegate(self.table, {0: 'person', 1: 'pill'})); self.table.set_empty_text('لا يوجد أفراد بعد - أضف أول فرد')
        self.table.setMinimumHeight(250); self.cl.addWidget(self.table, 1)
        self.meter = QProgressBar(); self.meter.setRange(0, 10); self.meter.setTextVisible(False)
        self.meter_label = QLabel(); self.meter_label.setObjectName('muted')
        self.cl.addWidget(self.meter_label); self.cl.addWidget(self.meter)
        row = QHBoxLayout(); row.setSpacing(10)
        self.name = QLineEdit(); self.name.setPlaceholderText('اسم الفرد'); FocusGlow(self.name); self.name.returnPressed.connect(self.add_person)
        add = Btn('إضافة', 'primary', 'plus'); add.clicked.connect(self.add_person)
        toggle = Btn('تفعيل / تعطيل المحدد', 'soft', 'users'); toggle.clicked.connect(self.toggle_active)
        row.addWidget(self.name, 1); row.addWidget(add); row.addWidget(toggle); self.cl.addLayout(row); self.reload()
    def reload(self):
        self.table.setRowCount(0); active = 0
        for p in self.db.people():
            r = self.table.rowCount(); self.table.insertRow(r)
            state, pill = ('scheduled', 'done') if p['active'] else ('cancel', 'cancel')
            active += 1 if p['active'] else 0
            for c, text in enumerate([p['name'], 'نشط' if p['active'] else 'معطّل']):
                it = QTableWidgetItem(text); it.setData(ROLE_STATE, state); it.setData(ROLE_PILL, pill)
                if c == 0: it.setData(ROLE_ID, p['id'])
                self.table.setItem(r, c, it)
        self.table.fit_columns({0: 240}); self.meter.setValue(min(10, active)); self.meter_label.setText(f'الأفراد النشطون: {active} / 10')
    def add_person(self):
        name = self.name.text().strip()
        if not name: return
        if len(self.db.people(active_only=True)) >= 10: warn(self, 'حد الفريق', 'الحد الأقصى 10 أفراد.'); return
        try: self.db.add_person(name); self.name.clear(); self.reload()
        except sqlite3.IntegrityError: warn(self, 'اسم مكرر', 'هذا الاسم موجود بالفعل.')
    def toggle_active(self):
        r = self.table.currentRow()
        if r < 0 or not self.table.item(r, 0): return
        pid = self.table.item(r, 0).data(ROLE_ID); person = next((p for p in self.db.people() if p['id'] == pid), None)
        if person is None: return
        if person['active']:
            if ask(self, 'تأكيد', 'تعطيل هذا الفرد؟ ستبقى مهامه القديمة محفوظة.', yes='تعطيل', danger=True): self.db.deactivate_person(pid)
        else:
            if len(self.db.people(active_only=True)) >= 10: warn(self, 'حد الفريق', 'الحد الأقصى 10 أفراد نشطين.'); return
            self.db.reactivate_person(pid)
        self.reload()


# =========================================================================== main window
class MainWindow(QMainWindow):
    TASK_COLS = ['المهمة', 'المسؤول', 'الفئة', 'التاريخ', 'البداية', 'النهاية', 'الأولوية', 'الخطوات', 'الحالة', 'التذكير']
    TASK_KINDS = {0: 'title', 1: 'person', 2: 'chip', 3: 'text', 4: 'muted', 5: 'muted', 6: 'priority', 7: 'progress', 8: 'pill', 9: 'muted'}

    def __init__(self):
        super().__init__(); self.setWindowTitle(APP_NAME); self.setMinimumSize(860, 520); self._initial_size()
        self.cfg = Config(); self.db = Database(app_data_dir() / 'team_tasks.sqlite3'); self.tray = None
        self.setup_ui(); self.setup_tray(); self.setup_shortcuts(); self.refresh()
        self.timer = QTimer(self); self.timer.timeout.connect(self.check_reminders); self.timer.start(30000)

    def app(self): return QApplication.instance()

    def _initial_size(self):
        """Never open larger than the screen; the layout adapts (compact header, scrollable pages) when it is small."""
        scr = QApplication.primaryScreen()
        if scr is None: self.resize(1360, 860); return
        g = scr.availableGeometry(); self.resize(min(1360, g.width() - 20), min(860, g.height() - 40))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, 'header'): self.header.set_compact(self.height() < 820)

    # ---------------------------------------------------------------- UI construction
    def make_table(self, cols, kinds, empty_text):
        t = HoverTable(0, len(cols)); t.setHorizontalHeaderLabels(cols); t.setItemDelegate(TaskDelegate(t, kinds)); t.set_empty_text(empty_text); return t

    def setup_ui(self):
        central = Backdrop(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(14, 6, 14, 4); root.setSpacing(0)
        self.header = HeaderBanner(); hl = self.header.lay
        hl.addWidget(LogoBadge())
        col = QVBoxLayout(); col.setSpacing(2); col.addStretch()
        title = QLabel(APP_NAME); title.setObjectName('heroTitle'); self.hero_sub = QLabel(logic.greeting_text()); self.hero_sub.setObjectName('heroSub')
        col.addWidget(title); col.addWidget(self.hero_sub); col.addStretch(); hl.addLayout(col); hl.addStretch()
        self.search = QLineEdit(); self.search.setObjectName('heroSearch'); self.search.setPlaceholderText('ابحث في العنوان أو الفئة أو المسؤول...')
        self.search.addAction(QIcon(theme.icon_pixmap('search', '#FFFFFF', 18)), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setMinimumWidth(150); self.search.setMaximumWidth(280); SearchGrow(self.search, 280, 420); hl.addWidget(self.search)
        pal = Btn('الأوامر', 'glass', 'sliders'); pal.setToolTip('لوحة الأوامر (Ctrl+K)'); pal.clicked.connect(self.open_palette); hl.addWidget(pal)
        people = Btn('الأفراد', 'glass', 'users'); people.clicked.connect(self.manage_people); hl.addWidget(people)
        self.theme_btn = Btn('', 'glass', 'sun' if theme.mode() == 'dark' else 'moon'); self.theme_btn.setToolTip('تبديل المظهر: فاتح / داكن (Ctrl+D)')
        self.theme_btn.clicked.connect(self.toggle_theme); hl.addWidget(self.theme_btn); theme.signals.changed.connect(self.sync_theme_btn)
        root.addWidget(self.header)
        navrow = QHBoxLayout(); navrow.setContentsMargins(0, 2, 0, 0)
        self.nav = PillNav([t for t, _ in TABS], [i for _, i in TABS]); navrow.addWidget(self.nav); navrow.addStretch(); root.addLayout(navrow)
        self.stack = FadeStack(); root.addWidget(self.stack, 1)
        self.dashboard = DashboardPage(self); self.page_tasks = self.build_tasks_page(); self.kanban = KanbanPage(self); self.calendar = CalendarPage(self)
        self.page_planning = self.build_planning_page(); self.page_archive = self.build_archive_page(); self.page_reports = self.build_reports_page()
        self.activity = ActivityPage(self); self.settings = SettingsPage(self); self.settings.changed.connect(self.on_setting_changed)
        # every page lives in a scroll area, so nothing is ever cut off on a small screen or a small window
        for pg in (self.dashboard, self.page_tasks, self.kanban, self.calendar, self.page_planning, self.page_archive, self.page_reports, self.activity, self.settings):
            self.stack.addWidget(pg if isinstance(pg, QScrollArea) or pg is self.settings else page_scroll(pg))
        self.nav.currentChanged.connect(self.on_nav)
        self.toast_widget = Toast(central)
        self.statusBar().showMessage('البيانات محفوظة محليًا على هذا الكمبيوتر  •  Ctrl+K لوحة الأوامر')
        self.search.textChanged.connect(self.refresh)

    def build_tasks_page(self):
        page = QWidget(); pl = QVBoxLayout(page); pl.setContentsMargins(0, 0, 0, 0)
        card = Card(); bar = QHBoxLayout(); bar.setSpacing(2)
        for text, variant, icon, fn in [('مهمة جديدة', 'primary', 'plus', self.new_task), ('تعديل', 'soft', 'edit', self.edit_task), ('نسخ', 'soft', 'copy', self.duplicate_task),
                                        ('إنجاز', 'success', 'check_circle', self.mark_done), ('الحالة', 'soft', 'check', self.change_status),
                                        ('أرشفة/حذف', 'soft', 'archive', self.archive_task), ('واتساب', 'soft', 'copy', self.copy_whatsapp)]:
            b = Btn(text, variant, icon); b.clicked.connect(fn); bar.addWidget(b)
        bar.addStretch(); self.task_count = QLabel('0 مهمة'); self.task_count.setObjectName('chip'); bar.addWidget(self.task_count); card.body.addLayout(bar)
        fl = QHBoxLayout(); fl.setSpacing(10)
        self.f_status, self.f_person, self.f_cat, self.f_sort = Combo(), Combo(), Combo(), Combo()
        self.f_status.addItem('كل الحالات', None); self.f_status.addItem('متأخرة', 'late')
        for s in STATUSES: self.f_status.addItem(s, s)
        self.f_person.addItem('كل الأفراد', None); self.f_cat.addItem('كل الفئات', None)
        for label, key in (('الترتيب: التاريخ', 'date'), ('الترتيب: الأولوية', 'priority'), ('الترتيب: المسؤول', 'person'), ('الترتيب: الحالة', 'status')): self.f_sort.addItem(label, key)
        for w in (field_label('تصفية'), self.f_status, self.f_person, self.f_cat, self.f_sort): fl.addWidget(w)
        fl.addStretch(); card.body.addLayout(fl)
        for w in (self.f_status, self.f_person, self.f_cat, self.f_sort): w.currentIndexChanged.connect(self.refresh)
        self.task_table = self.make_table(self.TASK_COLS, self.TASK_KINDS, 'لا توجد مهام مطابقة - اضغط «مهمة جديدة» للبدء')
        self.task_table.cellDoubleClicked.connect(lambda *_: self.edit_task())
        self.task_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu); self.task_table.customContextMenuRequested.connect(self.task_menu)
        card.body.addWidget(self.task_table, 1); pl.addWidget(card, 1); return page

    def build_planning_page(self):
        page = QWidget(); page.setAutoFillBackground(False); lay = QVBoxLayout(page); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        cc = Card(padding=10); controls = QHBoxLayout(); controls.setSpacing(8)
        self.plan_mode = Combo(); self.plan_mode.addItem('عرض اليوم', 'day'); self.plan_mode.addItem('عرض الأسبوع', 'week'); self.plan_mode.addItem('عرض الشهر', 'month')
        self.plan_date = DateBox(QDate.currentDate()); self.plan_person = Combo(); self.plan_person.addItem('كل الأفراد', None)
        prev_btn = Btn('السابق', 'soft', 'chevron_right'); prev_btn.clicked.connect(lambda: self.shift_plan(-1))
        today_btn = Btn('اليوم', 'soft', 'calendar'); today_btn.clicked.connect(self.plan_today)
        next_btn = Btn('التالي', 'soft', 'chevron_left'); next_btn.clicked.connect(lambda: self.shift_plan(1))
        self.plan_mode.currentIndexChanged.connect(self.refresh_planning); self.plan_date.dateChanged.connect(self.refresh_planning); self.plan_person.currentIndexChanged.connect(self.refresh_planning)
        for w in (field_label('الفترة'), self.plan_mode, self.plan_date, self.plan_person): controls.addWidget(w)
        controls.addStretch()
        for w in (prev_btn, today_btn, next_btn): controls.addWidget(w)
        cc.body.addLayout(controls); lay.addWidget(cc)
        kpis = QHBoxLayout(); kpis.setSpacing(0)
        self.plan_total = GradCard('إجمالي المهام', 'tasks', '#6366F1', '#8B5CF6'); self.plan_open = GradCard('مفتوحة', 'clock', '#0EA5E9', '#06B6D4')
        self.plan_done = GradCard('منجزة', 'check_circle', '#10B981', '#14B8A6'); self.plan_late = GradCard('متأخرة', 'alert', '#F43F5E', '#FB923C')
        for c in (self.plan_total, self.plan_open, self.plan_done, self.plan_late): kpis.addWidget(c)
        lay.addLayout(kpis)
        charts = QHBoxLayout(); charts.setSpacing(0)
        c1 = Card(); head = QHBoxLayout(); t = QLabel('توزيع المهام'); t.setObjectName('cardTitle'); self.plan_range_label = QLabel(''); self.plan_range_label.setObjectName('muted')
        head.addWidget(t); head.addStretch(); head.addWidget(self.plan_range_label); c1.body.addLayout(head)
        self.plan_chart = PlanningChart(); c1.body.addWidget(self.plan_chart, 1); charts.addWidget(c1, 3)
        c2 = Card(); t2 = QLabel('حالة المهام'); t2.setObjectName('cardTitle'); c2.body.addWidget(t2)
        self.plan_donut = DonutChart(); c2.body.addWidget(self.plan_donut, 1); charts.addWidget(c2, 2); lay.addLayout(charts)
        tc = Card(); actions = QHBoxLayout(); actions.setSpacing(4)
        add_plan = Btn('إضافة مهمة لهذه الفترة', 'primary', 'plus'); add_plan.clicked.connect(lambda: self.new_task())
        edit_plan = Btn('تعديل المهمة المحددة', 'soft', 'edit'); edit_plan.clicked.connect(self.edit_planned_task)
        actions.addWidget(add_plan); actions.addWidget(edit_plan); actions.addStretch(); tc.body.addLayout(actions)
        self.plan_table = self.make_table(['الوقت', 'المهمة', 'المسؤول', 'التاريخ', 'الأولوية', 'الحالة', 'المتبقي/التأخر'],
                                          {0: 'muted', 1: 'title', 2: 'person', 3: 'text', 4: 'priority', 5: 'pill', 6: 'pill'}, 'لا توجد مهام في هذه الفترة')
        self.plan_table.setMinimumHeight(260); self.plan_table.cellDoubleClicked.connect(lambda *_: self.edit_planned_task())
        tc.body.addWidget(self.plan_table); lay.addWidget(tc)
        return page_scroll(page)

    def build_archive_page(self):
        page = QWidget(); pl = QVBoxLayout(page); pl.setContentsMargins(0, 0, 0, 0); card = Card(); bar = QHBoxLayout(); bar.setSpacing(4)
        restore_btn = Btn('استعادة المحدد', 'success', 'restore'); restore_btn.clicked.connect(self.restore_archived)
        delete_btn = Btn('حذف نهائي', 'danger', 'trash'); delete_btn.clicked.connect(self.delete_archived)
        bar.addWidget(restore_btn); bar.addWidget(delete_btn); bar.addStretch(); card.body.addLayout(bar)
        self.archive_table = self.make_table(self.TASK_COLS[:9], self.TASK_KINDS, 'الأرشيف فارغ'); card.body.addWidget(self.archive_table, 1); pl.addWidget(card, 1); return page

    def build_reports_page(self):
        page = QWidget(); pl = QVBoxLayout(page); pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(0)
        card = Card(); t = QLabel('نطاق التقرير'); t.setObjectName('cardTitle'); card.body.addWidget(t)
        form = QHBoxLayout(); form.setSpacing(12)
        self.from_date = DateBox(QDate.currentDate().addDays(-7)); self.to_date = DateBox(QDate.currentDate().addDays(30))
        self.person_filter = Combo(); self.person_filter.addItem('كل الأفراد', None)
        for label, w in (('من', self.from_date), ('إلى', self.to_date), ('الفرد', self.person_filter)): form.addWidget(field_label(label)); form.addWidget(w)
        form.addStretch(); card.body.addLayout(form)
        self.report_info = QLabel('اختر الفترة والفرد ثم صدّر التقرير.'); self.report_info.setObjectName('chip'); ri = QHBoxLayout(); ri.addWidget(self.report_info); ri.addStretch(); card.body.addLayout(ri)
        pl.addWidget(card)
        tiles = QHBoxLayout(); tiles.setSpacing(0)
        for title, sub, icon, c1, c2, kind in [('تصدير PDF', 'تقرير جاهز للطباعة', 'file', '#F43F5E', '#FB923C', 'pdf'), ('تصدير Word', 'مستند قابل للتعديل', 'doc', '#0EA5E9', '#6366F1', 'docx'),
                                               ('تصدير Excel', 'جدول بيانات منظم', 'sheet', '#10B981', '#14B8A6', 'xlsx'), ('تصدير CSV', 'للتحليل والاستيراد', 'sheet', '#8B5CF6', '#EC4899', 'csv')]:
            tile = GradCard(title, icon, c1, c2, numeric=False, subtitle=sub, clickable=True); tile.clicked.connect(lambda k=kind: self.export_report(k)); tiles.addWidget(tile)
        pl.addLayout(tiles); pl.addStretch()
        for w in (self.from_date, self.to_date): w.dateChanged.connect(self.update_report_info)
        self.person_filter.currentIndexChanged.connect(self.update_report_info); return page

    def setup_tray(self):
        self.setWindowIcon(theme.app_icon())
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self); self.tray.setIcon(theme.app_icon()); self.tray.setToolTip(APP_NAME)
            menu = QMenu(); show = QAction('فتح البرنامج', self); show.triggered.connect(self.showNormal)
            quit_action = QAction('خروج', self); quit_action.triggered.connect(QApplication.quit)
            menu.addAction(show); menu.addAction(quit_action); self.tray.setContextMenu(menu); self.tray.show()

    def setup_shortcuts(self):
        def sc(seq, fn): QShortcut(QKeySequence(seq), self).activated.connect(fn)
        sc('Ctrl+N', lambda: self.new_task()); sc('Ctrl+K', self.open_palette); sc('Ctrl+D', self.toggle_theme); sc('F5', self.refresh)
        sc('Ctrl+F', lambda: (self.search.setFocus(), self.search.selectAll()))
        for i in range(len(TABS)): sc(f'Ctrl+{i + 1}', lambda i=i: self.nav.setCurrentIndex(i))

    # ---------------------------------------------------------------- theme / navigation / feedback
    def toggle_theme(self):
        new = 'light' if theme.mode() == 'dark' else 'dark'
        theme.apply(self.app(), new, theme.current_accent()); self.cfg.set('theme', new)
    def sync_theme_btn(self):
        self.theme_btn.icon_kind = 'sun' if theme.mode() == 'dark' else 'moon'; self.theme_btn.update()
    def on_setting_changed(self, key):
        if key != 'accent': self.refresh()
    def on_nav(self, i):
        self.stack.set_index_animated(i)
        if i == 0: self.dashboard.refresh(); self.dashboard.replay()
        elif i == 2: self.kanban.refresh()
        elif i == 3: self.calendar.refresh()
        elif i == 4:
            for k in (self.plan_total, self.plan_open, self.plan_done, self.plan_late): k.replay()
            self.plan_chart.replay(); self.plan_donut.replay()
        elif i == 7: self.activity.refresh()
    def toast(self, text, kind='success'): self.toast_widget.show_message(text, kind)

    def open_palette(self):
        acts = [('مهمة جديدة', 'Ctrl+N', self.new_task)]
        for i, (label, _icon) in enumerate(TABS): acts.append((f'الانتقال إلى: {label}', f'Ctrl+{i + 1}', lambda i=i: self.nav.setCurrentIndex(i)))
        acts += [('تبديل المظهر فاتح/داكن', 'Ctrl+D', self.toggle_theme), ('نسخ ملخص اليوم', '', self.copy_day_summary), ('نسخ احتياطي الآن', '', self.backup_now),
                 ('إدارة الأفراد', '', self.manage_people), ('تحديث البيانات', 'F5', self.refresh)]
        for name, label in theme.ACCENT_LABELS.items(): acts.append((f'لون التطبيق: {label}', '', lambda n=name: self.settings.pick_accent(n)))
        CommandPalette(acts, self).exec()

    # ---------------------------------------------------------------- data -> UI
    def rebuild_combo(self, combo, all_label, items):
        cur = combo.currentData(); combo.blockSignals(True); combo.clear(); combo.addItem(all_label, None)
        for label, data in items: combo.addItem(label, data)
        combo.setCurrentIndex(max(0, combo.findData(cur))); combo.blockSignals(False)

    def fill_tasks(self, table, tasks, with_reminder, subs):
        now = datetime.now(); table.setUpdatesEnabled(False); table.setRowCount(0)
        for t in tasks:
            r = table.rowCount(); table.insertRow(r); state = logic.task_state(t, now); pill = STATUS_KEYS.get(t['status'], 'scheduled'); d, n = subs.get(t['id'], (0, 0))
            vals = [t['title'], t['person_name'], t['category'] or '', t['task_date'], t['start_time'], t['end_time'], f"{t['priority']}/10", f'{d}/{n}', t['status']]
            if with_reminder: vals.append(f"قبل {t['reminder_minutes']} د")
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c == 0: it.setData(ROLE_ID, t['id'])
                it.setData(ROLE_STATE, state); it.setData(ROLE_PRIO, t['priority']); it.setData(ROLE_PILL, pill); table.setItem(r, c, it)
        table.setUpdatesEnabled(True); table.fit_columns({0: 230, 1: 150, 2: 100, 8: 130})

    def apply_filters(self, tasks):
        st, pid, cat, now = self.f_status.currentData(), self.f_person.currentData(), self.f_cat.currentData(), datetime.now(); out = []
        for t in tasks:
            if pid is not None and t['person_id'] != pid: continue
            if cat and (t['category'] or '') != cat: continue
            if st == 'late':
                if logic.task_state(t, now) != 'late': continue
            elif st and t['status'] != st: continue
            out.append(t)
        key = self.f_sort.currentData()
        if key == 'priority': out.sort(key=lambda t: (-t['priority'], t['task_date'], t['start_time']))
        elif key == 'person': out.sort(key=lambda t: (t['person_name'], t['task_date'], t['start_time']))
        elif key == 'status': out.sort(key=lambda t: (STATUSES.index(t['status']) if t['status'] in STATUSES else 9, t['task_date']))
        return out

    def refresh(self, *_):
        q = self.search.text(); db = self.db; subs = db.subtask_counts(); tasks = db.tasks(search=q)
        self.rebuild_combo(self.f_person, 'كل الأفراد', [(p['name'], p['id']) for p in db.people()])
        self.rebuild_combo(self.f_cat, 'كل الفئات', [(c, c) for c in db.categories()])
        shown = self.apply_filters(tasks)
        self.fill_tasks(self.archive_table, db.archived_tasks(q), False, subs); self.fill_tasks(self.task_table, shown, True, subs)
        self.task_count.setText(f'{len(shown)} مهمة'); self.hero_sub.setText(logic.greeting_text())
        self.rebuild_combo(self.person_filter, 'كل الأفراد', [(p['name'], p['id']) for p in db.people()])
        self.update_report_info(); self.refresh_planning()
        self.dashboard.refresh(); self.kanban.refresh(); self.calendar.refresh(); self.activity.refresh()

    def update_report_info(self, *_):
        start = self.from_date.date().toString('yyyy-MM-dd'); end = self.to_date.date().toString('yyyy-MM-dd')
        n = len(self.db.report_tasks(start, end, self.person_filter.currentData())) if start <= end else 0
        self.report_info.setText(f'عدد المهام في الفترة المحددة: {n}')

    def refresh_planning(self, *args):
        if not hasattr(self, 'plan_table'): return
        self.rebuild_combo(self.plan_person, 'كل الأفراد', [(p['name'], p['id']) for p in self.db.people(active_only=True)])
        start_date, end_date = logic.plan_bounds(self.plan_date.date().toPython(), self.plan_mode.currentData(), self.cfg.get('week_start'))
        start, end = start_date.isoformat(), end_date.isoformat(); tasks = self.db.report_tasks(start, end, self.plan_person.currentData())
        now = datetime.now(); today = now.date()
        open_tasks = [t for t in tasks if t['status'] not in ('منجزة', 'ملغاة')]; done = [t for t in tasks if t['status'] == 'منجزة']
        late = [t for t in open_tasks if logic.parse_dt(t['task_date'], t['end_time']) < now]; cancelled = len(tasks) - len(open_tasks) - len(done)
        self.plan_total.set_value(len(tasks)); self.plan_open.set_value(len(open_tasks)); self.plan_done.set_value(len(done)); self.plan_late.set_value(len(late))
        self.plan_range_label.setText(ltr(f'{start}  →  {end}'))
        self.plan_donut.set_data([('منجزة', len(done), '#10B981'), ('قيد الانتظار', len(open_tasks) - len(late), '#6366F1'), ('متأخرة', len(late), '#F43F5E'), ('ملغاة', cancelled, '#94A3B8')])
        self.plan_table.setUpdatesEnabled(False); self.plan_table.setRowCount(0)
        for t in tasks:
            r = self.plan_table.rowCount(); self.plan_table.insertRow(r); end_dt = logic.parse_dt(t['task_date'], t['end_time'])
            remaining = 'منجزة' if t['status'] == 'منجزة' else ('متأخرة' if end_dt < now and t['status'] not in ('ملغاة', 'منجزة') else ('ملغاة' if t['status'] == 'ملغاة' else 'ضمن الوقت'))
            vals = [ltr(f"{t['start_time']} – {t['end_time']}"), t['title'], t['person_name'], t['task_date'], f"{t['priority']}/10", t['status'], remaining]
            pills = {5: STATUS_KEYS.get(t['status'], 'scheduled'), 6: REMAINING_KEYS[remaining]}; state = logic.task_state(t, now)
            for c, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                if c == 0: item.setData(ROLE_ID, t['id'])
                item.setData(ROLE_STATE, state); item.setData(ROLE_PRIO, t['priority']); item.setData(ROLE_PILL, pills.get(c, 'scheduled')); self.plan_table.setItem(r, c, item)
        self.plan_table.setUpdatesEnabled(True); self.plan_table.fit_columns({0: 140, 1: 220, 2: 150, 6: 130})
        highlight = -1
        if self.plan_mode.currentData() == 'day':
            h0, h1 = self.cfg.get('day_start'), max(self.cfg.get('day_end'), self.cfg.get('day_start') + 1)
            labels = [f'{h:02d}:00' for h in range(h0, h1)]; values = [sum(1 for t in tasks if int(t['start_time'][:2]) == h) for h in range(h0, h1)]
            if start_date == today and h0 <= now.hour < h1: highlight = now.hour - h0
        else:
            day = start_date; labels = []; values = []
            while day <= end_date:
                if day == today: highlight = len(labels)
                labels.append(day.strftime('%d/%m')); values.append(sum(1 for t in tasks if t['task_date'] == day.isoformat())); day += timedelta(days=1)
        self.plan_chart.set_data(labels, values, highlight)

    def shift_plan(self, direction):
        mode = self.plan_mode.currentData(); d = self.plan_date.date()
        d = d.addDays(direction) if mode == 'day' else (d.addDays(7 * direction) if mode == 'week' else d.addMonths(direction)); self.plan_date.setDate(d)
    def plan_today(self): self.plan_date.setDate(QDate.currentDate())

    # ---------------------------------------------------------------- task actions
    def current_task(self):
        r = self.task_table.currentRow()
        return self.task_table.item(r, 0).data(ROLE_ID) if r >= 0 and self.task_table.item(r, 0) else None
    def need_task(self):
        tid = self.current_task()
        if not tid: info(self, 'اختر مهمة', 'حدد مهمة من الجدول أولًا.')
        return tid
    def default_day(self):
        w = self.stack.currentWidget()
        inner = w.widget() if isinstance(w, QScrollArea) else w
        if w is self.page_planning: return self.plan_date.date().toPython()
        if inner is self.calendar: return self.calendar.grid.selected
        return None

    def task_menu(self, pos):
        r = self.task_table.rowAt(pos.y())
        if r < 0: return
        self.task_table.selectRow(r); m = QMenu(self)
        for text, fn in (('تعديل', self.edit_task), ('نسخ المهمة (تكرار)', self.duplicate_task), ('وضع علامة منجزة', self.mark_done), ('تغيير الحالة...', self.change_status),
                         ('نسخ رسالة واتساب', self.copy_whatsapp), ('أرشفة / حذف', self.archive_task)):
            a = m.addAction(text); a.triggered.connect(lambda _=False, f=fn: f())
        m.exec(self.task_table.viewport().mapToGlobal(pos))

    def new_task(self, day=None):
        if not isinstance(day, date): day = None   # Btn.clicked passes a bool
        day = day or self.default_day()
        d = TaskDialog(self.db, None, self.cfg, self, day)
        if d.exec() != TaskDialog.DialogCode.Accepted: return
        p, subs, repeat, end = d.split_payload(); first = self.db.add_task(p); self.db.set_subtasks(first, subs); count = 1
        if repeat != 'none':
            start = datetime.strptime(p['task_date'], '%Y-%m-%d').date(); last = datetime.strptime(end, '%Y-%m-%d').date()
            for nd in logic.recurrence_dates(start, last, repeat, logic.WEEKEND_PRESETS.get(self.cfg.get('weekend'), (4, 5))):
                q = dict(p, task_date=nd.isoformat()); nid = self.db.add_task(q); self.db.set_subtasks(nid, [(t, False) for t, _ in subs]); count += 1
        self.refresh(); self.toast('تمت إضافة المهمة' if count == 1 else f'تمت إضافة {count} مهمة (تكرار)')
    def edit_task_id(self, tid):
        task = self.db.get_task(tid)
        if not task: return
        d = TaskDialog(self.db, task, self.cfg, self)
        if d.exec() == TaskDialog.DialogCode.Accepted:
            p, subs, _r, _e = d.split_payload(); self.db.update_task(tid, p); self.db.set_subtasks(tid, subs); self.refresh(); self.toast('تم حفظ التعديلات')
    def edit_task(self):
        tid = self.need_task()
        if tid: self.edit_task_id(tid)
    def edit_planned_task(self):
        r = self.plan_table.currentRow()
        if r >= 0 and self.plan_table.item(r, 0): self.edit_task_id(self.plan_table.item(r, 0).data(ROLE_ID))
    def duplicate_task(self):
        tid = self.need_task()
        if not tid: return
        t = self.db.get_task(tid); p = {k: t[k] for k in ('title', 'person_id', 'task_date', 'start_time', 'end_time', 'priority', 'details', 'reminder_minutes', 'category')}
        p['title'] = t['title'] + ' (نسخة)'; p['status'] = 'مجدولة'; nid = self.db.add_task(p)
        self.db.set_subtasks(nid, [(s['title'], False) for s in self.db.subtasks(tid)]); self.refresh(); self.toast('تم إنشاء نسخة من المهمة')
    def set_status(self, tid, status):
        self.db.update_task(tid, {'status': status}); self.refresh(); self.toast(f'تم تحديث الحالة: {status}')
    def mark_done(self):
        tid = self.need_task()
        if tid: self.set_status(tid, 'منجزة')
    def change_status(self):
        tid = self.need_task()
        if not tid: return
        d = StatusDialog(self.db.get_task(tid)['status'], self)
        if d.exec() == StatusDialog.DialogCode.Accepted and d.choice: self.set_status(tid, d.choice)
    def archive_task(self):
        tid = self.need_task()
        if not tid: return
        ans = ask_choice(self, 'إجراء على المهمة', 'ماذا تريد أن تفعل بالمهمة المحددة؟', [('أرشفة', 'accept'), ('حذف نهائي', 'destructive'), ('إلغاء', 'reject')])
        if ans == 0: self.db.archive_task(tid); self.toast('نُقلت المهمة إلى الأرشيف', 'info')
        elif ans == 1:
            if ask(self, 'حذف نهائي', 'لن يمكن استرجاع المهمة بعد الحذف. متابعة؟', yes='حذف', danger=True): self.db.delete_task(tid); self.toast('تم حذف المهمة نهائيًا', 'warn')
        self.refresh()
    def archived_id(self):
        r = self.archive_table.currentRow()
        if r < 0 or not self.archive_table.item(r, 0): info(self, 'اختر مهمة', 'حدد مهمة من الأرشيف أولًا.'); return None
        return self.archive_table.item(r, 0).data(ROLE_ID)
    def restore_archived(self):
        tid = self.archived_id()
        if tid: self.db.restore_task(tid); self.refresh(); self.toast('تمت استعادة المهمة')
    def delete_archived(self):
        tid = self.archived_id()
        if tid and ask(self, 'حذف نهائي', 'حذف المهمة من الأرشيف نهائيًا؟ لا يمكن التراجع عن ذلك.', yes='حذف', danger=True): self.db.delete_task(tid); self.refresh(); self.toast('تم حذف المهمة نهائيًا', 'warn')
    def copy_whatsapp(self):
        tid = self.need_task()
        if not tid: return
        t = self.db.get_task(tid); msg = f"📌 مهمة عمل\nالمهمة: {t['title']}\nالمسؤول: {t['person_name']}\nالتاريخ: {t['task_date']}\nالوقت: {t['start_time']} - {t['end_time']}\nالأولوية: {t['priority']}/10\nالحالة: {t['status']}"
        if t['category']: msg += '\nالفئة: ' + t['category']
        steps = self.db.subtasks(tid)
        if steps: msg += '\nالخطوات:\n' + '\n'.join(('✅ ' if s['done'] else '⬜ ') + s['title'] for s in steps)
        if t['details']: msg += '\nالتفاصيل: ' + t['details']
        QApplication.clipboard().setText(msg); self.toast('نُسخت الرسالة - الصقها في واتساب')
    def copy_day_summary(self):
        today = date.today(); QApplication.clipboard().setText(logic.today_summary(self.db.day_tasks(today.isoformat()), today)); self.toast('نُسخ ملخص اليوم - الصقه في واتساب')
    def manage_people(self):
        PeopleDialog(self.db, self).exec(); self.refresh()

    # ---------------------------------------------------------------- reports / data
    def export_report(self, kind):
        start = self.from_date.date().toString('yyyy-MM-dd'); end = self.to_date.date().toString('yyyy-MM-dd'); pid = self.person_filter.currentData()
        if start > end: warn(self, 'فترة غير صحيحة', 'تاريخ البداية يجب أن يسبق تاريخ النهاية.'); return
        tasks = self.db.report_tasks(start, end, pid)
        if not tasks: info(self, 'لا توجد بيانات', 'لا توجد مهام في الفترة المحددة.'); return
        path, _ = QFileDialog.getSaveFileName(self, 'حفظ التقرير', f'تقرير_المهام_{start}_{end}.{kind}', f'{kind.upper()} (*.{kind})')
        if not path: return
        try: {'pdf': export_pdf, 'docx': export_docx, 'xlsx': export_xlsx, 'csv': export_csv}[kind](tasks, path, start, end); self.toast('تم تصدير التقرير بنجاح')
        except Exception as e: error(self, 'تعذر التصدير', f'حدث خطأ أثناء إنشاء التقرير:\n{e}')
    def export_all_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, 'تصدير كل المهام', f'كل_المهام_{date.today().isoformat()}.csv', 'CSV (*.csv)')
        if not path: return
        try: export_csv(self.db.tasks(include_archived=True), path); self.toast('تم تصدير كل المهام')
        except Exception as e: error(self, 'تعذر التصدير', str(e))
    def backup_now(self):
        path, _ = QFileDialog.getSaveFileName(self, 'حفظ نسخة احتياطية', f'نسخة_المهام_{date.today().isoformat()}.sqlite3', 'SQLite (*.sqlite3 *.db)')
        if not path: return
        try: self.db.backup_to(path); self.toast('تم حفظ النسخة الاحتياطية')
        except Exception as e: error(self, 'تعذر النسخ', str(e))
    def restore_backup(self):
        path, _ = QFileDialog.getOpenFileName(self, 'اختيار نسخة احتياطية', '', 'SQLite (*.sqlite3 *.db)')
        if not path: return
        if not ask(self, 'استعادة نسخة', 'سيتم استبدال كل البيانات الحالية بمحتوى النسخة المختارة (مع حفظ نسخة من بياناتك الحالية أولًا). متابعة؟', yes='استعادة', danger=True): return
        try:
            self.db.backup_to(app_data_dir() / 'before_restore.sqlite3'); self.db.restore_from(path); self.refresh(); self.toast('تمت استعادة البيانات')
        except Exception as e: error(self, 'تعذرت الاستعادة', str(e))
    def open_data_folder(self): QDesktopServices.openUrl(QUrl.fromLocalFile(str(app_data_dir())))
    def auto_backup(self):
        if not self.cfg.get('auto_backup'): return
        try:
            d = app_data_dir() / 'backups'; d.mkdir(exist_ok=True); self.db.backup_to(d / f'team_tasks_{date.today():%Y%m%d}.sqlite3')
            for old in sorted(d.glob('team_tasks_*.sqlite3'))[:-7]: old.unlink()
        except Exception: pass

    # ---------------------------------------------------------------- reminders
    def check_reminders(self):
        now = datetime.now(); upcoming = self.db.tasks_due_for_reminder(now.strftime('%Y-%m-%d %H:%M'))
        for t in upcoming:
            key = f"{t['id']}:{t['task_date']}:{t['start_time']}"
            if self.db.reminder_seen(key): continue
            when = logic.parse_dt(t['task_date'], t['start_time']); delta = (when - now).total_seconds() / 60
            if 0 <= delta <= t['reminder_minutes']:
                self.notify('موعد مهمة قريب', f"{t['title']}\nالمسؤول: {t['person_name']}\nبعد {max(0, int(delta))} دقيقة"); self.db.mark_reminder_seen(key)
            elif now >= logic.parse_dt(t['task_date'], t['end_time']) and t['status'] not in ('منجزة', 'ملغاة'):
                latekey = 'late:' + key
                if not self.db.reminder_seen(latekey): self.notify('مهمة متأخرة', f"{t['title']}\nالمسؤول: {t['person_name']}"); self.db.mark_reminder_seen(latekey)
    def notify(self, title, message):
        if self.tray: self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 10000)
        else: info(self, title, message)
    def closeEvent(self, event):
        if self.tray and self.tray.isVisible(): self.hide(); event.ignore(); self.tray.showMessage(APP_NAME, 'سيبقى البرنامج يعمل في منطقة الإشعارات لتذكيرك بالمواعيد.'); return
        event.accept()


def main():
    app = QApplication(sys.argv); app.setStyle('Fusion'); app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    app.setApplicationName(APP_NAME); app.setOrganizationName('MounazzemAlFariq')
    cfg = Config(); theme.setup_fonts(app, Path(__file__).resolve().parent); theme.apply(app, cfg.get('theme'), cfg.get('accent'))
    w = MainWindow(); app.aboutToQuit.connect(w.auto_backup); w.showMaximized(); sys.exit(app.exec())


if __name__ == '__main__':
    main()
