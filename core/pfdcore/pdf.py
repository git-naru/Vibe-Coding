"""PDF sheets read the way the app reads them with pdf.js 3.11.174 (app.html section 3, `readPdf`).

The Equipment List and sheet links depend on how the page text is cut into items, so this module replays the
page's content stream with pdf.js's own text-item rules (evaluator `getTextContent`: glyph-by-glyph position
compare, fake spaces, new items on large gaps or line moves, a text state copied on q, Form XObjects as
separate runs) and pdf.js's page viewport. pdfminer.six parses the file, the content streams and the fonts
(byte → character code → Unicode); glyph widths follow pdf.js (font /Widths, /W, /DW, /MissingWidth).

Not reproduced (reported in `Sheet['warnings']`): vertical writing, right-to-left text, annotation
appearance streams, and pdf.js's merging of many small repeated images. Fonts pdf.js cannot load without its
CMap files are dropped as the app drops them (warning "cmap-font"; see `read_pdf(cmap_fonts=...)`). When they
are read instead, their CID → Unicode tables are pdfminer's, which can differ from pdf.js's for rare CIDs.
"""
import math
import unicodedata
from io import BytesIO

from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdffont import PDFCIDFont, PDFType3Font, PDFUnicodeNotDefined
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfdevice import PDFDevice
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.pdftypes import PDFObjRef, PDFStream, dict_value, list_value, resolve1, stream_value
from pdfminer.psparser import PSLiteral, literal_name

from . import js
from .equipment import extract_equipment, sheet_area, sheet_grid
from .layout import lay_title
from .sheets import connectors_of, is_badge, sheet_identity
from .streams import parse_text_table

IDENTITY = [1, 0, 0, 1, 0, 0]
FONT_IDENTITY = [0.001, 0, 0, 0.001, 0, 0]
LETTER = [0, 0, 612, 792]
TRACKING_SPACE_FACTOR = 0.102
NOT_A_SPACE_FACTOR = 0.03
NEGATIVE_SPACE_FACTOR = -0.2
SPACE_IN_FLOW_MIN_FACTOR = 0.102
SPACE_IN_FLOW_MAX_FACTOR = 0.6
VERTICAL_SHIFT_RATIO = 0.25


# ---- pdf.js Util -------------------------------------------------------------------------------
def transform(m1, m2):
    return [m1[0] * m2[0] + m1[2] * m2[1], m1[1] * m2[0] + m1[3] * m2[1], m1[0] * m2[2] + m1[2] * m2[3],
            m1[1] * m2[2] + m1[3] * m2[3], m1[0] * m2[4] + m1[2] * m2[5] + m1[4], m1[1] * m2[4] + m1[3] * m2[5] + m1[5]]


def apply(p, m):
    return [p[0] * m[0] + p[1] * m[2] + m[4], p[0] * m[1] + p[1] * m[3] + m[5]]


def normalize_rect(r):
    return [min(r[0], r[2]), min(r[1], r[3]), max(r[0], r[2]), max(r[1], r[3])]


def intersect(a, b):
    xlo, xhi = max(min(a[0], a[2]), min(b[0], b[2])), min(max(a[0], a[2]), max(b[0], b[2]))
    if xlo > xhi:
        return None
    ylo, yhi = max(min(a[1], a[3]), min(b[1], b[3])), min(max(a[1], a[3]), max(b[1], b[3]))
    if ylo > yhi:
        return None
    return [xlo, ylo, xhi, yhi]


def viewport(view, rotation, scale=1):
    """PageViewport.transform, width, height."""
    cx, cy = (view[2] + view[0]) / 2, (view[3] + view[1]) / 2
    rotation %= 360
    a, b, c, d = {180: (-1, 0, 0, 1), 90: (0, 1, 1, 0), 270: (0, -1, -1, 0), 0: (1, 0, 0, -1)}[rotation]
    if a == 0:
        ox, oy = abs(cy - view[1]) * scale, abs(cx - view[0]) * scale
        w, h = (view[3] - view[1]) * scale, (view[2] - view[0]) * scale
    else:
        ox, oy = abs(cx - view[0]) * scale, abs(cy - view[1]) * scale
        w, h = (view[2] - view[0]) * scale, (view[3] - view[1]) * scale
    t = [a * scale, b * scale, c * scale, d * scale, ox - a * scale * cx - c * scale * cy, oy - b * scale * cx - d * scale * cy]
    return t, w, h


