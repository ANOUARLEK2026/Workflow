import sqlite3
from datetime import date, timedelta
from pathlib import Path

TASK_KEYS = ['title', 'person_id', 'task_date', 'start_time', 'end_time', 'priority', 'status', 'details', 'reminder_minutes', 'category']
SELECT_TASK = 'SELECT t.*,p.name person_name FROM tasks t JOIN people p ON p.id=t.person_id'


class Database:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys=ON')
        self._init()

    # ------------------------------------------------------------------ schema
    def _init(self):
        self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS people(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, active INTEGER NOT NULL DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, title TEXT NOT NULL, person_id INTEGER NOT NULL REFERENCES people(id), task_date TEXT NOT NULL, start_time TEXT NOT NULL, end_time TEXT NOT NULL, priority INTEGER NOT NULL CHECK(priority BETWEEN 1 AND 10), status TEXT NOT NULL DEFAULT 'مجدولة', details TEXT DEFAULT '', reminder_minutes INTEGER NOT NULL DEFAULT 15, archived INTEGER NOT NULL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS reminder_log(reminder_key TEXT PRIMARY KEY, shown_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, task_id INTEGER, action TEXT NOT NULL, detail TEXT, changed_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS subtasks(id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE, title TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0, position INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS idx_tasks_date ON tasks(task_date,start_time); CREATE INDEX IF NOT EXISTS idx_tasks_person ON tasks(person_id);
        CREATE INDEX IF NOT EXISTS idx_sub_task ON subtasks(task_id);
        ''')
        self._migrate()
        self.conn.commit()

    def _migrate(self):
        """Older databases get the new columns without losing data."""
        cols = {r['name'] for r in self.conn.execute('PRAGMA table_info(tasks)')}
        if 'category' not in cols:
            self.conn.execute("ALTER TABLE tasks ADD COLUMN category TEXT DEFAULT ''")
        if 'completed_at' not in cols:
            self.conn.execute('ALTER TABLE tasks ADD COLUMN completed_at TEXT')
            self.conn.execute("UPDATE tasks SET completed_at=datetime(updated_at,'localtime') WHERE status='منجزة' AND completed_at IS NULL")

    def _log(self, tid, action, detail):
        self.conn.execute('INSERT INTO audit_log(task_id,action,detail) VALUES(?,?,?)', (tid, action, detail))

    def _title(self, tid):
        r = self.conn.execute('SELECT title FROM tasks WHERE id=?', (tid,)).fetchone()
        return r['title'] if r else ''

    # ------------------------------------------------------------------ people
    def people(self, active_only=False):
        sql = 'SELECT * FROM people' + (' WHERE active=1' if active_only else '') + ' ORDER BY name'
        return self.conn.execute(sql).fetchall()

    def add_person(self, name):
        self.conn.execute('INSERT INTO people(name) VALUES(?)', (name,)); self.conn.commit()

    def deactivate_person(self, pid):
        self.conn.execute('UPDATE people SET active=0 WHERE id=?', (pid,)); self.conn.commit()

    def reactivate_person(self, pid):
        self.conn.execute('UPDATE people SET active=1 WHERE id=?', (pid,)); self.conn.commit()

    # ------------------------------------------------------------------ tasks
    def add_task(self, p):
        cur = self.conn.execute('INSERT INTO tasks(' + ','.join(TASK_KEYS) + ',completed_at) VALUES(' + ','.join('?' for _ in TASK_KEYS) + ',?)',
                                [p.get(k) if k != 'category' else (p.get('category') or '') for k in TASK_KEYS] +
                                [None if p.get('status') != 'منجزة' else self._now_sql()])
        tid = cur.lastrowid
        self._log(tid, 'إنشاء', p.get('title') or ''); self.conn.commit()
        return tid

    def _now_sql(self):
        return self.conn.execute("SELECT datetime('now','localtime')").fetchone()[0]

    def update_task(self, tid, p):
        vals = [(k, p[k]) for k in TASK_KEYS if k in p]
        if not vals: return
        sql = 'UPDATE tasks SET ' + ','.join(k + '=?' for k, v in vals) + ", updated_at=CURRENT_TIMESTAMP"
        args = [v for k, v in vals]
        if 'status' in p:
            sql += ", completed_at=CASE WHEN ?='منجزة' THEN COALESCE(completed_at,datetime('now','localtime')) ELSE NULL END"
            args.append(p['status'])
        self.conn.execute(sql + ' WHERE id=?', args + [tid])
        self._log(tid, 'تعديل', self._title(tid)); self.conn.commit()

    def get_task(self, tid):
        return self.conn.execute(SELECT_TASK + ' WHERE t.id=?', (tid,)).fetchone()

    def tasks(self, include_archived=False, search=''):
        sql = SELECT_TASK + ' WHERE 1=1'; args = []
        if not include_archived: sql += ' AND t.archived=0'
        if search:
            sql += ' AND (t.title LIKE ? OR t.details LIKE ? OR p.name LIKE ? OR t.category LIKE ?)'; args += [f'%{search}%'] * 4
        return self.conn.execute(sql + ' ORDER BY t.task_date,t.start_time,t.priority DESC', args).fetchall()

    def archived_tasks(self, search=''):
        return self.conn.execute(SELECT_TASK + ' WHERE t.archived=1 AND (t.title LIKE ? OR t.details LIKE ? OR p.name LIKE ? OR t.category LIKE ?) ORDER BY t.task_date DESC', (f'%{search}%',) * 4).fetchall()

    def archive_task(self, tid):
        title = self._title(tid)
        self.conn.execute('UPDATE tasks SET archived=1,updated_at=CURRENT_TIMESTAMP WHERE id=?', (tid,)); self._log(tid, 'أرشفة', title); self.conn.commit()

    def restore_task(self, tid):
        title = self._title(tid)
        self.conn.execute('UPDATE tasks SET archived=0,updated_at=CURRENT_TIMESTAMP WHERE id=?', (tid,)); self._log(tid, 'استعادة', title); self.conn.commit()

    def delete_task(self, tid):
        title = self._title(tid)
        self._log(tid, 'حذف', title); self.conn.execute('DELETE FROM tasks WHERE id=?', (tid,)); self.conn.commit()

    def report_tasks(self, start, end, pid=None):
        sql = SELECT_TASK + ' WHERE t.task_date BETWEEN ? AND ? AND t.archived=0'; args = [start, end]
        if pid is not None: sql += ' AND t.person_id=?'; args.append(pid)
        return self.conn.execute(sql + ' ORDER BY p.name,t.task_date,t.start_time', args).fetchall()

    def day_tasks(self, day_iso):
        return self.conn.execute(SELECT_TASK + ' WHERE t.task_date=? AND t.archived=0 ORDER BY t.start_time,t.priority DESC', (day_iso,)).fetchall()

    def categories(self):
        return [r[0] for r in self.conn.execute("SELECT DISTINCT category FROM tasks WHERE category IS NOT NULL AND category<>'' ORDER BY category")]

    # ------------------------------------------------------------------ subtasks
    def subtasks(self, tid):
        return self.conn.execute('SELECT * FROM subtasks WHERE task_id=? ORDER BY position,id', (tid,)).fetchall()

    def set_subtasks(self, tid, items):
        """items: [(title, done_bool), ...] - replaces the whole checklist."""
        self.conn.execute('DELETE FROM subtasks WHERE task_id=?', (tid,))
        for pos, (title, done) in enumerate(items):
            title = (title or '').strip()
            if title: self.conn.execute('INSERT INTO subtasks(task_id,title,done,position) VALUES(?,?,?,?)', (tid, title, 1 if done else 0, pos))
        self.conn.commit()

    def subtask_counts(self):
        """{task_id: (done, total)}"""
        return {r[0]: (r[1] or 0, r[2]) for r in self.conn.execute('SELECT task_id,SUM(done),COUNT(*) FROM subtasks GROUP BY task_id')}

    # ------------------------------------------------------------------ planning helpers
    def conflicts(self, person_id, day, start, end, exclude_id=None):
        """Open tasks of the same person overlapping the given time range."""
        sql = SELECT_TASK + " WHERE t.person_id=? AND t.task_date=? AND t.archived=0 AND t.status NOT IN ('منجزة','ملغاة') AND t.start_time<? AND ?<t.end_time"
        args = [person_id, day, end, start]
        if exclude_id is not None: sql += ' AND t.id<>?'; args.append(exclude_id)
        return self.conn.execute(sql + ' ORDER BY t.start_time', args).fetchall()

    def completed_per_day(self, days=14, today=None):
        today = today or date.today(); first = today - timedelta(days=days - 1)
        rows = self.conn.execute("SELECT date(completed_at) d,COUNT(*) c FROM tasks WHERE completed_at IS NOT NULL AND date(completed_at)>=? GROUP BY d", (first.isoformat(),)).fetchall()
        got = {r['d']: r['c'] for r in rows}
        return [((first + timedelta(days=i)), got.get((first + timedelta(days=i)).isoformat(), 0)) for i in range(days)]

    def due_per_day(self, days=14, today=None):
        today = today or date.today(); first = today - timedelta(days=days - 1)
        rows = self.conn.execute("SELECT task_date d,COUNT(*) c FROM tasks WHERE archived=0 AND status<>'ملغاة' AND task_date BETWEEN ? AND ? GROUP BY d", (first.isoformat(), today.isoformat())).fetchall()
        got = {r['d']: r['c'] for r in rows}
        return [((first + timedelta(days=i)), got.get((first + timedelta(days=i)).isoformat(), 0)) for i in range(days)]

    def activity(self, limit=200):
        return self.conn.execute('SELECT id,task_id,action,detail,changed_at FROM audit_log ORDER BY id DESC LIMIT ?', (limit,)).fetchall()

    # ------------------------------------------------------------------ reminders
    def tasks_due_for_reminder(self, now):
        return self.conn.execute(SELECT_TASK + " WHERE t.archived=0 AND t.status NOT IN ('منجزة','ملغاة')").fetchall()

    def reminder_seen(self, key): return self.conn.execute('SELECT 1 FROM reminder_log WHERE reminder_key=?', (key,)).fetchone() is not None

    def mark_reminder_seen(self, key): self.conn.execute('INSERT OR IGNORE INTO reminder_log(reminder_key) VALUES(?)', (key,)); self.conn.commit()

    # ------------------------------------------------------------------ backup / restore
    def backup_to(self, path):
        dest = sqlite3.connect(str(path))
        try: self.conn.backup(dest)
        finally: dest.close()

    def restore_from(self, path):
        src = sqlite3.connect(str(path))
        try:
            names = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'people', 'tasks'} <= names: raise ValueError('ملف النسخة الاحتياطية غير صالح')
            src.backup(self.conn)
        finally: src.close()
        self.conn.execute('PRAGMA foreign_keys=ON'); self._init()

    def close(self): self.conn.close()
