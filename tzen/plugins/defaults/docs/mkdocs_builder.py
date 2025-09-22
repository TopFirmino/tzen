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
import re, textwrap
from jinja2 import Environment, DictLoader, select_autoescape
from typing import Dict
from csv import DictReader
import collections


hookimpl = pluggy.HookimplMarker("tzen")

@hookimpl
def build_docs(organizer, config:Mapping[str, Any], logger, output_folder: Path | None, requirements_file: Path | None):
    """ This plugin generates documentation from test docstrings using a simple @key: value as markdown. The output file is a docs.html file in the output_folder."""
    
    if output_folder is None:
        output_folder = Path("./docs")
        
    output_folder.mkdir(parents=True, exist_ok=True)
    
    # --- prepare env & directories ---
    root = Path(output_folder)
    docs = root / "docs"
    (docs / "requirements").mkdir(parents=True, exist_ok=True)
    (docs / "tests").mkdir(parents=True, exist_ok=True)
    (docs / "assets" / "stylesheets").mkdir(parents=True, exist_ok=True)
    
    # Load Jinja
    env = Environment(
            loader=DictLoader(TEMPLATES),
            autoescape=select_autoescape(enabled_extensions=("html", "xml"))
        )
    
    requirements = {}
    # Looking for requirements and and generate mkdocs 
    if requirements_file and requirements_file.is_file():
        with open(requirements_file, "r") as f:
            reader = DictReader(f)
            requirements = { row["Id"]: row for row in reader if "Id" in row }
    
    # Generates the requirements index page
    if requirements:
        template = env.get_template("docs/requirements/index.md.j2")
        with open(docs / "requirements" / "index.md", "w", encoding="utf-8") as f:
            f.write(template.render())
    
    # Generates all the requirements pages
    for req_id, req in requirements.items():
        template = env.get_template("docs/requirements/requirement.md.j2")
        _file = docs / "requirements" / f"{req_id}.md"
        with open(_file, "w", encoding="utf-8") as f:
            f.write(template.render(req=req))
        requirements[req_id]["rel_path"] = _file
    
    # Generates The tests index page
    template = env.get_template("docs/tests/index.md.j2")
    with open(docs / "tests" / "index.md", "w", encoding="utf-8") as f:
        f.write(template.render())
    
    # Define the Inverse Traceability Matrix
    inv_matrix: Dict[str, list[dict[str, str]]] = {}
    
    # Generate all the test case pages
    for test in organizer.iterate():
        doc = getattr(test, "doc", "") or ""
        inv_matrix[test.name] = find_reference_in_text(doc, set(requirements.keys()))
        doc = replace_text_with_reference(doc, {req:requirements[req]["rel_path"] for req in inv_matrix[test.name]} )
        try:
            meta = parse_atdoc_simple(doc) 
        except Exception as e:
            logger.warning(f"[DOCS] Error parsing doc for test '{test.name}': {e}")
            meta = {"description": doc}
        
        title = test.name.capitalize()
        template = env.get_template("docs/tests/test.md.j2")
        
        with open(docs / "tests" / f"{title}.md", "w", encoding="utf-8") as f:
            f.write(template.render({"title": title, "content": meta, "steps": [(i, step.__doc__) for i, step in enumerate(test.steps)]}))
    

    # From inverse traceability matrix create the forward one
    forward_matrix = {req: [] for req in requirements.keys()}
    for k, v in inv_matrix.items():
        for req_id in v:
            if req_id not in forward_matrix:
                forward_matrix[req_id] = []
            forward_matrix[req_id].append({"title": k.capitalize(), "rel_path": Path("../tests") / f"{k.capitalize()}"})
    
    forward_matrix = collections.OrderedDict(sorted(forward_matrix.items())) 
    inv_matrix = collections.OrderedDict(sorted(inv_matrix.items()))
    for k,v in inv_matrix.items():
        inv_matrix[k] = [ {'Id':x, 'rel_path': Path("../requirements") / f"{x}"} for x in v ]
        
    # Generates the traceability page
    template = env.get_template("docs/traceability.md.j2")
    with open(docs / "traceability.md", "w", encoding="utf-8") as f:
        f.write(template.render(forward_matrix=forward_matrix, inverse_matrix=inv_matrix))


    # Generates the index file
    template = env.get_template("docs/index.md.j2")
    with open(docs / "index.md", "w", encoding="utf-8") as f:
        f.write(template.render(site_name = config.get("site_name", "TZen Documentation")))
    
    # Generates the project files
    template = env.get_template("mkdocs.yml.j2")
    requirements_nav = [{"title": req["Id"], "path": f"requirements/{req['Id']}.md"} for req in requirements.values()]
    tests_nav = [{"title": test.name.capitalize(), "path": f"tests/{test.name.capitalize()}.md"} for test in organizer.iterate()]
    with open(root / "mkdocs.yml", "w", encoding="utf-8") as f:
        f.write(template.render(
            site_name = config.get("site_name", "TZen Documentation"),
            site_description = config.get("site_description", "Auto-generated documentation"),
            site_author = config.get("site_author", "TZen"),
            language = config.get("language", "en"),
            palette_primary = config.get("palette_primary", "indigo"),
            palette_accent = config.get("palette_accent", "indigo"),
            requirements_nav = requirements_nav,
            tests_nav = tests_nav
        ))
        
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
        - navigation.sections
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
    # Traceability HLR -> TC

    This matrix links **Requirements** to **Test Cases** detected in docstrings.

    | Requirement | Covered by Tests |
    |:-----------:|:-----------------|
    {% for req_id, tcs in forward_matrix.items() -%}
    | `{{ req_id }}` | {% if tcs %}{% for tc in tcs %}[{{ tc.title }}]({{ tc.rel_path }}){% if not loop.last %}<br> {% endif %}{% endfor %}{% else %}—{% endif %} |
    {% endfor %}
    
    # Inverse Traceability TC -> HLRs
    
    | TestCase | Covered Requirements |
    |:-----------:|:-----------------|
    {% for tc_name, reqs in inverse_matrix.items() -%}
    | `{{ tc_name }}` | {% if reqs %}{% for req in reqs %}[{{ req.Id }}]({{ req.rel_path }}){% if not loop.last %}<br> {% endif %}{% endfor %}{% else %}—{% endif %} |
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

    """).strip(),

    # docs/tests/test.md
    "docs/tests/test.md.j2": textwrap.dedent("""
    # {{ title }}

    {% for k, v in content.items() %}
    ## {{ k.replace("_", " ").title() }}
    {{ v }}
    {% endfor %}

    ## Steps
    {% for i, step in steps %}
    - **Step {{ i + 1 }}:**
    {{ step }}
    {% endfor %}
    """).strip(),

    # docs/requirements/requirement.md
    "docs/requirements/requirement.md.j2": textwrap.dedent("""
    # {{ req.Id }}
    {% for k, v in req.items() if k != "Id" %}
    ##{{ k.replace("_", " ").title() }}
    {{v}}
    {% endfor %}
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

def find_reference_in_text(text: str, references: set[str]) -> list[str]:
    """ Find all references in the text. References are words in the text that match the given set of references. """
    found = set()
    words = re.findall(r'\b[\w\-_]+\b', text)
    for word in words:
        if word in references:
            found.add(word)
            
    return list(found)

def replace_text_with_reference(text: str, references: Dict[str, dict]) -> str:
    """ Replace all references in the text with a markdown link to the reference. References are words in the text that match the given set of references. """
    
    def replacement(match: re.Match) -> str:
        word = match.group(0)
        if word in references:
            return f"[{word}](../requirements/{word}.md)"
        return word
    
    pattern = r'\b(' + '|'.join(re.escape(ref) for ref in references.keys()) + r')\b'
    return re.sub(pattern, replacement, text)