# ---- unicode (pdf.js normalizeUnicode, getCharUnicodeCategory) --------------------------------
_NORM = js.rx("([ µ;ຳ -  Ωﬀ-ﬄﬆﬠ-זּטּ-לּמּנּ-סּףּ-פּצּ-ﮡ"
              "ﮤ-ﮩﮮ-ﮱﯓ-ﯜﯞ-ﯧﯪ-ﯸﯼ-ﯽﰀ-ﱝﱤ-ﳱﳵ-ﴽﶈﷴ"
              "ﷺ-ﷻﹱﹷﹹﹻﹽ]+)|(ﬅ+)")


def normalize_unicode(s):
    return _NORM.sub(lambda m: unicodedata.normalize("NFKC", m.group(1)) if m.group(1) else ("ſt" if len(m.group(2)) == 1 else "undefined"), s)


def category(u):
    """/^(\\s)|(\\p{Mn})|(\\p{Cf})$/u → (white space, zero-width diacritic, invisible format mark).
    The first match decides: white space only as the first character, a combining mark anywhere,
    a format mark only as the last character."""
    for i, c in enumerate(u):
        if i == 0 and c in js._SPACE_CHARS:
            return True, False, False
        cat = unicodedata.category(c)
        if cat == "Mn":
            return False, True, False
        if i == len(u) - 1 and cat == "Cf":
            return False, False, True
    return False, False, False


_RTL = js.rx("[֐-ࣿיִ-﷿ﹰ-﻿]")


# ---- fonts ---------------------------------------------------------------------------------------
CMAP_ORDERINGS = ("GB1", "CNS1", "Japan1", "Korea1")


def needs_cmap_files(spec):
    """True when pdf.js can only load this font with its CMap files (`cMapUrl`), which the app does not give it:
    a Type0 font whose encoding is a predefined CMap other than Identity-H/V (or an embedded CMap that uses one),
    or one without /ToUnicode whose CIDs are Adobe-GB1/CNS1/Japan1/Korea1."""
    if not (isinstance(spec.get("Subtype"), PSLiteral) and literal_name(spec["Subtype"]) == "Type0"):
        return False
    enc = resolve1(spec.get("Encoding"))
    if isinstance(enc, PSLiteral) and literal_name(enc) not in ("Identity-H", "Identity-V"):
        return True
    if isinstance(enc, PDFStream):
        if enc.get("UseCMap") is not None or b"usecmap" in (enc.get_data() or b""):
            return True
    tu = resolve1(spec.get("ToUnicode"))
    has_tu = isinstance(tu, PDFStream) and len(tu.get_data() or b"") > 0
    if not has_tu:
        dfs = list_value(resolve1(spec.get("DescendantFonts")) or [])
        csi = dict_value(resolve1(dict_value(resolve1(dfs[0])).get("CIDSystemInfo")) or {}) if dfs else {}
        reg, order = resolve1(csi.get("Registry")), resolve1(csi.get("Ordering"))
        dec = lambda b: b.decode("latin-1") if isinstance(b, bytes) else js.jstr(b)
        if dec(reg) == "Adobe" and dec(order) in CMAP_ORDERINGS:
            return True
    return False


class ErrorFont:
    """pdf.js ErrorFont: a font that failed to load draws nothing and does not move the text position."""
    type3 = composite = vertical = False
    matrix = FONT_IDENTITY
    bbox = None

    def glyphs(self, chars):
        return []


