#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino) 
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------

from __future__ import annotations
import re
from typing import Mapping, Optional, Dict, List
from .tz_tree import TzTreeNode
from ._tz_logging import tz_getLogger
from .tz_types import TZDocRecord
from jinja2 import Template
from .tz_tree import TzTree, tz_tree_register_type
from pathlib import Path
from .tz_plugins import hookimpl, hookspec, get_pm

logger = tz_getLogger(__name__)


class TZDocPlugin:
    @hookspec
    def tz_register_doc_backends(self) -> Dict[str, TZDocBackend]:
        """
        Return a dictionary that maps the backend name with its class
        """

class _Builtins:
    @hookimpl
    def tz_register_doc_backends(self):
        return {"default": DefaultMarkdownBackend}

get_pm().register(_Builtins(), "tzen.doc.builtins")

# Load optional third-party entry points (if any)
# Packages can expose: [project.entry-points."tzen_doc_backends"]
try:
    get_pm().load_setuptools_entrypoints("tzen_doc_backends")
except Exception:
    # Stay silent: plugin loading is best-effort
    pass

def _get_doc_backends() -> Dict[str, TZDocBackend]:
    """Collect all registered backends into one dict."""
    backends: Dict[str, TZDocBackend] = {}
    pm = get_pm()
    for mapping in pm.hook.tz_register_doc_backends():
        if mapping:
            # last one wins on same key — simple and predictable
            backends.update(mapping)
    return backends

def register_doc_backend(name: str, backend_cls: TZDocBackend) -> None:
    """
    Ad-hoc runtime registration (no packaging needed).
    Example:
        register_doc_backend("default", MyMarkdownBackend)
    """
    class _AdHoc:
        @hookimpl
        def tzen_register_doc_backends(self):
            return {name: backend_cls}
    get_pm().register(_AdHoc(), f"adhoc:{name}")




_TZEN_REQUIREMENTS_ = {}

def tz_add_requirement(name:str, description:str, details:Dict[str, str]):
    if name in _TZEN_REQUIREMENTS_:
        raise RuntimeError(f"Requirement '{name}' already exists")
    
    _TZEN_REQUIREMENTS_[name] = TZRequirement(name, description, details)

def _tz_requirement_provider(name:str, selector:str):
    if name not in _TZEN_REQUIREMENTS_:
        raise RuntimeError(f"Requirement '{name}' does not exist")
    return _TZEN_REQUIREMENTS_[name]

@tz_tree_register_type('requirement', provider=_tz_requirement_provider)
class TZRequirement:
    __slots__ = ('name', 'description', 'details')

    def __init__(self, name:str, description:str, details:Dict = {}) -> None:
        self.name = name
        self.description = description
        self.details = details

def tz_load_requirements(file_path:str):
    p = Path(file_path)

    file_to_dict = None

    if p.exists():
       
        if p.name.endswith(".json"):
            import json
            file_to_dict = json.load
        
        elif p.name.endswith(".yaml") or p.name.endswith(".yml"):
            import yaml
            file_to_dict = yaml.safe_load
        
        elif p.name.endswith(".toml"):
            import toml
            file_to_dict = toml.load
        
        else:
            raise ValueError("Not supported requirements file extension")
        
        # Load the configuration from the file
        with open(p.name, "r") as f:
            for k,v in file_to_dict(f).items():
                _descr = v.pop("description", "")
                tz_add_requirement(k, _descr, v)


HEADER_RE = re.compile(r'^(?:[ \t]*)@([^:\n]+):[ \t]*(.*)$')  # @key: first-line (indent tollerata)
FENCE_OPEN_RE = re.compile(r'^[ \t]*(```+|~~~+)\S*.*$')       # ```lang   oppure  ~~~lang

# Check if a line closes a fence block that was opened with 3*'token'
def _is_fence_close(line: str, token: str) -> bool:
    ch = token[0]  # '`' or '~'
    return bool(re.match(r'^[ \t]*' + re.escape(ch) + r'{3,}[ \t]*$', line))

