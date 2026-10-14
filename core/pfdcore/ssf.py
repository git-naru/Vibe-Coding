"""Cell text the way SheetJS 0.18.5 writes it (its SSF formatter), for `sheet_to_json(..., {raw: false})`.

Ported exactly: General, and the plain numeric formats Stream tables use — 0, 0.00, #,##0, #,##0.00 (any number
of decimals), percent, thousands scaling (trailing commas), quoted text, \\x literals, _x padding, [Color] and
two/three-section formats. Anything else (dates, fractions, scientific, conditions) falls back to General and is
reported through `unsupported`, so a caller can tell the text may differ from the app's.
"""
import math
import re
from decimal import ROUND_HALF_UP, Decimal, localcontext

from . import js

TABLE = {0: "General", 1: "0", 2: "0.00", 3: "#,##0", 4: "#,##0.00", 9: "0%", 10: "0.00%", 11: "0.00E+00",
         12: "# ?/?", 13: "# ??/??", 14: "m/d/yy", 15: "d-mmm-yy", 16: "d-mmm", 17: "mmm-yy", 18: "h:mm AM/PM",
         19: "h:mm:ss AM/PM", 20: "h:mm", 21: "h:mm:ss", 22: "m/d/yy h:mm", 37: "#,##0 ;(#,##0)",
         38: "#,##0 ;[Red](#,##0)", 39: "#,##0.00;(#,##0.00)", 40: "#,##0.00;[Red](#,##0.00)", 45: "mm:ss",
         46: "[h]:mm:ss", 47: "mmss.0", 48: "##0.0E+0", 49: "@"}
DEFAULT_MAP = {5: 37, 6: 38, 7: 39, 8: 40, 23: 0, 24: 0, 25: 0, 26: 0, 27: 14, 28: 14, 29: 14, 30: 14, 31: 14,
               50: 14, 51: 14, 52: 14, 53: 14, 54: 14, 55: 14, 56: 14, 57: 14, 58: 14, 59: 1, 60: 2, 61: 3, 62: 4,
               67: 9, 68: 10, 69: 12, 70: 13, 71: 14, 72: 14, 73: 15, 74: 16, 75: 17, 76: 20, 77: 21, 78: 22,
               79: 45, 80: 46, 81: 47, 82: 0}

unsupported = set()   # format codes met that this port does not write exactly


class Unsupported(Exception):
    pass


# ---- JavaScript number → text ----------------------------------------------------------------
def _exact(v):
    return Decimal(v)


def to_precision(v, p):
    """Number.prototype.toPrecision"""
    with localcontext(js._WIDE):
        return _to_precision(v, p)


def _to_precision(v, p):
    if v == 0:
        return "0" + ("." + "0" * (p - 1) if p > 1 else "")
    sign = "-" if v < 0 else ""
    x = abs(_exact(v))
    e = x.adjusted()
    q = x.scaleb(-e).quantize(Decimal(1).scaleb(-(p - 1)), rounding=ROUND_HALF_UP)
    if q >= 10:
        e += 1
        q = x.scaleb(-e).quantize(Decimal(1).scaleb(-(p - 1)), rounding=ROUND_HALF_UP)
    digits = format(q, "f").replace(".", "")
    if e < -6 or e >= p:
        m = digits[0] + ("." + digits[1:] if p > 1 else "")
        return sign + m + "e" + ("+" if e >= 0 else "-") + str(abs(e))
    if e >= 0:
        return sign + digits[: e + 1] + ("." + digits[e + 1:] if p > e + 1 else "")
    return sign + "0." + "0" * (-e - 1) + digits


def to_exponential(v, f):
    """Number.prototype.toExponential"""
    with localcontext(js._WIDE):
        return _to_exponential(v, f)


def _to_exponential(v, f):
    sign = "-" if v < 0 else ""
    if v == 0:
        return "0" + ("." + "0" * f if f else "") + "e+0"
    x = abs(_exact(v))
    e = x.adjusted()
    q = x.scaleb(-e).quantize(Decimal(1).scaleb(-f), rounding=ROUND_HALF_UP)
    if q >= 10:
        e += 1
        q = x.scaleb(-e).quantize(Decimal(1).scaleb(-f), rounding=ROUND_HALF_UP)
    return sign + format(q, "f") + "e" + ("+" if e >= 0 else "-") + str(abs(e))


