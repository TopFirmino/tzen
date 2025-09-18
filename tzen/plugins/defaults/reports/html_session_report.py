import pluggy
from string import Template
from html import escape
from pathlib import Path
from jinja2 import Environment
from datetime import datetime
from tzen.tz_types import *
from typing import Mapping, Any

hookimpl = pluggy.HookimplMarker("tzen")

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
    <h1>{{ report_title or "TZen test report" }}</h1>
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
              <code>{{ t.error }}</code>
              {% if t.error_details %}
                <pre>{{ t.error_details }}</pre>
              {% endif %}
            {% else %}
              <span class="muted">—</span>
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


def _ts_iso(ts: float | int) -> str:
    """POSIX ts -> ISO local (YYYY-MM-DD HH:MM:SS)"""
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)

def _dhms(total_seconds: float | int) -> str:
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
    

@hookimpl
def build_session_report(session:TZSessionInfo, config, logger, output_file: Path):
  logger.info(f"[REPORT] Generating HTML report for session '{session.name}'")
  
  env = Environment(autoescape=True)
  env.filters["ts_iso"] = _ts_iso
  env.filters["dhms"] = _dhms
  
  template = env.from_string(HTML_TEMPLATE)
  template.globals['TZTestStatusType'] = TZTestStatusType
  
    
  ctx = {
    "report_title": None,
    "executed_tests": session.executed_tests,
    "passed_tests": session.passed_tests,
    "failed_tests": session.failed_tests,
    "start_time": session.start,
    "end_time": session.end,
    "duration": session.end - session.start,
    "tests": session.details.values(),
  }

  rendered = template.render(**ctx)

  with open(output_file, "w") as f:
    f.write(rendered)
      