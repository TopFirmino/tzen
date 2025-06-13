from __future__ import annotations

import threading
from typing import List, Callable, Any

TZEN_ALL_EVENT = "ALL_EVENTS"

class TZObservable:
    
    interests:List[str] = []

    def __init__(self):
        self._observers = {x:set() for x in self.interests + [TZEN_ALL_EVENT]}
        self._lock = threading.Lock()

    def attach(self, observer_func:Callable[[Any], None], interest):
        with self._lock:
            if interest in self.interests:
                self._observers[interest].add(observer_func)

    def detach(self, observer_func, interest):
        with self._lock:
            if interest in self.interests:
                self._observers[interest].remove(observer_func)

    def notify(self, interest, message):
        with self._lock:
            if interest in self.interests:
                for observer_func in self._observers[interest]:
                    observer_func(message)
                    
            for observer_func in self._observers[TZEN_ALL_EVENT]:
                observer_func((interest, message))