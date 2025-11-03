#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino)
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------
from __future__ import annotations

from tzen.tz_types import TZSessionInfo

from .tz_types import *
from .tz_test import TZTest
from ._tz_logging import tz_getLogger
from .tz_types import TZEventType
import time
from .tz_tree import TzTreeNode
from .tz_fixture import TZFixtureScope
from .tz_plugins import hookimpl, hookspec, get_pm
from pathlib import Path
from typing import List
from datetime import datetime
from jinja2 import Environment


logger = tz_getLogger("")


class TZSvrPlugin:
    @hookspec
    def tz_register_svr_backends(self) -> Dict[str, TZSvrBackend]:
        """
        Return a dictionary that maps the backend name with its class
        """

class _Builtins:
    @hookimpl
    def tz_register_svr_backends(self):
        return {"default_html": DefaultHtmlSVRBackend, "default_plain": DefaultPlainSVRBackend}

get_pm().register(_Builtins(), "tzen.svr.builtins")

# Load optional third-party entry points (if any)
# Packages can expose: [project.entry-points."tzen_svr_backends"]
try:
    get_pm().load_setuptools_entrypoints("tzen_svr_backends")
except Exception:
    # Stay silent: plugin loading is best-effort
    pass

def _get_svr_backends() -> Dict[str, TZSvrBackend]:
    """Collect all registered backends into one dict."""
    backends: Dict[str, TZSvrBackend] = {}
    pm = get_pm()
    for mapping in pm.hook.tz_register_svr_backends():
        if mapping:
            # last one wins on same key — simple and predictable
            backends.update(mapping)
    return backends

def register_svr_backend(name: str, backend_cls: TZSvrBackend) -> None:
    """
    Ad-hoc runtime registration (no packaging needed).
    Example:
        register_doc_backend("default", MyMarkdownBackend)
    """
    class _AdHoc:
        @hookimpl
        def tzen_register_svr_backends(self):
            return {name: backend_cls}
    get_pm().register(_AdHoc(), f"adhoc:{name}")

class TZSvrBackend:

    def __init__(self, path:str) -> None:
        self.path = path

    def build(self, info:TZSessionInfo, logger=logger) -> str:
        raise NotImplementedError("You shall implement this method")
    
    def write(self, info:TZSessionInfo, logger):
        _p = Path(self.path).absolute()

        with open(_p, 'w') as f:
            f.write(self.build(info, logger))

class DefaultHtmlSVRBackend(TZSvrBackend):
    HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{{ report_title or "TZen test report" }}</title>

  <!-- Minimal classless CSS inspired by Sakura (inlined for offline use) -->
  <style>
    /* Sakura-ish classless base */
    :root { --fg:#222; --bg:#fff; --muted:#666; --accent:#0d6efd; --ok:#1b7f3b; --fail:#b00020; --warn:#9a6b00; --card:#f7f7f9; --border:#e5e5e5; }
    @media (prefers-color-scheme: dark) {
      :root { --fg:#eaeaea; --bg:#111; --muted:#aaa; --accent:#6ea8fe; --ok:#5bd08a; --fail:#ff6b7a; --warn:#ffd166; --card:#17171a; --border:#2a2a2e; }
    }
    html { font-size: 16px; }
    body {
      margin: 0 auto; padding: 2rem 1rem; max-width: 1000px;
      color: var(--fg); background: var(--bg); line-height: 1.6; font-family: system-ui, -apple-system, "Segoe UI", Roboto, Ubuntu, Cantarell, "Helvetica Neue", Helvetica, Arial, "Apple Color Emoji","Segoe UI Emoji", "Segoe UI Symbol", sans-serif;
    }
    h1,h2,h3 { line-height: 1.25; margin-top: 1.5rem; }
    h1 { font-size: 2rem; margin-bottom: .25rem; }
    h2 { font-size: 1.35rem; }
    p, ul, ol { margin: .5rem 0 1rem; }
    code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; }
    pre { padding: .75rem; background: var(--card); border:1px solid var(--border); border-radius: .5rem; overflow:auto; }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }

    /* Cards & layout */
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px,1fr)); gap: 1rem; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: .75rem; padding: 1rem; }
    .muted { color: var(--muted); }
    .kpi { font-size: 1.75rem; font-weight: 700; margin: .25rem 0; }
    .ok { color: var(--ok) }
    .fail { color: var(--fail) }
    .warn { color: var(--warn) }

    /* Tables */
    table { width: 100%; border-collapse: collapse; border-spacing: 0; background: transparent; }
    th, td { padding: .65rem .5rem; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }
    th { font-weight: 700; }
    tr:hover td { background: rgba(0,0,0,.03); }
    .badge {
      display: inline-block; padding: .2rem .5rem; border-radius: 999px; font-size: .85rem; border:1px solid var(--border); background: var(--bg);
    }
    .badge.ok { border-color: var(--ok); color: var(--ok); }
    .badge.fail { border-color: var(--fail); color: var(--fail); }

    /* Footer */
    footer { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid var(--border); font-size: .85rem; color: var(--muted); }
  </style>
