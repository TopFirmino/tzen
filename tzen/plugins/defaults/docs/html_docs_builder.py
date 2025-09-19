#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino) 
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------

from __future__ import annotations

import pluggy
from typing import Mapping, Any, Optional
from pathlib import Path
import re, json, shutil, textwrap
from jinja2 import Environment, DictLoader, select_autoescape
from typing import Dict

hookimpl = pluggy.HookimplMarker("tzen")

@hookimpl
def build_docs(organizer, config:Mapping[str, Any], logger, output_folder: Path):
    """ This plugin generates documentation from test docstrings using a simple @key: value as markdown. The output file is a docs.html file in the output_folder."""
    output_folder.mkdir(parents=True, exist_ok=True)
    
    # --- prepare env & directories ---
    root = Path(output_folder)
    docs = root / "docs"
    (docs / "requirements" / "_templates").mkdir(parents=True, exist_ok=True)
    (docs / "tests" / "_templates").mkdir(parents=True, exist_ok=True)
    (docs / "assets" / "stylesheets").mkdir(parents=True, exist_ok=True)
    
    # Load Jinja
    env = Environment(
            loader=DictLoader(TEMPLATES),
            autoescape=select_autoescape(enabled_extensions=("html", "xml"))
        )
    
    for test in organizer.iterate():
        doc = getattr(test, "doc", "") or ""
        try:
            meta = parse_atdoc_simple(doc) 
        except Exception as e:
            logger.warning(f"[DOCS] Error parsing doc for test '{test.name}': {e}")
            meta = {"description": doc}

        title = test.name.capitalize()
        
        
        
TEMPLATES: Dict[str, str] = {
    # mkdocs.yml
    "mkdocs.yml.j2": textwrap.dedent("""
    site_name: {{ site_name }}
    site_description: {{ site_description }}
    site_author: {{ site_author }}
    theme:
      name: material
      language: {{ language }}
      features:
        - navigation.instant
        - navigation.tracking
        - navigation.tabs
        - search.highlight
        - search.suggest
        - content.code.copy
      palette:
        - scheme: default
          primary: {{ palette_primary }}
          accent: {{ palette_accent }}
    markdown_extensions:
      - admonition
      - toc:
          permalink: true
      - pymdownx.details
      - pymdownx.superfences
      - pymdownx.tabbed:
          alternate_style: true
      - pymdownx.tasklist:
          custom_checkbox: true
      - pymdownx.highlight
      - pymdownx.emoji
      - tables
      - attr_list
      - sane_lists
    extra_css:
      - assets/stylesheets/extra.css
    nav:
      - Home: index.md
      - Requirements:
          - Overview: requirements/index.md
          {% for req in requirements_nav %}
          - {{ req.title }}: {{ req.path }}
          {% endfor %}
      - Tests:
          - Overview: tests/index.md
          {% for tc in tests_nav %}
          - {{ tc.title }}: {{ tc.path }}
          {% endfor %}
      - Traceability: traceability.md
    """).strip(),

    # docs/index.md
    "docs/index.md.j2": textwrap.dedent("""
    # {{ site_name }}

    Welcome to the **{{ site_name }}** documentation site.

    - Use the sidebar to browse **Requirements** and **Test Cases**.
    - This site is generated programmatically from test docstrings written with the `@key: value` format.
    """).strip(),

    # docs/traceability.md
    "docs/traceability.md.j2": textwrap.dedent("""
    # Traceability

    This matrix links **Requirements** to **Test Cases** detected in docstrings.

    | Requirement | Covered by Tests |
    |:-----------:|:-----------------|
    {% for req_id, tcs in matrix.items() -%}
    | `{{ req_id }}` | {% if tcs %}{% for tc in tcs %}[{{ tc.title }}]({{ tc.rel_path }}){% if not loop.last %}, {% endif %}{% endfor %}{% else %}—{% endif %} |
    {% endfor %}
    """).strip(),

    # docs/requirements/index.md
    "docs/requirements/index.md.j2": textwrap.dedent("""
    # Requirements Overview

    This section is auto-generated from `requirement_ids` found in test docstrings.
    """).strip(),

    # docs/tests/index.md
    "docs/tests/index.md.j2": textwrap.dedent("""
    # Tests Overview

    The following test cases were generated from docstrings.

    | Test | Status | Requirements |
    |------|:------:|-------------:|
    {% for t in tests -%}
    | [{{ t.title }}]({{ t.rel_path }}) | {{ t.status or "—" }} | {% if t.requirement_ids %}{% for r in t.requirement_ids %}`{{ r }}`{% if not loop.last %}, {% endif %}{% endfor %}{% else %}—{% endif %} |
    {% endfor %}
    """).strip(),

    # docs/tests/test.md
    "docs/tests/test.md.j2": textwrap.dedent("""
    ---
    id: {{ t.id }}
    title: "{{ t.title | replace('"', '\\"') }}"
    status: {{ t.status or "Draft" }}
    requirement_ids:
    {% for r in t.requirement_ids %}  - {{ r }}
    {% endfor -%}
    ---

    # {{ t.title }}

    **Name:** `{{ t.name }}`  
    **Status:** {{ t.status or "—" }}  
    **Requirements:** {% if t.requirement_ids %}{% for r in t.requirement_ids %}`{{ r }}` {% endfor %}{% else %}—{% endif %}

    {% for key, val in t.meta.items() if key not in ["title", "status", "requirement_ids", "id"] -%}
    ## {{ key.replace("_", " ").title() }}

    {{ val }}
    {% endfor %}
    """).strip(),

    # docs/requirements/requirement.md
    "docs/requirements/requirement.md.j2": textwrap.dedent("""
    ---
    id: {{ req.id }}
    title: "{{ req.title }}"
    status: {{ req.status }}
    ---

    # {{ req.title }}

    This page was generated automatically from test references to `{{ req.id }}`.
    Add a hand-curated requirement file later if desired.

    ## Covered by Tests
    {% if req.tests %}
    {% for tc in req.tests -%}
    - [{{ tc.title }}]({{ tc.rel_path }})
    {% endfor %}
    {% else %}
    _No tests reference this requirement yet._
    {% endif %}
    """).strip(),

    # docs/assets/stylesheets/extra.css
    "docs/assets/stylesheets/extra.css": textwrap.dedent("""
    .badge { display:inline-block; padding:.2em .6em; border-radius:.5em; font-size:.85em; background:#3f51b5; color:#fff; }
    """).strip(),

    # project files
    "README.md.j2": textwrap.dedent("""
    # {{ site_name }}

    Generated MkDocs project using **Material**.

    ## Local preview

    ```bash
    python -m venv .venv
    source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
    pip install -r requirements.txt
    mkdocs serve
    ```

    Open http://127.0.0.1:8000/
    """).strip(),

    "requirements.txt": textwrap.dedent("""
    mkdocs>=1.5
    mkdocs-material>=9.5
    pymdown-extensions>=10.0
    Jinja2>=3.1
    """).strip(),
}