class Font:
    """What pdf.js uses of a font: glyph widths (pdf.js rules), font matrix, and code → Unicode (pdfminer)."""

    def __init__(self, rsrcmgr, objid, spec):
        self.pm = rsrcmgr.get_font(objid, spec)
        self.type3 = isinstance(self.pm, PDFType3Font)
        self.composite = isinstance(self.pm, PDFCIDFont)
        self.vertical = bool(self.composite and self.pm.is_vertical())
        self.matrix = [float(x) for x in list_value(spec.get("FontMatrix"))] if self.type3 else FONT_IDENTITY
        bbox = list_value(resolve1(spec.get("FontBBox"))) if self.type3 else []
        self.bbox = [float(resolve1(x)) for x in bbox] if len(bbox) == 4 else None
        self.widths, self.default = {}, 0
        if self.composite:
            dfs = list_value(resolve1(spec.get("DescendantFonts")) or [])
            cid = dict_value(resolve1(dfs[0])) if dfs else {}
            dw = resolve1(cid.get("DW"))
            self.default = dw if dw is not None else 1000
            w = list_value(resolve1(cid.get("W") or []))
            i = 0
            while i < len(w):
                start = resolve1(w[i])
                i += 1
                code = resolve1(w[i]) if i < len(w) else None
                if isinstance(code, list):
                    for x in code:
                        self.widths[start] = resolve1(x)
                        start += 1
                else:
                    i += 1
                    width = resolve1(w[i]) if i < len(w) else None
                    for j in range(start, (code or 0) + 1):
                        self.widths[j] = width
                i += 1
        elif spec.get("Widths") is not None:
            first = resolve1(spec.get("FirstChar")) or 0
            for k, x in enumerate(list_value(resolve1(spec.get("Widths")))):
                self.widths[first + k] = resolve1(x)
            desc = dict_value(resolve1(spec.get("FontDescriptor")) or {})
            mw = js.parse_float(js.jstr(resolve1(desc.get("MissingWidth"))) if desc.get("MissingWidth") is not None else "")
            self.default = mw if js.truthy(mw) else 0
        else:   # no /Widths: standard-font metrics (pdfminer's AFM tables), as pdf.js getBaseFontMetrics
            self.std = True
            self.default = self.pm.default_width
            base = literal_name(spec.get("BaseFont")) if isinstance(spec.get("BaseFont"), PSLiteral) else ""
            if not self.pm.widths or not any(self.pm.widths.values()):
                self.std_metrics(base)

    def std_metrics(self, base):
        from pdfminer.fontmetrics import FONT_METRICS
        n = base.split("+")[-1].replace(" ", "").replace(",", "-")
        bold, italic = "Bold" in n, "Italic" in n or "Oblique" in n
        fam = "Courier" if "Courier" in n else "Times" if js.test("Times|Serif|Georgia|Garamond|Cambria|Batang|Myungjo", n) else "Helvetica"
        if fam == "Times":
            name = "Times-" + ("BoldItalic" if bold and italic else "Bold" if bold else "Italic" if italic else "Roman")
        else:
            name = fam + ("-BoldOblique" if bold and italic else "-Bold" if bold else "-Oblique" if italic else "")
        desc, widths = FONT_METRICS.get(name, FONT_METRICS["Helvetica"])
        self.pm.widths = dict(widths)
        self.default = desc.get("MissingWidth", 0) if isinstance(desc, dict) else 0

    def codes(self, chars):
        """Character codes of a string. Identity-H/V follow pdf.js readCharCode: 2-byte codes, and a lone
        last byte reads as that byte × 256 (the missing byte counts as 0)."""
        enc = getattr(self.pm, "cmap", None)
        if self.composite and type(enc).__name__ == "IdentityCMap":
            return [(chars[i] << 8) | (chars[i + 1] if i + 1 < len(chars) else 0) for i in range(0, len(chars), 2)]
        return list(self.pm.decode(chars))

    def glyphs(self, chars):
        """[(unicode, width in glyph units)] for a string's bytes."""
        out = []
        for cid in self.codes(chars):
            if getattr(self, "std", False):
                w = self.pm.widths.get(cid)
                if w is None:
                    try:
                        w = self.pm.widths.get(self.pm.to_unichr(cid))
                    except PDFUnicodeNotDefined:
                        w = None
            else:
                w = self.widths.get(cid)
            if not js.is_num(w):
                w = self.default
            try:
                u = self.pm.to_unichr(cid)
            except (PDFUnicodeNotDefined, KeyError, IndexError):
                u = ""
            if not u:
                u = chr(cid) if 0 <= cid <= 0xFFFF else ""
            out.append((u, w))
        return out


# ---- text state (pdf.js TextState; q copies all of it) -----------------------------------------
class TextState:
    def __init__(self):
        self.ctm = list(IDENTITY)
        self.font_name = None
        self.font_size = 0
        self.font = None
        self.font_matrix = FONT_IDENTITY
        self.tm = list(IDENTITY)
        self.tlm = list(IDENTITY)
        self.char_spacing = 0
        self.word_spacing = 0
        self.leading = 0
        self.h_scale = 1
        self.rise = 0

    def clone(self):
        c = TextState()
        c.__dict__.update(self.__dict__)
        c.tm, c.tlm, c.font_matrix = list(self.tm), list(self.tlm), list(self.font_matrix)
        return c

    def translate_tm(self, x, y):
        m = self.tm
        m[4] = m[0] * x + m[2] * y + m[4]
        m[5] = m[1] * x + m[3] * y + m[5]

    def translate_tlm(self, x, y):
        m = self.tlm
        m[4] = m[0] * x + m[2] * y + m[4]
        m[5] = m[1] * x + m[3] * y + m[5]

    def carriage_return(self):
        self.translate_tlm(0, -self.leading)
        self.tm = list(self.tlm)


def _num(v):
    v = resolve1(v)
    return v if js.is_num(v) else 0