</head>
<body>

  <header>
    <h1>{{ report_title or "TZen Test Report" }}</h1>
    <p class="muted">
      Start time: <strong>{{ start_time | ts_iso}}</strong> &middot;
      End time: <strong>{{ end_time | ts_iso }}</strong>
      {% if duration %}&middot; Duration: <strong>{{ duration | dhms }}</strong>{% endif %}
    </p>
  </header>

  <section class="grid">
    <div class="card">
      <h2>Overall</h2>
      <div class="kpi">{{ executed_tests }}</div>
      <div class="muted">Total tests executed</div>
    </div>
    <div class="card">
      <h2>Passed</h2>
      <div class="kpi ok">{{ passed_tests }}</div>
      <div class="muted">Total passed</div>
    </div>
    <div class="card">
      <h2>Failed</h2>
      <div class="kpi fail">{{ failed_tests }}</div>
      <div class="muted">Total failed</div>
    </div>
  </section>

  <section>
    <h2>Test details</h2>
    <table>
      <thead>
        <tr>
          <th style="width:32%">Test</th>
          <th style="width:12%">Status</th>
          <th style="width:14%">Duration</th>
          <th>Notes / Error</th>
        </tr>
      </thead>
      <tbody>
        {% for t in tests %}
        <tr>
          <td>
            <strong>{{ t.name }}</strong>
            {% if t.requirement_id %}<div class="muted">Req: {{ t.requirement_id }}</div>{% endif %}
            {% if t.category %}<div class="muted">Category: {{ t.category }}</div>{% endif %}
          </td>
          <td>
            {% if t.status == TZTestStatusType.PASSED %}
              <span class="badge ok">Passed</span>
            {% elif t.status == TZTestStatusType.FAILED  %}
              <span class="badge fail">Failed</span>
            {% else %}
              <span>{{ t.status }}</span>
              <span class="badge">{{ t.status|capitalize }}</span>
            {% endif %}
          </td>
          <td>{{ (t.end - t.start) | dhms }}</td>
          <td>
            {% if t.error %}
              <code style="color:#ff6b7a">{{ t.error }}</code>
              {% if t.error_details %}
                <pre style="color:red">{{ t.error_details }}</pre>
              {% endif %}
            {% else %}
              <span class="muted">-</span>
            {% endif %}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </section>

  <footer>
    Test Report generated with TZen. MIT License.
  </footer>
