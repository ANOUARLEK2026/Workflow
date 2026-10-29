"""logic.py - pure-Python helpers (no Qt) so they can be unit-tested anywhere."""
import calendar
from datetime import datetime, date, timedelta, timezone

WEEKDAYS = ['الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت', 'الأحد']   # datetime.weekday() order
MONTHS = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']
STATUSES = ['مجدولة', 'قيد التنفيذ', 'منجزة', 'ملغاة']
WEEKEND_PRESETS = {'fri_sat': (4, 5), 'sat_sun': (5, 6), 'fri': (4,), 'sun': (6,)}
WEEKEND_LABELS = {'fri_sat': 'الجمعة والسبت', 'sat_sun': 'السبت والأحد', 'fri': 'الجمعة فقط', 'sun': 'الأحد فقط'}
WEEK_START_LABELS = {6: 'الأحد', 5: 'السبت', 0: 'الاثنين'}
REPEATS = [('بدون تكرار', 'none'), ('يومي', 'daily'), ('أيام العمل فقط', 'workdays'), ('أسبوعي', 'weekly'), ('شهري', 'monthly')]
ACTION_PILLS = {'إنشاء': 'done', 'تعديل': 'scheduled', 'أرشفة': 'progress', 'استعادة': 'ontime', 'حذف': 'late'}


def parse_dt(date_s, time_s):
    return datetime.strptime(f'{date_s} {time_s}', '%Y-%m-%d %H:%M')


def task_state(t, now=None):
    """done / cancel / late / progress / scheduled."""
    now = now or datetime.now()
    if t['status'] == 'منجزة': return 'done'
    if t['status'] == 'ملغاة': return 'cancel'
    try: end = parse_dt(t['task_date'], t['end_time'])
    except ValueError: end = None
    if end and end < now: return 'late'
    return 'progress' if t['status'] == 'قيد التنفيذ' else 'scheduled'


def greeting_text(now=None):
    now = now or datetime.now()
    hello = 'صباح الخير' if now.hour < 12 else ('مساء الخير' if now.hour < 18 else 'مساء النور')
    return f'{hello}  •  {WEEKDAYS[now.weekday()]}، {now.day} {MONTHS[now.month - 1]} {now.year}'


def week_start_of(d, week_start=6):
    return d - timedelta(days=(d.weekday() - week_start) % 7)


def add_months(d, n):
    y = d.year + (d.month - 1 + n) // 12
    m = (d.month - 1 + n) % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def plan_bounds(selected, mode, week_start=6):
    if mode == 'day': return selected, selected
    if mode == 'week':
        s = week_start_of(selected, week_start); return s, s + timedelta(days=6)
    s = selected.replace(day=1); return s, s.replace(day=calendar.monthrange(s.year, s.month)[1])


def month_weeks(year, month, week_start=6):
    """List of weeks (each 7 dates) covering the month, starting on `week_start`."""
    first = date(year, month, 1)
    d = week_start_of(first, week_start)
    last = date(year, month, calendar.monthrange(year, month)[1])
    weeks = []
    while d <= last:
        weeks.append([d + timedelta(days=i) for i in range(7)]); d += timedelta(days=7)
    return weeks


def recurrence_dates(first, last, repeat, weekend=(4, 5), limit=500):
    """Dates AFTER `first` up to `last` for a repeating task."""
    out = []
    if repeat in ('daily', 'workdays'):
        d = first
        while len(out) < limit:
            d += timedelta(days=1)
            if d > last: break
            if repeat == 'workdays' and d.weekday() in weekend: continue
            out.append(d)
    elif repeat == 'weekly':
        d = first + timedelta(days=7)
        while d <= last and len(out) < limit: out.append(d); d += timedelta(days=7)
    elif repeat == 'monthly':
        n = 1
        while len(out) < limit:
            d = add_months(first, n)
            if d > last: break
            out.append(d); n += 1
    return out


def overlaps(s1, e1, s2, e2):
    return s1 < e2 and s2 < e1


def percent(part, whole):
    return int(round(100 * part / whole)) if whole else 0


def utc_to_local(s):
    try: return datetime.strptime(s, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    except (ValueError, TypeError): return None


def human_ago(dt, now=None):
    now = now or datetime.now()
    if dt is None: return ''
    sec = max(0, int((now - dt).total_seconds()))
    if sec < 60: return 'الآن'
    if sec < 3600: return f'منذ {sec // 60} دقيقة'
    if sec < 86400: return f'منذ {sec // 3600} ساعة'
    if sec < 86400 * 7: return f'منذ {sec // 86400} يوم'
    return dt.strftime('%Y-%m-%d')


def today_summary(tasks, day):
    """WhatsApp-friendly daily schedule grouped by person."""
    lines = [f'📅 جدول يوم {WEEKDAYS[day.weekday()]} {day.isoformat()}', '']
    if not tasks: return '\n'.join(lines + ['لا توجد مهام مجدولة لهذا اليوم.'])
    by = {}
    for t in tasks: by.setdefault(t['person_name'], []).append(t)
    for name, items in by.items():
        lines.append(f'👤 {name}')
        for t in sorted(items, key=lambda x: x['start_time']):
            mark = '✅' if t['status'] == 'منجزة' else ('❌' if t['status'] == 'ملغاة' else '🔸')
            lines.append(f"  {mark} {t['start_time']}-{t['end_time']}  {t['title']}  (أولوية {t['priority']}/10)")
        lines.append('')
    return '\n'.join(lines).rstrip()