HEADER_RE = re.compile(r'^(?:[ \t]*)@([^:\n]+):[ \t]*(.*)$')  # @key: first-line (indent tollerata)
FENCE_OPEN_RE = re.compile(r'^[ \t]*(```+|~~~+)\S*.*$')       # ```lang   oppure  ~~~lang

# Check if a line closes a fence block that was opened with 3*'token'
def _is_fence_close(line: str, token: str) -> bool:
    ch = token[0]  # '`' or '~'
    return bool(re.match(r'^[ \t]*' + re.escape(ch) + r'{3,}[ \t]*$', line))

def _process_whole_as_default(text: str, *, default_key: str) -> Dict[str, str]:
    """
    Elabora tutto il testo come un unico valore:
    - mantiene i fence
    - applica l'escape '@@' -> '@' solo FUORI dai fence
    """
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    buf: list[str] = []
    in_fence: Optional[str] = None

    for line in lines:
        if in_fence:
            buf.append(line)
            if _is_fence_close(line, in_fence):
                in_fence = None
            continue

        m_fopen = FENCE_OPEN_RE.match(line)
        if m_fopen:
            buf.append(line)
            in_fence = '```' if '```' in m_fopen.group(1) else '~~~'
            continue

        buf.append(line[1:] if line.startswith('@@') else line)

    return {default_key: '\n'.join(buf).rstrip('\n')}

def parse_atdoc_simple(text: str, *, allow_indent: bool = True, default_key: str = "description") -> Mapping[str, str]:
    """ Main parser for simple @key: value blocks with support for fenced code blocks.
        Lines starting with @@ are unescaped to @.
    """
    
    # Special case where no keys are specified
    if not re.search(r'(?m)^[ \t]*@[^:\n]+:', text):
        return _process_whole_as_default(text, default_key=default_key)
    
    
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    out: Mapping[str, str] = {}
    cur_key: Optional[str] = None
    buf: list[str] = []
    in_fence: Optional[str] = None  # '```' o '~~~'

    def flush():
        nonlocal cur_key, buf
        if cur_key is not None:
            out[cur_key] = '\n'.join(buf).rstrip('\n')
            cur_key, buf = None, []

    for line in lines:
        if in_fence:
            buf.append(line)
            if _is_fence_close(line, in_fence):
                in_fence = None
            continue

        # apertura fence?
        m_fopen = FENCE_OPEN_RE.match(line)
        if m_fopen:
            if cur_key is None:
                raise ValueError("Blocco fence prima di qualsiasi '@key:'")
            buf.append(line)
            in_fence = '```' if '```' in m_fopen.group(1) else '~~~'
            continue

        # header @key:
        m = HEADER_RE.match(line) if allow_indent else re.match(r'^@([^:\n]+):[ \t]*(.*)$', line)
        if m:
            # chiudi sezione precedente
            flush()
            cur_key = m.group(1).strip()
            first = m.group(2)
            buf = [first] if first else []
            continue

        # contenuto (con escape @@ -> @)
        if cur_key is None:
            if line.strip() == "":
                continue  # ignora blank prima del primo header
            raise ValueError("Contenuto trovato prima del primo header '@key:'")
        buf.append(line[1:] if line.startswith('@@') else line)

    flush()
    return out

