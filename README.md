# TZen

A tiny, pluggable Python testing framework built around **test classes**, **steps**, and **fixtures**, with automatic dependency injection, simple reporting, and one-file documentation.

## Install

```bash
pip install -e .
```

## Quick Start

### 1) Minimal test

```python
from tzen import tz_testcase, tz_step

@tz_testcase
class HelloTest:
    """@description: A minimal test"""

    @tz_step
    def step_hello(self):
        print("hello from step")
```

### 2) Add a fixture (injected by type)

```python
from tzen import tz_fixture, tz_testcase, tz_step

@tz_fixture
class Conn:
    def setup(self): print("setup conn")
    def teardown(self): print("teardown conn")
    def ping(self): print("pong")

@tz_testcase
class UsesFixture:
    def __init__(self, conn: Conn):   # injected in constructor
        conn.ping()

    @tz_step
    def run(self, conn: Conn):        # injected in step
        conn.ping()
```

### 3) Add constants (injected by name)

```python
from tzen.tz_constants import tz_add_constant
from tzen import tz_testcase, tz_step

tz_add_constant("PORT", 5555)

@tz_testcase
class UsesConstant:
    def __init__(self, PORT):         # injected by name
        print("port is", PORT)

    @tz_step
    def run(self, PORT):
        print("still", PORT)
```

### 4) Run a session and build a report

```python
from tzen.tz_tree import TzTree
from tzen.tz_session import TZSession

tree = TzTree()
session = TZSession(tree)
session.start()
session.build_report("report.html")   # writes a minimal HTML report
```

### 5) Generate documentation (one Markdown file)

```python
from tzen.tz_tree import TzTree
from tzen.tz_doc import tz_build_documentation

tree = TzTree()
tz_build_documentation(tree, name="TESTS.md", path=".")
```

**Docstrings format:** use simple `@key:` blocks inside docstrings.

```python
@tz_testcase
class DocgedTest:
    """
    @description: High-level description
    @summary: one-liner
    @notes:
      - uses Conn
      - prints hello
    """

    @tz_step
    def step_a(self):
        """@description: Does A"""
        ...
```

### 6) Requirements (optional)

Tag tests/steps and load requirement details from a file for docs.

```python
from tzen import tz_testcase, tz_step
from tzen.tz_doc import tz_load_requirements

tz_load_requirements("reqs.yaml")   # or .json / .toml

@tz_testcase(requirements=["SRS_1009"])
class ReqTest:
    @tz_step(requirements=["SVR_2128"])
    def do(self): pass
```

`reqs.yaml`:

```yaml
SRS_1009:
  description: Module shall ping
SVR_2128:
  description: Shall print message
```

### 7) Extensibility

- **Doc backends** and **session report backends** can be added via plugins.
- Defaults: Markdown docs and a minimal HTML report.

---

## Full minimal example

```python
from tzen import tz_testcase, tz_step, tz_fixture
from tzen.tz_session import TZSession
from tzen.tz_tree import TzTree
from tzen.tz_doc import tz_build_documentation

@tz_fixture
class F:
    def setup(self): pass
    def teardown(self): pass

@tz_testcase(requirements=["SRS_1009"])
class MyTest:
    """@description: Example test"""
    @tz_step
    def s1(self, f: F):
        print("ok")

tree = TzTree()
session = TZSession(tree)
session.start()
session.build_report("report.html")
tz_build_documentation(tree, "TESTS.md", ".")
```

**License:** MIT