def _is_int32(v):
    return js.is_num(v) and math.isfinite(v) and float(v).is_integer() and -2**31 <= v < 2**31


# ---- General -----------------------------------------------------------------------------------
def _strip_decimal(o):
    return o if "." not in o else js.sub(r"(?:\.0*|(\.\d*[1-9])0+)$", lambda m: m.group(1) or "", o, count=1)


def _normalize_exp(o):
    if "E" not in o:
        return o
    o = js.sub(r"(?:\.0*|(\.\d*[1-9])0+)[Ee]", lambda m: (m.group(1) or "") + "E", o, count=1)
    return js.sub(r"(E[+-])(\d)$", lambda m: m.group(1) + "0" + m.group(2), o, count=1)


def _small_exp(v):
    w = 12 if v < 0 else 11
    o = _strip_decimal(js.to_fixed(v, 12))
    if len(o) <= w:
        return o
    o = to_precision(v, 10)
    if len(o) <= w:
        return o
    return to_exponential(v, 5)


def _large_exp(v):
    o = _strip_decimal(js.to_fixed(v, 11))
    return to_precision(v, 6) if (len(o) > (12 if v < 0 else 11) or o in ("0", "-0")) else o


def general_num(v):
    V = math.floor(math.log(abs(v)) * (1 / math.log(10))) if v else -math.inf
    if -4 <= V <= -1:
        o = to_precision(v, int(10 + V))
    elif abs(V) <= 9:
        o = _small_exp(v)
    elif V == 10:
        o = js.to_fixed(v, 10)[:12]
    else:
        o = _large_exp(v)
    return _strip_decimal(_normalize_exp(o.upper()))


def general(v):
    if isinstance(v, str):
        return v
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if v is None:
        return ""
    if _is_int32(v):
        return js.num_str(v)
    return general_num(v)


# ---- explicit numeric formats ------------------------------------------------------------------
def _commaify(s):
    w = 3
    if len(s) <= w:
        return s
    j = len(s) % w
    o = s[:j]
    while j != len(s):
        o += ("," if o else "") + s[j:j + w]
        j += w
    return o


def _pad0(v, d):
    t = js.num_str(v) if js.is_num(v) else str(v)
    return t if len(t) >= d else "0" * (d - len(t)) + t


def _pad0r(v, d):
    t = js.num_str(js.js_round(v))
    return t if len(t) >= d else "0" * (d - len(t)) + t


def _hashq(s):
    return "".join("" if c == "#" else " " if c == "?" else c for c in s)


def _rnd(v, d):
    dd = 10 ** d
    return js.num_str(js.js_round(v * dd) / dd)


def _dec(v, d):
    frac, dd = v - math.floor(v), 10 ** d
    if d < len(js.num_str(js.js_round(frac * dd))):
        return 0
    return js.js_round(frac * dd)


def _carry(v, d):
    return 1 if d < len(js.num_str(js.js_round((v - math.floor(v)) * 10 ** d))) else 0


def _write_num(fmt, v):
    return _write_int(fmt, v) if _is_int32(v) else _write_flt(fmt, v)


def _write_pct(fmt, v, writer):
    sfmt = fmt.replace("%", "")
    mul = len(fmt) - len(sfmt)
    return writer(sfmt, v * 10 ** (2 * mul)) + "%" * mul


def _write_cm(fmt, v):
    idx = len(fmt) - 1
    while idx > 0 and fmt[idx - 1] == ",":
        idx -= 1
    return _write_num(fmt[:idx], v / 10 ** (3 * (len(fmt) - idx)))


