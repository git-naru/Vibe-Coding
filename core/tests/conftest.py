import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import fixtures  # noqa: E402

HARNESS = HERE / "parity" / "harness.cjs"
NODE_MODULES = HERE / "parity" / "node_modules"


def _node():
    return shutil.which("node")


def run_app(js_code, timeout=300):
    """Run code inside the app's page script (see parity/harness.cjs) and return its JSON answer."""
    if not _node() or not (NODE_MODULES / "pdfjs-dist").exists() or not (NODE_MODULES / "xlsx").exists():
        pytest.skip("parity harness needs node and `npm ci` in core/tests/parity")
    r = subprocess.run([_node(), str(HARNESS)], input=json.dumps({"js": js_code}), capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise AssertionError("app script failed:\n" + r.stderr[-4000:])
    return json.loads(r.stdout, object_hook=lambda o: None if set(o) == {"$num"} else o)


def jsq(s):
    """A Python string as a JavaScript string literal."""
    return json.dumps(str(s))


def _clean(v):
    """JSON as both sides keep it: no None-valued keys (undefined vs null), whole floats as ints."""
    from pfdcore import js
    v = js.plain(v)
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items() if x is not None}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    return v


def diff(a, b, path="", out=None, tol=1e-12):
    """Differences between two JSON values (floats compared to a relative tolerance)."""
    out = [] if out is None else out
    if len(out) > 40:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}.{k}: only in {'app' if k in a else 'pfdcore'} ({a.get(k, b.get(k))!r:.120})")
            else:
                diff(a[k], b[k], f"{path}.{k}", out, tol)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: length app {len(a)} vs pfdcore {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, f"{path}[{i}]", out, tol)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        if not (a == b or math.isclose(a, b, rel_tol=tol, abs_tol=tol)):
            out.append(f"{path}: app {a!r} vs pfdcore {b!r}")
    elif a != b:
        out.append(f"{path}: app {a!r:.200} vs pfdcore {b!r:.200}")
    return out


def assert_same(app_value, py_value, what=""):
    d = diff(_clean(app_value), _clean(py_value))
    assert not d, f"{what} differs from the app:\n" + "\n".join(d)


@pytest.fixture(scope="session")
def work(tmp_path_factory):
    """The made-up inputs, written once per test session."""
    d = tmp_path_factory.mktemp("inputs")
    return {"pdf": fixtures.pfd_pdf(d / "pfd.pdf"), "cost": fixtures.cost_xlsx(d / "eq-cost.xlsx"),
            "qty": fixtures.qty_xlsx(d / "qty.xlsx"), "rates": fixtures.rates_xlsx(d / "rates.xlsx"), "dir": d}
