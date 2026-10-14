"""JavaScript behaviour the app relies on, so the ported code gives the app's answers to the digit.

The app runs in a browser: numbers are doubles, regexes are ECMAScript regexes, `localeCompare` is ICU
collation and `toLocaleString` rounds the shortest decimal form of a double. Python differs in each of
these in small ways (banker's rounding, Unicode \\d and \\b, `$` before a final newline, …); the helpers
here restore the JavaScript result.
"""
import functools
import math
import re
from decimal import ROUND_HALF_UP, Context, Decimal, localcontext

_WIDE = Context(prec=1200)   # enough digits for any double's exact decimal value

NaN = float("nan")
INF = float("inf")

# ---- strings ---------------------------------------------------------------------------------
_SPACE = "\t\n\v\f\r \xa0  -     　﻿"   # \s and trim()
_SPACE_CHARS = set("\t\n\v\f\r \xa0     　﻿") | {chr(c) for c in range(0x2000, 0x200B)}
_WORD = "A-Za-z0-9_"


def trim(s):
    """String.prototype.trim (JavaScript's whitespace set, not str.isspace)."""
    i, j = 0, len(s)
    while i < j and s[i] in _SPACE_CHARS:
        i += 1
    while j > i and s[j - 1] in _SPACE_CHARS:
        j -= 1
    return s[i:j]


def trim_end(s):
    j = len(s)
    while j and s[j - 1] in _SPACE_CHARS:
        j -= 1
    return s[:j]


def length(s):
    """String length in UTF-16 code units, as JavaScript counts it."""
    return len(s.encode("utf-16-le")) // 2


def cut(s, n):
    """s.slice(0, n), counted in UTF-16 code units."""
    if all(ord(c) < 0x10000 for c in s):
        return s[:n]
    return s.encode("utf-16-le", "surrogatepass")[: 2 * n].decode("utf-16-le", "surrogatepass")


def jstr(v):
    """String(v) for the values the app passes through templates and String() (None is undefined)."""
    if v is None:
        return "undefined"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        return num_str(v)
    if isinstance(v, list):
        return ",".join("" if x is None else jstr(x) for x in v)
    return str(v)


# ---- regular expressions ---------------------------------------------------------------------
@functools.lru_cache(maxsize=None)
def rx(source, flags=""):
    """Compile an ECMAScript regex source (as written in the app) to an equivalent Python regex."""
    out, i, n, cls = [], 0, len(source), False
    while i < n:
        c = source[i]
        if c == "\\" and i + 1 < n:
            e = source[i + 1]
            i += 2
            if cls:
                out.append({"d": "0-9", "w": _WORD, "s": _SPACE}.get(e) or ("\\" + e))
                if e in "DWSb":
                    raise ValueError(f"unsupported class escape \\{e} in {source!r}")
            else:
                out.append({
                    "d": "[0-9]", "D": "[^0-9]", "w": f"[{_WORD}]", "W": f"[^{_WORD}]",
                    "s": f"[{_SPACE}]", "S": f"[^{_SPACE}]",
                    "b": f"(?:(?<=[{_WORD}])(?![{_WORD}])|(?<![{_WORD}])(?=[{_WORD}]))",
                    "B": f"(?:(?<=[{_WORD}])(?=[{_WORD}])|(?<![{_WORD}])(?![{_WORD}]))",
                }.get(e) or ("\\" + e))
            continue
        if cls:
            if c == "]":
                cls = False
                out.append(c)
            elif c in "[&~|":
                out.append("\\" + c)
            else:
                out.append(c)
        elif c == "[":
            cls = True
            out.append(c)
            if source.startswith("^", i + 1):
                out.append("^")
                i += 1
            if source.startswith("]", i + 1):   # JS: [] matches nothing, [^] anything
                raise ValueError(f"empty class in {source!r}")
        elif c == "$":
            out.append(r"\Z")
        elif c == ".":
            out.append("[^\n\r  ]")
        elif c == "(" and source.startswith("(?<", i) and not source.startswith(("(?<=", "(?<!"), i):
            out.append("(?P<")
            i += 3
            continue
        else:
            out.append(c)
        i += 1
    if "m" in flags or "s" in flags or "y" in flags:
        raise ValueError(f"unsupported regex flags {flags!r}")
    return re.compile("".join(out), re.I if "i" in flags else 0)


def test(source, s, flags=""):
    """RegExp.prototype.test"""
    return rx(source, flags).search(s) is not None


def match(source, s, flags=""):
    """String.prototype.match without the g flag: the first match (groups as JS gives them) or None."""
    return rx(source, flags).search(s)