def _write_int(fmt, v):
    if fmt.endswith(","):
        return _write_cm(fmt, v)
    if "%" in fmt:
        return _write_pct(fmt, v, _write_num)
    if "E" in fmt or "/" in fmt or fmt.startswith("$") or fmt.startswith("("):
        raise Unsupported(fmt)
    aval, sign = abs(v), "-" if v < 0 else ""
    if re.fullmatch(r"00+", fmt):
        return sign + _pad0(js.num_str(aval), len(fmt))
    if re.fullmatch(r"[#?]+", fmt):
        o = "" if v == 0 else js.num_str(v)
        return o if len(o) > len(fmt) else _hashq(fmt[: len(fmt) - len(o)]) + o
    if re.fullmatch(r"#+0+", fmt):
        return sign + _pad0(js.num_str(aval), len(fmt) - fmt.index("0"))
    r = re.match(r"#*0*\.([0#]+)", fmt)
    if r:
        h = _hashq(r.group(1))
        o = js.num_str(v)
        o = re.sub(r"^([^.]+)$", lambda m: m.group(1) + "." + h, o)
        o = re.sub(r"\.$", "." + h, o)
        o = re.sub(r"\.(\d*)$", lambda m: "." + m.group(1) + "0" * (len(h) - len(m.group(1))), o)
        return o if "0." in fmt else re.sub(r"^0\.", ".", o)
    fmt = re.sub(r"^#+([0.])", r"\1", fmt)
    r = re.fullmatch(r"(0*)\.(#*)", fmt)
    if r:
        o = js.num_str(aval)
        o = re.sub(r"\.(\d*[1-9])0*$", r".\1", o)
        o = re.sub(r"^(-?\d*)$", r"\1.", o)
        return sign + re.sub(r"^0\.", "0." if r.group(1) else ".", o)
    if re.fullmatch(r"#{1,3},##0(\.?)", fmt):
        return sign + _commaify(js.num_str(aval))
    r = re.fullmatch(r"#,##0\.([#0]*0)", fmt)
    if r:
        return "-" + _write_int(fmt, -v) if v < 0 else _commaify(js.num_str(v)) + "." + "0" * len(r.group(1))
    if re.match(r"#,#*,#0", fmt):
        return _write_int(re.sub(r"^#,#*,", "", fmt, count=1), v)
    if re.fullmatch(r"[#0?]+", fmt):
        o = js.num_str(v)
        return o if len(fmt) <= len(o) else _hashq(fmt[: len(fmt) - len(o)]) + o
    if fmt in ("###,###", "##,###", "#,###"):
        x = _commaify(js.num_str(aval))
        return sign + x if x != "0" else ""
    raise Unsupported(fmt)


def _write_flt(fmt, v):
    if fmt.endswith(","):
        return _write_cm(fmt, v)
    if "%" in fmt:
        return _write_pct(fmt, v, _write_num)
    if "E" in fmt or "/" in fmt or fmt.startswith("$") or fmt.startswith("("):
        raise Unsupported(fmt)
    aval, sign = abs(v), "-" if v < 0 else ""
    if re.fullmatch(r"00+", fmt):
        return sign + _pad0r(aval, len(fmt))
    if re.fullmatch(r"[#?]+", fmt):
        o = _pad0r(v, 0)
        if o == "0":
            o = ""
        return o if len(o) > len(fmt) else _hashq(fmt[: len(fmt) - len(o)]) + o
    if re.fullmatch(r"#+0+", fmt):
        return sign + _pad0r(aval, len(fmt) - fmt.index("0"))
    r = re.match(r"#*0*\.([0#]+)", fmt)
    if r:
        h = _hashq(r.group(1))
        o = _rnd(v, len(r.group(1)))
        o = re.sub(r"^([^.]+)$", lambda m: m.group(1) + "." + h, o)
        o = re.sub(r"\.$", "." + h, o)
        o = re.sub(r"\.(\d*)$", lambda m: "." + m.group(1) + "0" * (len(h) - len(m.group(1))), o)
        return o if "0." in fmt else re.sub(r"^0\.", ".", o)
    fmt = re.sub(r"^#+([0.])", r"\1", fmt)
    r = re.fullmatch(r"(0*)\.(#*)", fmt)
    if r:
        o = _rnd(aval, len(r.group(2)))
        o = re.sub(r"\.(\d*[1-9])0*$", r".\1", o)
        o = re.sub(r"^(-?\d*)$", r"\1.", o)
        return sign + re.sub(r"^0\.", "0." if r.group(1) else ".", o)
    if re.fullmatch(r"#{1,3},##0(\.?)", fmt):
        return sign + _commaify(_pad0r(aval, 0))
    r = re.fullmatch(r"#,##0\.([#0]*0)", fmt)
    if r:
        d = len(r.group(1))
        if v < 0:
            return "-" + _write_flt(fmt, -v)
        return _commaify(js.num_str(float(math.floor(v)) + _carry(v, d))) + "." + _pad0(_dec(v, d), d)
    if re.match(r"#,#*,#0", fmt):
        return _write_flt(re.sub(r"^#,#*,", "", fmt, count=1), v)
    if re.fullmatch(r"[#0?]+", fmt):
        o = _pad0r(v, 0)
        return o if len(fmt) <= len(o) else _hashq(fmt[: len(fmt) - len(o)]) + o
    if fmt == "###,##0.00":
        return _write_flt("#,##0.00", v)
    if fmt in ("###,###", "##,###", "#,###"):
        x = _commaify(_pad0r(aval, 0))
        return sign + x if x != "0" else ""
    raise Unsupported(fmt)