class _Item:
    """pdf.js textContentItem: one object reused for the whole run (its last position outlives a flush)."""

    def __init__(self):
        self.initialized = False
        self.str = []
        self.total_width = self.total_height = self.width = self.height = 0
        self.prev = None
        self.adv_scale = 0
        self.space_min = self.space_max = 0
        self.tracking_min = math.inf
        self.negative_max = -math.inf
        self.not_a_space = -math.inf
        self.transform = None
        self.has_eol = False


class _Run:
    """One getTextContent call (the page, or a Form XObject): its own item and last-two-characters memory."""

    def __init__(self, out, view):
        self.out, self.view = out, view
        self.item = _Item()
        self.two = [" ", " "]
        self.pos = 0

    def save_last(self, ch):
        nxt = (self.pos + 1) % 2
        ret = self.two[self.pos] != " " and self.two[nxt] == " "
        self.two[self.pos] = ch
        self.pos = nxt
        return ret

    def should_add_ws(self):
        return self.two[self.pos] != " " and self.two[(self.pos + 1) % 2] == " "

    def reset_last(self):
        self.two = [" ", " "]
        self.pos = 0


class _Interp(PDFPageInterpreter):
    def __init__(self, rsrcmgr, reader, run, ts):
        super().__init__(rsrcmgr, PDFDevice(rsrcmgr))
        self.reader, self.run, self.ts, self.stack = reader, run, ts, []

    def dup(self):
        raise RuntimeError("forms are run by _Interp.do_Do")

    def init_resources(self, resources):
        """Only what text and images need; fonts load when first set (pdfminer would build them all up front)."""
        self.resources = resources or {}
        self.fontmap, self.xobjmap, self.csmap = {}, {}, {}
        self.font_specs = {}
        try:
            fonts = dict_value(self.resources.get("Font")) if self.resources.get("Font") else {}
            self.font_specs = dict(fonts.items())
        except Exception:
            pass
        try:
            xo = dict_value(self.resources.get("XObject")) if self.resources.get("XObject") else {}
            self.xobjmap = dict(xo.items())
        except Exception:
            pass

    def init_state(self, ctm):
        super().init_state(ctm)

    # paths, colours and clipping do not change text items or image boxes. pdfminer pops an operator's operands
    # by the handler's argument count; these take none and drop the operands themselves (else the operand stack
    # grows with every path operator and each later pop copies it)
    def _skip(self):
        self.argstack = []
    do_w = do_J = do_j = do_M = do_d = do_ri = do_i = _skip
    do_m = do_l = do_c = do_v = do_y = do_re = do_h = _skip
    do_S = do_s = do_f = do_F = do_f_a = do_B = do_B_a = do_b = do_b_a = do_n = do_W = do_W_a = _skip
    do_CS = do_cs = do_SC = do_sc = do_SCN = do_scn = do_G = do_g = do_RG = do_rg = do_K = do_k = _skip
    do_sh = do_MP = do_DP = do_BX = do_EX = do_d0 = do_d1 = _skip

    # -- state ----------------------------------------------------------------------------------
    def current(self):
        ts = self.ts
        tsm = [ts.font_size * ts.h_scale, 0, 0, ts.font_size, 0, ts.rise]
        f = ts.font
        if f and f.type3 and ts.font_size <= 1 and ts.font_matrix != FONT_IDENTITY and f.bbox:
            gh = f.bbox[3] - f.bbox[1]
            if gh > 0:
                tsm[3] *= gh * ts.font_matrix[3]
        return transform(ts.ctm, transform(ts.tm, tsm))

    def do_q(self):
        self.stack.append(self.ts)
        self.ts = self.ts.clone()
        self.reader.img_stack.append(list(self.reader.img_ctm))

    def do_Q(self):
        r = self.reader
        r.img_ctm = r.img_stack.pop() if r.img_stack else list(IDENTITY)
        prev = self.ts
        if self.stack:
            self.ts = self.stack.pop()
        ts = self.ts
        if prev.font is not ts.font or prev.font_size != ts.font_size or prev.font_name != ts.font_name:
            self.flush()

    def do_cm(self, a, b, c, d, e, f):
        m = [_num(a), _num(b), _num(c), _num(d), _num(e), _num(f)]
        self.ts.ctm = transform(self.ts.ctm, m)
        self.reader.img_ctm = transform(self.reader.img_ctm, m)

    # -- items ----------------------------------------------------------------------------------
    def ensure(self):
        it = self.run.item
        if it.initialized:
            return it
        ts = self.ts
        trm = it.transform = self.current()
        it.width = it.total_width = 0
        it.height = it.total_height = math.hypot(trm[2], trm[3])
        it.adv_scale = math.hypot(ts.tlm[0], ts.tlm[1]) * math.hypot(ts.ctm[0], ts.ctm[1])
        fs = ts.font_size
        it.tracking_min = fs * TRACKING_SPACE_FACTOR
        it.not_a_space = fs * NOT_A_SPACE_FACTOR
        it.negative_max = fs * NEGATIVE_SPACE_FACTOR
        it.space_min = fs * SPACE_IN_FLOW_MIN_FACTOR
        it.space_max = fs * SPACE_IN_FLOW_MAX_FACTOR
        it.has_eol = False
        it.initialized = True
        return it

    def update_adv_scale(self):
        it = self.run.item
        if not it.initialized:
            return
        ts = self.ts
        s = math.hypot(ts.tlm[0], ts.tlm[1]) * math.hypot(ts.ctm[0], ts.ctm[1])
        if s == it.adv_scale:
            return
        it.total_width += it.width * it.adv_scale
        it.width = 0
        it.adv_scale = s

    def flush(self):
        it = self.run.item
        if not it.initialized:
            return
        it.total_width += it.width * it.adv_scale
        text = normalize_unicode("".join(it.str))
        if _RTL.search(text):
            self.reader.warn("rtl")
        self.run.out.append({"str": text, "width": abs(it.total_width), "height": abs(it.total_height), "transform": it.transform})
        it.initialized = False
        it.str = []

    def push_ws(self):
        self.run.out.append({"str": " "})

    def append_eol(self):
        self.run.reset_last()
        it = self.run.item
        if it.initialized:
            it.has_eol = True
            self.flush()

    def compare(self, glyph_width):
        ts, it, run = self.ts, self.run.item, self.run
        cur = self.current()
        px, py = cur[4], cur[5]
        v = run.view
        if px + glyph_width < v[0] or px > v[2] or py < v[1] or py > v[3]:
            return False
        if not ts.font or not it.prev:
            return True
        lx, ly = it.prev[4], it.prev[5]
        if lx == px and ly == py:
            return True
        rot = -1
        if cur[0] and cur[1] == 0 and cur[2] == 0:
            rot = 0 if cur[0] > 0 else 180
        elif cur[1] and cur[0] == 0 and cur[3] == 0:
            rot = 90 if cur[1] > 0 else 270
        if rot == 90:
            px, py, lx, ly = py, px, ly, lx
        elif rot == 180:
            px, py, lx, ly = -px, -py, -lx, -ly
        elif rot == 270:
            px, py, lx, ly = -py, -px, -ly, -lx
        elif rot == -1:
            s1 = math.hypot(cur[0], cur[1])
            px, py = (cur[0] * px + cur[1] * py) / s1, (cur[2] * px + cur[3] * py) / s1
            p = it.prev
            s2 = math.hypot(p[0], p[1])
            lx, ly = (p[0] * lx + p[1] * ly) / s2, (p[2] * lx + p[3] * ly) / s2
        adv_x = (px - lx) / it.adv_scale
        adv_y = py - ly
        orient = (it.width > 0) - (it.width < 0)
        if adv_x < orient * it.negative_max:
            if abs(adv_y) > 0.5 * it.height:
                self.append_eol()
                return True
            run.reset_last()
            self.flush()
            return True
        if abs(adv_y) > it.height:
            self.append_eol()
            return True
        if adv_x <= orient * it.not_a_space:
            run.reset_last()
        if adv_x <= orient * it.tracking_min:
            if run.should_add_ws():
                run.reset_last()
                self.flush()
                self.push_ws()
            else:
                it.width += adv_x
        elif not self.add_fake_spaces_oriented(adv_x, orient):
            if len(it.str) == 0:
                run.reset_last()
                self.push_ws()
            else:
                it.width += adv_x
        if abs(adv_y) > it.height * VERTICAL_SHIFT_RATIO:
            self.flush()
        return True

    def add_fake_spaces_oriented(self, width, orient):
        it = self.run.item
        if orient * it.space_min <= width <= orient * it.space_max:
            if it.initialized:
                self.run.reset_last()
                it.str.append(" ")
            return False
        self.flush()
        self.run.reset_last()
        self.push_ws()
        return True

    def build(self, chars, extra):
        ts = self.ts
        font = ts.font
        if font is None:
            return
        if not chars:
            cs = ts.char_spacing + extra
            if cs:
                ts.translate_tm(cs * ts.h_scale, 0)
            return
        if font.vertical:
            self.reader.warn("vertical")
        glyphs = font.glyphs(chars)
        scale = ts.font_matrix[0] * ts.font_size
        n = len(glyphs)
        for i, (uni, gw) in enumerate(glyphs):
            is_ws, is_mn, is_cf = category(uni)
            if is_cf:
                continue
            cs = ts.char_spacing + (extra if i + 1 == n else 0)
            dim = gw * scale
            if is_ws:
                cs += dim + ts.word_spacing
                ts.translate_tm(cs * ts.h_scale, 0)
                self.run.save_last(" ")
                continue
            if not is_mn and not self.compare(dim):
                ts.translate_tm(dim * ts.h_scale, 0)
                continue
            chunk = self.ensure()
            if is_mn:
                dim = 0
            dim *= ts.h_scale
            ts.translate_tm(dim, 0)
            chunk.width += dim
            if dim:
                chunk.prev = self.current()
            if self.run.save_last(uni):
                chunk.str.append(" ")
            chunk.str.append(uni)
            if cs:
                ts.translate_tm(cs * ts.h_scale, 0)

    # -- text operators ---------------------------------------------------------------------
    def do_BT(self):
        self.ts.tm = list(IDENTITY)
        self.ts.tlm = list(IDENTITY)

    def do_ET(self):
        pass

    def do_Tc(self, space):
        self.ts.char_spacing = _num(space)

    def do_Tw(self, space):
        self.ts.word_spacing = _num(space)

    def do_Tz(self, scale):
        self.ts.h_scale = _num(scale) / 100

    def do_TL(self, leading):
        self.ts.leading = _num(leading)

    def do_Ts(self, rise):
        self.ts.rise = _num(rise)

    def do_Tr(self, render):
        pass

    def do_Tf(self, fontid, fontsize):
        ts = self.ts
        name = literal_name(fontid) if isinstance(fontid, PSLiteral) else js.jstr(fontid)
        size = _num(fontsize)
        if ts.font and name == ts.font_name and size == ts.font_size:
            return
        self.flush()
        ts.font_name, ts.font_size = name, size
        spec = self.font_specs.get(name)
        # a font missing from the resources: pdf.js (ignoreErrors) falls back to its default font, Helvetica metrics
        self.set_font(self.reader.font(self.rsrcmgr, spec) if spec is not None else self.reader.fallback(self.rsrcmgr))

    def set_font(self, font):
        ts = self.ts
        ts.font = font
        ts.font_matrix = list(font.matrix) if font else FONT_IDENTITY

    def do_Td(self, tx, ty):
        self.ts.translate_tlm(_num(tx), _num(ty))
        self.ts.tm = list(self.ts.tlm)

    def do_TD(self, tx, ty):
        self.ts.leading = -_num(ty)
        self.do_Td(tx, ty)

    def do_Tm(self, a, b, c, d, e, f):
        m = [_num(a), _num(b), _num(c), _num(d), _num(e), _num(f)]
        self.ts.tm, self.ts.tlm = list(m), list(m)
        self.update_adv_scale()

    def do_T_a(self):
        self.ts.carriage_return()

    def do_Tj(self, s):
        if isinstance(s, bytes):
            self.build(s, 0)

    def do_TJ(self, seq):
        ts = self.ts
        if ts.font is None:
            return
        factor = (1 if ts.font.vertical else -1) * ts.font_size / 1000
        buf = []
        for x in list_value(seq):
            x = resolve1(x)
            if isinstance(x, bytes):
                buf.append(x)
            elif js.is_num(x) and x != 0:
                self.build(b"".join(buf), x * factor)
                buf = []
        if buf:
            self.build(b"".join(buf), 0)

    def do__q(self, s):
        if self.ts.font is None:
            return
        self.ts.carriage_return()
        self.do_Tj(s)

    def do__w(self, aw, ac, s):
        if self.ts.font is None:
            return
        self.ts.word_spacing = _num(aw)
        self.ts.char_spacing = _num(ac)
        self.ts.carriage_return()
        self.do_Tj(s)

    def do_BMC(self, tag):
        self.flush()

    def do_BDC(self, tag, props):
        self.flush()

    def do_EMC(self):
        self.flush()

    def do_gs(self, name):
        try:
            gs = dict_value(dict_value(self.resources.get("ExtGState")).get(literal_name(name)))
        except Exception:
            return
        f = resolve1(gs.get("Font"))
        if not f:
            return
        self.flush()
        self.ts.font_name = None
        self.ts.font_size = _num(f[1])
        self.set_font(self.reader.font(self.rsrcmgr, f[0]))

    # -- images and forms -----------------------------------------------------------------------
    def image(self):
        self.reader.image(self.reader.img_ctm)

    def do_EI(self, obj):
        if isinstance(obj, PDFStream):
            self.image()

    def do_Do(self, xobjid_arg):
        self.flush()
        name = literal_name(xobjid_arg)
        try:
            xobj = stream_value(self.xobjmap[name])
        except (KeyError, TypeError):
            return
        sub = xobj.get("Subtype")
        sub = literal_name(sub) if isinstance(sub, PSLiteral) else None
        if sub == "Image":
            self.image()
            return
        if sub != "Form":
            return
        if xobj.objid in self.reader.form_stack:
            return
        res = xobj.get("Resources")
        resources = dict_value(res) if res else self.resources
        ts = self.ts.clone()
        matrix = list_value(xobj.get("Matrix")) if xobj.get("Matrix") is not None else None
        if matrix is not None and len(matrix) == 6:
            ts.ctm = transform(ts.ctm, [_num(x) for x in matrix])
        r = self.reader
        r.form_stack.append(xobj.objid)
        r.img_stack.append(list(r.img_ctm))   # operator list: paintFormXObjectBegin [matrix, bbox] … End
        if matrix:
            r.img_ctm = transform(r.img_ctm, [_num(x) for x in matrix])
        try:
            sub_run = _Run(self.run.out, self.run.view)
            interp = _Interp(self.rsrcmgr, r, sub_run, ts)
            interp.render_contents(resources, [xobj])
            interp.flush()
        finally:
            r.form_stack.pop()
            r.img_ctm = r.img_stack.pop() if r.img_stack else r.img_ctm