</body>
</html>
"""

    def _ts_iso(self, ts: float | int) -> str:
        """POSIX ts -> ISO local (YYYY-MM-DD HH:MM:SS)"""
        try:
            return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(ts)

    def _dhms(self, total_seconds: float | int) -> str:
        """seconds -> 'Xd Yh Zm Ws' (omette i componenti a 0, tranne i secondi)"""
        try:
            s = int(round(float(total_seconds)))
        except Exception:
            return str(total_seconds)
        days, s = divmod(s, 86400)
        hours, s = divmod(s, 3600)
        minutes, seconds = divmod(s, 60)
        parts = []
        if days: parts.append(f"{days}d")
        if hours: parts.append(f"{hours}h")
        if minutes: parts.append(f"{minutes}m")
        parts.append(f"{seconds}s") 
        return " ".join(parts)
    
    def build(self, info: TZSessionInfo, logger) -> str:
    
        env = Environment(autoescape=True)
        env.filters["ts_iso"] = self._ts_iso
        env.filters["dhms"] = self._dhms
        
        template = env.from_string(self.HTML_TEMPLATE)
        template.globals['TZTestStatusType'] = TZTestStatusType

        ctx = {
            "report_title": None,
            "executed_tests": info.executed_tests,
            "passed_tests": info.passed_tests,
            "failed_tests": info.failed_tests,
            "start_time": info.start,
            "end_time": info.end,
            "duration": info.end - info.start,
            "tests": info.details.values(),
        }

        return template.render(**ctx)

class DefaultPlainSVRBackend(TZSvrBackend):

    def build(self, info: TZSessionInfo, logger) -> str:
        status = info.name
        total  = info.total_tests
        execd  = info.executed_tests
        logger.info(f"[REPORT] info: {session.name} | Status: {status} | Executed: {execd}/{total}")



class TZSession:
    """ Class to manage a test session. It allows to run tests and notify observers about test events."""
    
    def __init__(self, test_organizer:TzTreeNode) -> None:
        super().__init__()
        self.tests = [x.get_object() for x in test_organizer.find("test")]
        self.info = TZSessionInfo(name="Test Session", total_tests=len(self.tests), details={test.name: None for test in self.tests })
        self.subscribers = {event:[] for event in TZEventType.__members__.values()}
        self.current_test:TZTest = None
        self.result: bool = True
        self.test_organizer = test_organizer
            
    def _on_test_started(self, test:TZTest):
        """Attach the session to a test and notify about the start of the test."""
        self.info.current_test = test.info.name
        self.info.details[test.name] = test.info
        self.info.executed_tests += 1
        self.notify(TZEventType.TEST_STARTED)
    
    def _on_test_terminated(self, test:TZTest):
        # Teardown all test fixtures
        for fix in [x.get_object() for x in self.test_organizer.resolve(test.get_selector()).find("fixture")]:
            if fix.scope in [TZFixtureScope.TEST, TZFixtureScope.STEP]:
                fix.teardown()

        self.info.details[test.name] = test.info
        self.notify(TZEventType.TEST_TERMINATED)


    def _on_step_started(self, test:TZTest):
        self.info.details[test.name] = test.info
        self.notify(TZEventType.STEP_STARTED)
    
    def _on_step_terminated(self, test:TZTest):
        # Teardown all step fixtures
        for fix in [x.get_object() for x in self.test_organizer.resolve(test.current_step.get_selector()).find("fixture")]:
            if fix.scope in [TZFixtureScope.TEST, TZFixtureScope.STEP]:
                fix.teardown()

        self.info.details[test.name] = test.info
        self.notify(TZEventType.STEP_TERMINATED)
        
    def _attach_to_test(self, test:TZTest):
        """Attach the session to a test."""
        test.attach(self._on_test_started, TZEventType.TEST_STARTED)
        test.attach(self._on_test_terminated, TZEventType.TEST_TERMINATED)
        test.attach(self._on_step_started, TZEventType.STEP_STARTED)
        test.attach(self._on_step_terminated, TZEventType.STEP_TERMINATED)
            
    def attach(self, subscriber, event):
        if event in self.subscribers:
            self.subscribers[event].append(subscriber)

    def notify(self, event):
        if event in self.subscribers:
            for subscriber in self.subscribers[event]:
                subscriber(self)
 
    def start(self):
        """Run the test session."""
        logger.info(f"#"*30)
        logger.info(f"[green]TZen[/green] Starting session with a total of {self.info.total_tests} tests")
        logger.info(f"#"*30)
        
        self.info.status = TZSessionStatusType.RUNNING
        self.notify(TZEventType.SESSION_STARTED)
        self.info.start = int(time.time())
        
        for test in self.tests:

            self.current_test = test
            self._attach_to_test(test)
            self.info.current_test = test.name
            _test_result = test.run()
            
            self.result = _test_result and self.result
            
            if  _test_result:
                self.info.passed_tests += 1
            else:
                self.info.failed_tests += 1
        
        self.info.status = TZSessionStatusType.PASSED if self.result else TZSessionStatusType.FAILED
        self.notify(TZEventType.SESSION_TERMINATED)
        self.info.end = int(time.time())
        
        # Teardown all fixtures.
        # FIXME Filter by unique names
        for x in self.test_organizer.find("fixture"):        
            x.get_object().teardown()

    def build_report(self, output_path:str, backend:str = "default_html"):
        
        backends = _get_svr_backends()
        if backend not in backends:
            raise ValueError(f"Unknown backend {backend}. Available backends {backends}")

        backend_cls = backends[backend]
        instance = backend_cls(output_path)
        instance.write(self.info, logger)