def match_all(source, s, flags=""):
    """String.prototype.match with the g flag: every full match (empty list for null)."""
    return [m.group(0) for m in rx(source, flags).finditer(s)]


def finditer(source, s, flags=""):
    """String.prototype.matchAll"""
    return rx(source, flags).finditer(s)


def group(m, k):
    """A capture group as JavaScript reports it: '' is kept, a group that did not take part is None."""
    return m.group(k)


def split(source, s, flags=""):
    """String.prototype.split with a regex separator."""
    return rx(source, flags).split(s)


def sub(source, repl, s, flags="", count=0):
    """String.prototype.replace with a regex (count=0 for the g flag, 1 without it)."""
    return rx(source, flags).sub(repl.replace("\\", "\\\\") if isinstance(repl, str) else repl, s, count=count)


# ---- numbers ---------------------------------------------------------------------------------
def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def finite(v):
    return is_num(v) and math.isfinite(v)


def js_round(x):
    """Math.round: halves go up (towards +Infinity)."""
    if not math.isfinite(x):
        return x
    r = math.floor(x)
    return float(r + 1 if x - r >= 0.5 else r)


def number(v):
    """Number(v) / unary + for the strings and numbers the app converts (None is undefined: NaN)."""
    if v is None:
        return NaN
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if is_num(v):
        return float(v)
    s = trim(str(v))
    if s == "":
        return 0.0
    m = re.fullmatch(r"([+-]?)(Infinity|(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)", s)
    if m:
        x = INF if m.group(2) == "Infinity" else float(m.group(2))
        return -x if m.group(1) == "-" else x
    m = re.fullmatch(r"0([xXoObB])([0-9a-fA-F]+)", s)
    if m:
        try:
            return float(int(m.group(2), {"x": 16, "o": 8, "b": 2}[m.group(1).lower()]))
        except ValueError:
            return NaN
    return NaN


def parse_float(v):
    """parseFloat: the longest numeric prefix after leading white space."""
    s = str(v)
    i = 0
    while i < len(s) and s[i] in _SPACE_CHARS:
        i += 1
    m = re.match(r"[+-]?(?:Infinity|(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)", s[i:])
    if not m:
        return NaN
    t = m.group(0)
    if t.lstrip("+-") == "Infinity":
        return -INF if t.startswith("-") else INF
    return float(t)


def _digits(x):
    """Shortest round-trip digits of a positive finite double: (digits, n) with x = 0.digits × 10^n."""
    r = repr(float(x))
    m = re.fullmatch(r"([0-9]+)(?:\.([0-9]+))?(?:e([+-][0-9]+))?", r)
    ip, fp, e = m.group(1), m.group(2) or "", int(m.group(3) or 0)
    d, exp = (ip + fp), e - len(fp)
    stripped = d.lstrip("0")
    t = len(stripped) - len(stripped.rstrip("0"))
    d = stripped.rstrip("0") or "0"
    exp += t
    return d, exp + len(d)


def num_str(x):
    """Number.prototype.toString() (what a template literal prints for a number)."""
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, int):
        return str(x)
    if x != x:
        return "NaN"
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    if x == 0:
        return "0"
    sign = "-" if x < 0 else ""
    d, n = _digits(abs(x))
    k = len(d)
    if k <= n <= 21:
        s = d + "0" * (n - k)
    elif 0 < n <= 21:
        s = d[:n] + "." + d[n:]
    elif -6 < n <= 0:
        s = "0." + "0" * (-n) + d
    else:
        e = n - 1
        s = (d if k == 1 else d[0] + "." + d[1:]) + "e" + ("+" if e >= 0 else "-") + str(abs(e))
    return sign + s


def _shortest_decimal(x):
    d, n = _digits(abs(x))
    return Decimal(("-" if x < 0 else "") + "0." + d + "E" + str(n)) if x else Decimal(0)


def to_locale(x, max_frac=2, min_frac=0):
    """Number.prototype.toLocaleString('en-US', {maximumFractionDigits}) (ICU: shortest decimal, half away from zero)."""
    if x != x:
        return "NaN"
    if math.isinf(x):
        return "∞" if x > 0 else "-∞"
    neg = x < 0 or (x == 0 and math.copysign(1, x) < 0)
    with localcontext(_WIDE):
        q = abs(_shortest_decimal(x)).quantize(Decimal(1).scaleb(-max_frac), rounding=ROUND_HALF_UP)
    s = format(q, "f")
    ip, _, fp = s.partition(".")
    fp = fp.rstrip("0")
    if len(fp) < min_frac:
        fp = fp + "0" * (min_frac - len(fp))
    ip = f"{int(ip):,}"
    return ("-" if neg else "") + ip + ("." + fp if fp else "")


