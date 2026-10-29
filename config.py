"""config.py - typed access to user settings (QSettings)."""
from PySide6.QtCore import QSettings

DEFAULTS = dict(theme='light', accent='aurora', week_start=6, weekend='fri_sat', day_start=7, day_end=22,
                default_reminder=15, auto_backup=True)


class Config:
    def __init__(self):
        self.s = QSettings()

    def get(self, key):
        default = DEFAULTS[key]
        v = self.s.value(key, default)
        if isinstance(default, bool):
            return v in (True, 'true', 'True', '1', 1)
        if isinstance(default, int):
            try: return int(v)
            except (TypeError, ValueError): return default
        return str(v)

    def set(self, key, value):
        self.s.setValue(key, value)