class _Reader:
    def __init__(self, vp_t, vp_w, vp_h, cmap_fonts="app"):
        self.vp_t, self.vp_w, self.vp_h = vp_t, vp_w, vp_h
        self.cmap_fonts = cmap_fonts
        self.fonts = {}
        self.imgs = []
        self.img_ctm, self.img_stack = list(IDENTITY), []
        self.form_stack = []
        self.warnings = set()

    def warn(self, w):
        self.warnings.add(w)

    def font(self, rsrcmgr, ref):
        if ref is None:
            return None
        key = ref.objid if isinstance(ref, PDFObjRef) else id(ref)
        if key not in self.fonts:
            try:
                spec = dict_value(ref)
                if self.cmap_fonts == "app" and needs_cmap_files(spec):
                    self.warn("cmap-font")   # the app drops this font's text: pdf.js gets no cMapUrl
                    self.fonts[key] = ErrorFont()
                else:
                    self.fonts[key] = Font(rsrcmgr, ref.objid if isinstance(ref, PDFObjRef) else None, spec)
            except Exception:
                self.fonts[key] = ErrorFont()
        return self.fonts[key]

    def fallback(self, rsrcmgr):
        if "fallback" not in self.fonts:
            from pdfminer.psparser import LIT
            spec = {"Type": LIT("Font"), "Subtype": LIT("Type1"), "BaseFont": LIT("PDFJS-FallbackFont"), "Encoding": LIT("WinAnsiEncoding")}
            try:
                self.fonts["fallback"] = Font(rsrcmgr, None, spec)
            except Exception:
                self.fonts["fallback"] = ErrorFont()
        return self.fonts["fallback"]

    def image(self, ctm):
        pts = [apply(apply(q, ctm), self.vp_t) for q in ([0, 0], [1, 0], [0, 1], [1, 1])]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        bx = [min(xs) / self.vp_w, min(ys) / self.vp_h, max(xs) / self.vp_w, max(ys) / self.vp_h]
        if (bx[2] - bx[0]) * (bx[3] - bx[1]) > 0.03:
            self.imgs.append(bx)


