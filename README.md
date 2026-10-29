# 📋 منظّم الفريق (Team Organizer)

A local Windows app for managing the tasks of a small team (2 to 10 people),
with a full Arabic right-to-left interface. No server, no account: everything is
stored in a SQLite file on your computer.

## Features
- **Tasks:** priority 1 to 10, date and time, reminders, categories, checklists with a progress
  bar, and daily / weekdays / weekly / monthly repeats
- **Views:** Home dashboard, Kanban board (drag cards to change status), month calendar,
  and daily / weekly / monthly planning with charts
- **Team:** up to 10 active members, workload per person, filters by person, status and category,
  and a warning when a person's tasks overlap
- **Search and shortcuts:** command palette (`Ctrl+K`), `Ctrl+N` new task, `Ctrl+F` search, `Ctrl+D` theme
- **Reminders:** Windows tray notifications when a task is near its deadline or late
- **Reports:** export to PDF, Word, Excel and CSV by period and person
- **WhatsApp-ready:** copy a formatted task message or the day summary to the clipboard
- **Activity log:** every create, edit, archive, restore and delete, with relative time
- **Backup:** automatic backup on close (last 7 kept), plus manual backup and restore
- **Look:** light and dark themes, 4 accent colors, animated header, toasts, gradient charts

## Run
1. Install Python 3.11 or newer on Windows
2. `py -m venv .venv` then `.venv\Scripts\activate`
3. `py -m pip install -r requirements.txt`
4. `py main.py` (or double-click `run_windows.bat`)

Tests: `python -m unittest test_database.py test_logic.py`

## Notes
- Data is in `%LOCALAPPDATA%\MounazzemAlFariq\team_tasks.sqlite3`. Back it up regularly.
- Reminders only work while the app is running in the tray.
- For the best Arabic text, put the Cairo or Tajawal `.ttf` files in `fonts/`.
- Arabic shaping in PDF reports depends on the installed font, so check a sample report first.