def _process_whole_as_default(text: str, *, default_key: str) -> Dict[str, str]:
    """ Parse the whole text as a single block with the given default key."""
    
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

def parse_atdoc(text: str, *, allow_indent: bool = True, default_key: str = "description") -> Dict[str, str]:
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
        line = line.strip()
        if in_fence:
            buf.append(line)
            if _is_fence_close(line, in_fence):
                in_fence = None
            continue

        m_fopen = FENCE_OPEN_RE.match(line)
        if m_fopen:
            if cur_key is None:
                raise ValueError("A fenced block was opened before any header '@key:'")
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

        # content (escape @@ -> @)
        if cur_key is None:
            if line.strip() == "":
                continue  # ignores empty lines before the first header
            raise ValueError("Content found before any header '@key:'")
        buf.append(line[1:] if line.startswith('@@') else line)

    flush()
    
    return out

def tz_doc_extract(node: TzTreeNode) -> TZDocRecord:
    
    _record = TZDocRecord(name=node.name, kind = node.kind, selector=node.get_selector())

    try:
        _obj = node.get_object()
    except Exception as e:
        logger.warning(f"Cannot find documentation for object {node.name}")
    else:
        if node.kind == 'requirement':
            _record.summary = _obj.description
            _record.details = _obj.details
        else:
            _docs = Template(_obj.doc).render(**{x.name:x.value for x in [y.get_object() for y in node.find('constant')]})
            _docs_dict = parse_atdoc(_docs)
            _record.summary = _docs_dict.get("description", "")
            _record.details = _docs_dict

    return _record

class TZDocBackend:

    MODULE_LEVEL = 1
    FIXTURE_LEVEL = 2
    TEST_LEVEL = 2
    CONSTANTS_LEVEL = 2
    STEP_LEVEL = 3

    def __init__(self, name, path) -> None:
        self.name = name
        self.path = path
        self.fixtures = {}
        self.constants = {}
        self._file = ""

    def on_record(self, record: TZDocRecord):
        raise NotImplementedError("You shall implement this method.")

    def write(self):
        _p = Path(self.path).absolute() / self.name

        with open(_p, 'w') as f:
            f.write(self._file)