def _split(fmt):
    out, in_str, i, j = [], False, 0, 0
    while i < len(fmt):
        c = fmt[i]
        if c == '"':
            in_str = not in_str
        elif c in "_*\\":
            i += 1
        elif c == ";":
            out.append(fmt[j:i])
            j = i + 1
        i += 1
    out.append(fmt[j:])
    return out


def _choose(f, v):
    parts = _split(f)
    n, lat = len(parts), parts[-1].find("@")
    if n < 4 and lat > -1:
        n -= 1
    if len(parts) > 4:
        raise Unsupported(f)
    if not js.is_num(v):
        return 4, parts[-1] if len(parts) == 4 or lat > -1 else "@"
    if len(parts) == 1:
        parts = ["General", "General", "General", parts[0]] if lat > -1 else [parts[0], parts[0], parts[0], "@"]
    elif len(parts) == 2:
        parts = [parts[0], parts[0], parts[0], parts[1]] if lat > -1 else [parts[0], parts[1], parts[0], "@"]
    elif len(parts) == 3:
        parts = [parts[0], parts[1], parts[0], parts[2]] if lat > -1 else [parts[0], parts[1], parts[2], "@"]
    if re.search(r"\[[=<>]", parts[0]) or re.search(r"\[[=<>]", parts[1]):
        raise Unsupported(f)
    return n, parts[0] if v > 0 else parts[1] if v < 0 else parts[2]


def _is_general(s, i=0):
    return s[i:i + 7].lower() == "general"