def to_fixed(x, f):
    """Number.prototype.toFixed (exact binary value, ties away from zero)."""
    if not math.isfinite(x):
        return num_str(x)
    if abs(x) >= 1e21:
        return num_str(x)
    with localcontext(_WIDE):
        q = Decimal(abs(x)).quantize(Decimal(1).scaleb(-f), rounding=ROUND_HALF_UP)
    s = format(q, "f")
    return ("-" if x < 0 else "") + s   # (-0.001).toFixed(2) is "-0.00"


def fmt(n):
    """The app's fmt: up to 2 decimals, '–' for anything not finite."""
    return to_locale(n, 2) if finite(n) else "–"


def fmt_cost(v):
    """The app's fmtCost."""
    return "–" if v is None else to_locale(v, 2 if abs(v) < 100 else 0)


def add(xs, start=0):
    """xs.reduce((a, b) => a + b, start): plain left-to-right addition (Python 3.12's sum() compensates
    float rounding, which JavaScript does not)."""
    a = start
    for x in xs:
        a = a + x
    return a


def mean(xs):
    return add(xs) / len(xs) if xs else None


def median(xs):
    a = sorted(x for x in xs if finite(x))
    if not a:
        return None
    m = len(a) >> 1
    return a[m] if len(a) % 2 else (a[m - 1] + a[m]) / 2


# ---- objects, arrays and sorting -------------------------------------------------------------
def truthy(v):
    if v is None or v is False:
        return False
    if is_num(v):
        return v == v and v != 0
    if isinstance(v, str):
        return v != ""
    return True   # objects and arrays, empty or not


def _index_key(k):
    if isinstance(k, str) and re.fullmatch(r"0|[1-9][0-9]*", k) and int(k) < 2**32 - 1:
        return int(k)
    return None


def keys(d):
    """Object.keys order: array-index keys ascending, then the other keys in insertion order."""
    idx = sorted((_index_key(k), k) for k in d if _index_key(k) is not None)
    return [k for _, k in idx] + [k for k in d if _index_key(k) is None]


def values(d):
    return [d[k] for k in keys(d)]


def entries(d):
    return [(k, d[k]) for k in keys(d)]


def unique(xs):
    """[...new Set(xs)]"""
    return list(dict.fromkeys(xs))


def sort(xs, cmp):
    """Array.prototype.sort with a comparator (stable, like V8's TimSort; NaN counts as 0)."""
    def c(a, b):
        v = cmp(a, b)
        v = float(v)
        return -1 if v < 0 else 1 if v > 0 else 0
    return sorted(xs, key=functools.cmp_to_key(c))


def reduce_max(xs, better):
    """xs.reduce((a, b) => better(b, a) ? b : a) — the first element kept on ties."""
    best = xs[0]
    for b in xs[1:]:
        if better(b, best):
            best = b
    return best


# ICU root collation, enough for the drawing numbers, tags, areas and names the app sorts:
# white space < punctuation < symbols < digits < letters (case folded, lower case first on ties) < other scripts.
_ICU_PUNCT = "_-,;:!?.'\"()[]{}@*/\\&#%`^+<=>|~$"


def _collate_key(s):
    prim, tert = [], []
    for ch in s:
        o = ord(ch)
        if ch in _SPACE_CHARS:
            prim.append((0, o))
        elif ch in _ICU_PUNCT:
            prim.append((1, _ICU_PUNCT.index(ch)))
        elif "0" <= ch <= "9":
            prim.append((3, o))
        elif ch.isascii() and ch.isalpha():
            prim.append((4, ord(ch.lower())))
        elif o < 128:
            prim.append((2, o))
        else:
            prim.append((5, o))
        tert.append(0 if ch.islower() or not ch.isalpha() else 1)
    return prim, tert


def locale_compare(a, b):
    """String.prototype.localeCompare (ICU root order for the characters above)."""
    ka, kb = _collate_key(a), _collate_key(b)
    return -1 if ka < kb else 1 if ka > kb else 0


# ---- JSON ------------------------------------------------------------------------------------
def plain(v):
    """A value as JSON.stringify would keep it: whole floats as ints, NaN/Infinity as null."""
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items() if not callable(x)}
    if isinstance(v, (list, tuple, set)):
        return [plain(x) for x in v]
    if isinstance(v, float):
        if not math.isfinite(v):
            return None
        return int(v) if v.is_integer() and abs(v) < 2**53 else v
    return v