class DefaultMarkdownBackend(TZDocBackend):
    """
    Generates a single Markdown document:
      - Header + global 'Fixtures' section at the top
      - Per-test sections with steps, fixtures, and constants used
    """

    MODULE_LEVEL = 1
    FIXTURES_TOP_LEVEL = 2
    TEST_LEVEL = 2
    SUBSECTION_LEVEL = 3

    def __init__(self, name: str, path: str | Path) -> None:
        super().__init__(name, path)
        self._fixtures_lines: List[str] = []        # global fixtures section (top of file)
        self._body_lines: List[str] = []            # everything after fixtures section
        self._seen_fixture_names: set[str] = set()  # dedupe fixtures across project

        # prepare header + empty fixtures section (so it stays at the very top)
        self._header = f"# {self.name}\n\n"
        self._fixtures_header = f"{'#'*self.FIXTURES_TOP_LEVEL} Fixtures\n\n"
        self._file = self._compose()  # keep self._file always up to date

    # ---- small helpers -------------------------------------------------------

    @staticmethod
    def _best_summary(rec: TZDocRecord) -> str:
        """Prefer rec.summary, else 'summary' key, else 'description' key."""
        if getattr(rec, "summary", None):
            return rec.summary
        d = getattr(rec, "details", {}) or {}
        return d.get("summary") or d.get("description") or ""

    def _compose(self) -> str:
        """Rebuild the whole file string from parts so that 'Fixtures' stays first."""
        parts: List[str] = [self._header, self._fixtures_header]
        if self._fixtures_lines:
            parts.extend(self._fixtures_lines)
        else:
            parts.append("_No fixtures defined._\n\n")
        parts.extend(self._body_lines)
        return "".join(parts)

    # ---- main API ------------------------------------------------------------

    def on_record(self, record: TZDocRecord):
        """
        Append info as records arrive. We keep 'Fixtures' at the beginning by
        pre-creating that section and appending entries into it whenever a
        fixture record is seen; test content goes to the body.
        """

        kind = record.kind

        if kind == "fixture":
            # Add/Update top fixtures section (dedup by fixture name)
            if record.name not in self._seen_fixture_names:
                desc = self._best_summary(record)
                self._fixtures_lines.append(
                    f"### {record.name}\n\n{desc}\n\n"
                )
                self._seen_fixture_names.add(record.name)

        elif kind == "test":
            # Build the test section with steps, fixtures, and constants used
            test_node = TzTree().resolve(record.selector)
            test_title = f"{'#'*self.TEST_LEVEL} {record.name}\n\n"
            test_intro = (self._best_summary(record) + "\n\n") if self._best_summary(record) else ""

            # Steps (direct children of the test node)
            step_lines: List[str] = []
            if test_node:
                for sn in test_node.get_children_of_kind("step"):
                    try:
                        srec = tz_doc_extract(sn)
                        ssum = self._best_summary(srec)
                    except Exception:
                        ssum = ""
                    if ssum:
                        step_lines.append(f"- **{sn.name}** — {ssum}")
                    else:
                        step_lines.append(f"- **{sn.name}**")

            steps_block = ""
            if step_lines:
                steps_block = f"{'#'*self.SUBSECTION_LEVEL} Steps\n\n" + "\n".join(step_lines) + "\n\n"

            # Fixtures used (anywhere under this test subtree; dedupe by name)
            fixtures_block = ""
            if test_node:
                seen: Dict[str, str] = {}
                for fn in test_node.find("fixture"):
                    if fn.name in seen:
                        continue
                    try:
                        frec = tz_doc_extract(fn)
                        fsum = self._best_summary(frec)
                    except Exception:
                        fsum = ""
                    seen[fn.name] = fsum
                if seen:
                    lines = []
                    for name in sorted(seen.keys()):
                        if seen[name]:
                            lines.append(f"- **{name}** — {seen[name]}")
                        else:
                            lines.append(f"- **{name}**")
                    fixtures_block = f"{'#'*self.SUBSECTION_LEVEL} Fixtures used\n\n" + "\n".join(lines) + "\n\n"

            # Constants used (anywhere under this test subtree; dedupe by name)
            constants_block = ""
            if test_node:
                cseen: Dict[str, str] = {}
                for cn in test_node.find("constant"):
                    if cn.name in cseen:
                        continue
                    try:
                        crec = tz_doc_extract(cn)
                        csum = self._best_summary(crec)
                    except Exception:
                        csum = ""
                    cseen[cn.name] = csum
                if cseen:
                    lines = []
                    for name in sorted(cseen.keys()):
                        if cseen[name]:
                            lines.append(f"- **{name}** — {cseen[name]}")
                        else:
                            lines.append(f"- **{name}**")
                    constants_block = f"{'#'*self.SUBSECTION_LEVEL} Constants used\n\n" + "\n".join(lines) + "\n\n"

            # Assemble the test section
            self._body_lines.append(test_title + test_intro + steps_block + fixtures_block + constants_block)

        elif kind == "module":
            # Optional: keep a module header/summary if you like
            # title = f"{'#'*self.MODULE_LEVEL} {record.name}\n\n"
            # self._body_lines.append(title + (self._best_summary(record) + "\n\n" if self._best_summary(record) else ""))
            pass

        # For 'step' and 'constant' we don’t add standalone sections here,
        # because they’re summarized under each test.

        # Keep the exported file string up to date
        self._file = self._compose()

def tz_build_documentation(tree: TzTreeNode, name:str, path:str, backend:str = "default"):

    backends = _get_doc_backends()
    if backend not in backends:
        raise ValueError(f"Unknown backend {backend}. Available backends {backends}")
    
    backend_cls = backends[backend]
    instance = backend_cls(name, path)

    def _visit(_node:TzTreeNode):
        instance.on_record( tz_doc_extract(_node) )
    
    tree.visit(_visit)

    instance.write()

