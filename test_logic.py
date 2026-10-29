import unittest
from datetime import date, datetime
import logic


class LogicTests(unittest.TestCase):
    def test_week_bounds_sunday_start(self):
        s, e = logic.plan_bounds(date(2026, 10, 16), 'week', 6)   # Friday
        self.assertEqual((s, e), (date(2026, 10, 11), date(2026, 10, 17)))
    def test_month_bounds(self):
        self.assertEqual(logic.plan_bounds(date(2026, 2, 10), 'month'), (date(2026, 2, 1), date(2026, 2, 28)))
    def test_recurrence_daily_workdays_weekly_monthly(self):
        a, b = date(2026, 10, 16), date(2026, 10, 31)
        self.assertEqual(len(logic.recurrence_dates(a, b, 'daily')), 15)
        wd = logic.recurrence_dates(a, b, 'workdays', weekend=(4, 5))
        self.assertTrue(all(d.weekday() not in (4, 5) for d in wd))
        self.assertEqual(logic.recurrence_dates(a, b, 'weekly'), [date(2026, 10, 23), date(2026, 10, 30)])
        self.assertEqual(logic.recurrence_dates(date(2026, 1, 31), date(2026, 4, 30), 'monthly'), [date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)])
    def test_overlaps(self):
        self.assertTrue(logic.overlaps('09:00', '10:00', '09:30', '11:00'))
        self.assertFalse(logic.overlaps('09:00', '10:00', '10:00', '11:00'))
    def test_state(self):
        t = {'status': 'مجدولة', 'task_date': '2020-01-01', 'end_time': '10:00'}
        self.assertEqual(logic.task_state(t), 'late')
        t['status'] = 'منجزة'; self.assertEqual(logic.task_state(t), 'done')
    def test_month_weeks_cover_month(self):
        w = logic.month_weeks(2026, 10, 6)
        self.assertTrue(all(len(x) == 7 for x in w)); self.assertEqual(w[0][0].weekday(), 6)
        self.assertIn(date(2026, 10, 31), [d for x in w for d in x])
    def test_percent_and_ago(self):
        self.assertEqual(logic.percent(1, 3), 33); self.assertEqual(logic.percent(1, 0), 0)
        now = datetime(2026, 1, 1, 12, 0); self.assertEqual(logic.human_ago(datetime(2026, 1, 1, 11, 0), now), 'منذ 1 ساعة')
    def test_summary(self):
        txt = logic.today_summary([{'person_name': 'أ', 'start_time': '08:00', 'end_time': '09:00', 'title': 'x', 'priority': 5, 'status': 'مجدولة'}], date(2026, 10, 16))
        self.assertIn('👤 أ', txt)


if __name__ == '__main__':
    unittest.main()
