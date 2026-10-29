import tempfile, unittest
from pathlib import Path
from database import Database

class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.db=Database(Path(self.tmp.name)/'test.sqlite3'); self.db.add_person('أنور')
        self.pid=self.db.people()[0]['id']
        self.payload={'title':'اختبار المهمة','person_id':self.pid,'task_date':'2026-10-16','start_time':'08:00','end_time':'09:00','priority':8,'status':'مجدولة','details':'تفاصيل اختبار','reminder_minutes':15}
    def tearDown(self): self.db.close(); self.tmp.cleanup()
    def test_add_and_get_task(self):
        self.db.add_task(self.payload); t=self.db.get_task(1); self.assertEqual(t['title'],'اختبار المهمة'); self.assertEqual(t['person_name'],'أنور')
    def test_search(self):
        self.db.add_task(self.payload); self.assertEqual(len(self.db.tasks(search='تفاصيل')),1); self.assertEqual(len(self.db.tasks(search='غير موجود')),0)
    def test_report_date_range(self):
        self.db.add_task(self.payload); self.assertEqual(len(self.db.report_tasks('2026-10-16','2026-10-16',self.pid)),1); self.assertEqual(len(self.db.report_tasks('2026-10-17','2026-10-18')),0)
    def test_archive_hides_task(self):
        self.db.add_task(self.payload); self.db.archive_task(1); self.assertEqual(len(self.db.tasks()),0); self.assertEqual(len(self.db.tasks(include_archived=True)),1)
    def test_priority_constraint(self):
        bad=self.payload.copy(); bad['priority']=11
        with self.assertRaises(Exception): self.db.add_task(bad)

    def test_subtasks_and_counts(self):
        tid=self.db.add_task(self.payload); self.db.set_subtasks(tid,[('أ',True),('ب',False),('  ',False)])
        self.assertEqual(len(self.db.subtasks(tid)),2); self.assertEqual(self.db.subtask_counts()[tid],(1,2))
        self.db.delete_task(tid); self.assertEqual(self.db.subtasks(tid),[])
    def test_category_and_completion(self):
        p=dict(self.payload,category='اجتماع'); tid=self.db.add_task(p); self.assertEqual(self.db.categories(),['اجتماع'])
        self.assertIsNone(self.db.get_task(tid)['completed_at'])
        self.db.update_task(tid,{'status':'منجزة'}); self.assertIsNotNone(self.db.get_task(tid)['completed_at'])
        self.db.update_task(tid,{'status':'مجدولة'}); self.assertIsNone(self.db.get_task(tid)['completed_at'])
    def test_conflicts(self):
        tid=self.db.add_task(self.payload)
        self.assertEqual(len(self.db.conflicts(self.pid,'2026-10-16','08:30','09:30')),1)
        self.assertEqual(len(self.db.conflicts(self.pid,'2026-10-16','09:00','10:00')),0)
        self.assertEqual(len(self.db.conflicts(self.pid,'2026-10-16','08:30','09:30',exclude_id=tid)),0)
    def test_activity_keeps_title_after_delete(self):
        tid=self.db.add_task(self.payload); self.db.delete_task(tid)
        a=self.db.activity(); self.assertEqual(a[0]['action'],'حذف'); self.assertEqual(a[0]['detail'],'اختبار المهمة')
    def test_backup_restore_roundtrip(self):
        self.db.add_task(self.payload); b=Path(self.tmp.name)/'b.sqlite3'; self.db.backup_to(b)
        self.db.delete_task(1); self.assertEqual(len(self.db.tasks()),0)
        self.db.restore_from(b); self.assertEqual(len(self.db.tasks()),1)
    def test_migration_from_old_schema(self):
        import sqlite3
        old=Path(self.tmp.name)/'old.sqlite3'; c=sqlite3.connect(old)
        c.executescript("CREATE TABLE people(id INTEGER PRIMARY KEY,name TEXT NOT NULL UNIQUE,active INTEGER NOT NULL DEFAULT 1,created_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE tasks(id INTEGER PRIMARY KEY,title TEXT NOT NULL,person_id INTEGER NOT NULL,task_date TEXT NOT NULL,start_time TEXT NOT NULL,end_time TEXT NOT NULL,priority INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'مجدولة',details TEXT DEFAULT '',reminder_minutes INTEGER NOT NULL DEFAULT 15,archived INTEGER NOT NULL DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);INSERT INTO people(name) VALUES('x');INSERT INTO tasks(title,person_id,task_date,start_time,end_time,priority,status) VALUES('t',1,'2026-01-01','08:00','09:00',5,'منجزة');")
        c.commit(); c.close(); d=Database(old); t=d.tasks()[0]; self.assertEqual(t['category'],''); self.assertIsNotNone(t['completed_at']); d.close()

if __name__=='__main__': unittest.main()