def _box(pdfpage, name):
    v = pdfpage.attrs.get(name)
    v = resolve1(v)
    if isinstance(v, list) and len(v) == 4:
        b = normalize_rect([float(resolve1(x)) for x in v])
        if b[2] - b[0] > 0 and b[3] - b[1] > 0:
            return b
    return None


def page_view(pdfpage):
    media = _box(pdfpage, "MediaBox") or LETTER
    crop = _box(pdfpage, "CropBox") or media
    if crop != media:
        b = intersect(crop, media)
        if b and b[2] - b[0] > 0 and b[3] - b[1] > 0:
            return b
    return media


def page_rotate(pdfpage):
    r = resolve1(pdfpage.attrs.get("Rotate")) or 0
    r = int(r) if js.is_num(r) else 0
    if r % 90:
        return 0
    return r % 360


def text_items(pdfpage, rsrcmgr, cmap_fonts="app"):
    """One page's text items {s, x0, y0, x1, y1} (page fractions, sorted like readPdf), image boxes, rotation."""
    view, rot = page_view(pdfpage), page_rotate(pdfpage)
    vt, vw, vh = viewport(view, rot)
    reader = _Reader(vt, vw, vh, cmap_fonts)
    raw = []
    run = _Run(raw, view)
    interp = _Interp(rsrcmgr, reader, run, TextState())
    contents = pdfpage.contents or []
    try:
        interp.render_contents(pdfpage.resources, contents)
    except Exception:   # a broken content stream: keep what was read, as pdf.js does (ignoreErrors)
        reader.warn("content-error")
    interp.flush()
    items = []
    for t in raw:
        s = js.trim(t.get("str") or "")
        if not s:
            continue
        a, b, c, d, e, f = t["transform"]
        ul = math.hypot(a, b) or 1
        vl = math.hypot(c, d) or 1
        h = t["height"] or vl
        w = t["width"]
        P = [[e, f], [e + a / ul * w, f + b / ul * w], [e + c / vl * h, f + d / vl * h], [e + a / ul * w + c / vl * h, f + b / ul * w + d / vl * h]]
        P = [apply(q, vt) for q in P]
        xs, ys = [q[0] / vw for q in P], [q[1] / vh for q in P]
        items.append({"s": s, "x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)})
    items = js.sort(items, lambda p, q: (p["y0"] - q["y0"]) or (p["x0"] - q["x0"]))
    return items, reader.imgs, rot, sorted(reader.warnings)


def _title(items):
    a = next((it for it in items if js.test("PROCESS FLOW DIAGRAM", it["s"])), None)
    if not a:
        return ""
    cx = (a["x0"] + a["x1"]) / 2   # title-block lines are centred under the "PROCESS FLOW DIAGRAM" line
    xs = [b for b in items if b is not a and b["y0"] > a["y0"] + 0.002 and b["y0"] - a["y1"] < 0.03 and abs((b["x0"] + b["x1"]) / 2 - cx) < 0.06]
    return js.cut(" ".join(x["s"] for x in js.sort(xs, lambda p, q: p["y0"] - q["y0"])[:3]), 110)


def make_sheet(items, imgs, rot, file_name, page, file_id=1):
    """A sheet record as readPdf builds it (identity, title, connectors, badges, stream table, grid, area, equipment)."""
    ident = sheet_identity(items)
    own, aliases = ident["own"], ident["aliases"]
    badges = js.unique(w for it in items if is_badge(it["s"]) and it["y0"] < 0.86 for w in js.split(r"\s+", it["s"]))
    sh = {"key": f"{file_name} p{page}", "fileId": file_id, "file": file_name, "page": page, "dwg": own, "aliases": aliases, "title": _title(items),
          "connectors": connectors_of(items, own, aliases), "badges": badges, "items": items, "imgs": imgs, "textLayer": len(items) > 40,
          "textTable": parse_text_table(items), "rotate": rot}
    try:
        sh["grid"] = sheet_grid(items)
        sh["area"] = sheet_area(sh)
        sh["eq"] = extract_equipment(sh)
    except Exception:   # the app keeps the sheet without equipment when the pass fails
        sh["eq"] = None
    sh["layTitle"] = lay_title(items)
    return sh


def read_pdf(path_or_bytes, name=None, file_id=1, cmap_fonts="app"):
    """Every page of a PDF as a sheet record (see make_sheet), plus pdf-reading warnings per sheet.
    Process sheets and Layout/GA drawings come together; `layout.split_sheets` sorts them as the app does.

    cmap_fonts="app" drops the text of fonts pdf.js cannot load without its CMap files, as the app does
    (warning "cmap-font"); "read" reads them, as the app would if it gave pdf.js a cMapUrl."""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        data = bytes(path_or_bytes)
    else:
        with open(path_or_bytes, "rb") as fh:
            data = fh.read()
        name = name or str(path_or_bytes).replace("\\", "/").rsplit("/", 1)[-1]
    doc = PDFDocument(PDFParser(BytesIO(data)))
    rsrcmgr = PDFResourceManager(caching=True)
    sheets = []
    for p, page in enumerate(PDFPage.create_pages(doc), start=1):
        items, imgs, rot, warnings = text_items(page, rsrcmgr, cmap_fonts)
        sh = make_sheet(items, imgs, rot, name, p, file_id)
        sh["warnings"] = warnings
        sheets.append(sh)
    return sheets