def _eval(fmt, v, flen):
    """eval_fmt for formats without date, fraction or scientific parts."""
    out, i = [], 0
    while i < len(fmt):
        c = fmt[i]
        if c == "G":
            if not _is_general(fmt, i):
                raise Unsupported(fmt)
            out.append(["G", "General"])
            i += 7
        elif c == '"':
            o = ""
            i += 1
            while i < len(fmt) and fmt[i] != '"':
                o += fmt[i]
                i += 1
            out.append(["t", o])
            i += 1
        elif c == "\\":
            w = fmt[i + 1] if i + 1 < len(fmt) else ""
            out.append([w if w in "()" else "t", w])
            i += 2
        elif c == "_":
            out.append(["t", " "])
            i += 2
        elif c == "@":
            out.append(["T", v])
            i += 1
        elif c in "BbMDYHSEmdyhseg" or c in "Aa上":
            raise Unsupported(fmt)   # dates and times
        elif c == "[":
            o = c
            i += 1
            while i < len(fmt) and fmt[i - 1] != "]":
                o += fmt[i]
                i += 1
            if not o.endswith("]"):
                raise Unsupported(fmt)
            if re.search(r"\[[HhMmSs]*\]", o):
                raise Unsupported(fmt)
            if "$" in o:
                m = re.search(r"\$([^-\[\]]*)", o)
                out.append(["t", (m.group(1) if m else "") or "$"])
        elif c in ".0#":
            o = c
            i += 1
            while i < len(fmt) and fmt[i] in "0#?.,E+-%":
                o += fmt[i]
                i += 1
            out.append(["n", o])
        elif c == "?":
            raise Unsupported(fmt)
        elif c == "*":
            i += 1
            if i < len(fmt) and fmt[i] in " *":
                i += 1
        elif c in "()":
            out.append(["t" if flen == 1 else c, c])
            i += 1
        elif c in "123456789":
            raise Unsupported(fmt)
        elif c == " ":
            out.append([" ", " "])
            i += 1
        elif c == "$":
            out.append(["t", "$"])
            i += 1
        elif c in ",$-+/():!^&'~{}<>=€acfijklopqrtuvwxzP":
            out.append(["t", c])
            i += 1
        else:
            raise Unsupported(fmt)
    nstr = ""
    k = 0
    while k < len(out):
        t = out[k][0]
        if t == "n":
            jj = k + 1
            while jj < len(out) and (out[jj][0] == "D" or (out[jj][0] in (" ", "t") and jj + 1 < len(out) and out[jj + 1][0] == "t" and out[jj + 1][1] == "/")
                                     or (out[jj][0] == "t" and out[jj][1] == "/")):
                out[k][1] += out[jj][1]
                out[jj] = [";", ""]
                jj += 1
            nstr += out[k][1]
            k = jj
            continue
        if t == "G":
            out[k] = ["t", general(v)]
        k += 1
    if nstr:
        if "E" in nstr or "/" in nstr:
            raise Unsupported(fmt)
        if nstr[0] == "(":
            raise Unsupported(fmt)
        myv = -v if (v < 0 and flen > 1) else v
        ostr = _write_num(nstr, myv)
        if myv < 0 and out and out[0][0] == "t":
            ostr = ostr[1:]
            out[0][1] = "-" + out[0][1]
        jj = len(ostr) - 1
        decpt = len(out)
        for k, o in enumerate(out):
            if o[0] != "t" and isinstance(o[1], str) and "." in o[1]:
                decpt = k
                break
        lasti = len(out)
        if decpt == len(out):
            for k in range(len(out) - 1, -1, -1):
                if out[k][0] not in ("n", "?"):
                    continue
                L = len(out[k][1])
                if jj >= L - 1:
                    jj -= L
                    out[k][1] = ostr[jj + 1: jj + 1 + L]
                elif jj < 0:
                    out[k][1] = ""
                else:
                    out[k][1] = ostr[: jj + 1]
                    jj = -1
                out[k][0] = "t"
                lasti = k
            if jj >= 0 and lasti < len(out):
                out[lasti][1] = ostr[: jj + 1] + out[lasti][1]
        else:
            jj = ostr.find(".") - 1
            for k in range(decpt, -1, -1):
                if out[k][0] not in ("n", "?"):
                    continue
                s = out[k][1]
                j = s.find(".") - 1 if ("." in s and k == decpt) else len(s) - 1
                vv = s[j + 1:]
                while j >= 0:
                    if jj >= 0 and s[j] in "0#":
                        vv = ostr[jj] + vv
                        jj -= 1
                    j -= 1
                out[k] = ["t", vv]
                lasti = k
            if jj >= 0 and lasti < len(out):
                out[lasti][1] = ostr[: jj + 1] + out[lasti][1]
            jj = ostr.find(".") + 1
            for k in range(decpt, len(out)):
                if out[k][0] not in ("n", "?", "(") and k != decpt:
                    continue
                s = out[k][1]
                j = s.find(".") + 1 if ("." in s and k == decpt) else 0
                vv = s[:j]
                while j < len(s):
                    if jj < len(ostr):
                        vv += ostr[jj]
                        jj += 1
                    j += 1
                out[k] = ["t", vv]
                lasti = k
    return "".join(str(o[1]) for o in out)


def format_code(numfmt_id, custom):
    """The format code SheetJS uses for a cell's numFmtId (custom codes from styles.xml first)."""
    if numfmt_id in custom:
        return custom[numfmt_id]
    f = TABLE.get(numfmt_id)
    if f is None:
        f = TABLE.get(DEFAULT_MAP.get(numfmt_id, -1))
    return f or "General"


def is_date(fmt):
    s = re.sub(r'"[^"]*"|\\.|_.|\[[^\]]*\]', "", fmt)
    return bool(re.search(r"[ymdhsYMDHSeE]|AM/PM|A/P", s.replace("General", "").replace("E+", "").replace("E-", "")))


def cell_text(v, fmt):
    """The `w` text SheetJS keeps for a cell value under a format code."""
    if v is None:
        return ""
    if _is_general(fmt):
        return general(v)
    try:
        n, f = _choose(fmt, v)
        if _is_general(f):
            return general(v)
        if v is True:
            v = "TRUE"
        elif v is False:
            v = "FALSE"
        elif v == "":
            return ""
        if isinstance(v, str):
            if f == "@" or "@" in f:
                return re.sub(r'"([^"]*)"', r"\1", f).replace("@", v) if f != "@" else v
            return v
        return _eval(f, v, n)
    except (Unsupported, IndexError, ValueError):
        unsupported.add(fmt)
        return general(v)
