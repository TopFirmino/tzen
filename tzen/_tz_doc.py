#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Author:   Lorenzo Furcas (TopFirmino) 
# License:  MIT – see the LICENSE file in the repository root for details.
# ---------------------------------------------------------------------------

from __future__ import annotations
import re
from typing import Mapping, Optional, Dict

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

def parse_atdoc(text: str, *, allow_indent: bool = True, default_key: str = "description") -> Mapping[str, str]:
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

