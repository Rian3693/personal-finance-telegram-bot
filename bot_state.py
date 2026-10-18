"""Conversation state that survives a bot restart.

`pending_commands` (the step a typed answer belongs to: /addcash, /sell, /buy...)
used to live only in memory, so a restart in the middle of a question sent the
next answer to the AI chat. PersistentDict is a dict that, once attached to a
file, writes itself after every change and reloads on start. Entries older than
MAX_AGE_MINUTES are dropped on load: a question left that long is abandoned.

Until attach() is called (only by the running bot), it is a plain dict, so
importing the bot in a test never touches the live file.
"""

import json
import os
from datetime import datetime, timedelta

MAX_AGE_MINUTES = 120


class PersistentDict(dict):
    path = None

    def attach(self, path, now=None):
        """Load what was pending before the restart, then save on every change."""
        self.path = path
        now = now or datetime.now()
        try:
            with open(path, encoding='utf-8') as fh:
                saved = json.load(fh)
            when = datetime.fromisoformat(saved.get('saved', '1970-01-01T00:00:00'))
            if now - when <= timedelta(minutes=MAX_AGE_MINUTES):
                for key, value in (saved.get('items') or {}).items():
                    dict.__setitem__(self, int(key) if str(key).lstrip('-').isdigit() else key, value)
        except (FileNotFoundError, ValueError, OSError):
            pass
        self._flush()
        return self

    def _flush(self):
        if not self.path:
            return
        try:
            tmp = self.path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump({'saved': datetime.now().isoformat(timespec='seconds'),
                           'items': {str(k): v for k, v in self.items()}}, fh, ensure_ascii=False, default=str)
            os.replace(tmp, self.path)
        except OSError:
            pass                      # never let saving break a reply

    def __setitem__(self, key, value):
        dict.__setitem__(self, key, value)
        self._flush()

    def __delitem__(self, key):
        dict.__delitem__(self, key)
        self._flush()

    def pop(self, *args):
        value = dict.pop(self, *args)
        self._flush()
        return value

    def popitem(self):
        item = dict.popitem(self)
        self._flush()
        return item

    def clear(self):
        dict.clear(self)
        self._flush()

    def update(self, *args, **kwargs):
        dict.update(self, *args, **kwargs)
        self._flush()

    def setdefault(self, key, default=None):
        value = dict.setdefault(self, key, default)
        self._flush()
        return value
