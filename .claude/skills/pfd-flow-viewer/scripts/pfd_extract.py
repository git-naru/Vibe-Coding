#!/usr/bin/env python3
"""Read PFD / mass-balance inputs (PDF, XLSX, DOCX) so their numbers can be transcribed exactly.

Subcommands
  info   FILE.pdf                         page count, size, text-layer check, drawing number/title per page
  find   FILE.pdf TOKEN [TOKEN ...]       pages whose text contains each token (stream numbers, tags)
  text   FILE.pdf PAGE [--raw]            text of one page (pdftotext -layout by default)
  render FILE.pdf PAGES OUTDIR [--dpi N]  render pages to PNG (PAGES like 27 or 3-5 or 6,9,11)
  crop   IMAGE.png OUT.png --box X0 Y0 X1 Y1 [--cols A:B,C:D] [--ref 2000] [--zoom Z]
         Crop a region given in "reference" coordinates (the ~2000 px wide preview the Read tool
         shows). --cols keeps only those x-ranges (e.g. the label column plus the stream columns
         you need) and pastes them side by side, which makes small stream-table digits legible.
  xlsx   FILE.xlsx [--sheet NAME] [--max-rows N] [--max-cols N]
         dump every sheet as tab-separated rows with Excel coordinates (computed values, merged
         cells filled), ready to map onto stream fields.
  docx   FILE.docx                        paragraphs and tables (tab-separated) in document order.

Needs: poppler-utils (pdftoppm, pdftotext, pdfinfo), Pillow, openpyxl, python-docx.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace").stdout


def page_count(pdf):
    m = re.search(r"Pages:\s+(\d+)", run(["pdfinfo", pdf]))
    return int(m.group(1)) if m else 0


def page_text(pdf, page, layout=True):
    cmd = ["pdftotext", "-f", str(page), "-l", str(page)]
    if layout:
        cmd.append("-layout")
    return run(cmd + [pdf, "-"])


def parse_pages(spec):
    out = []
    for part in str(spec).split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def cmd_info(a):
    n = page_count(a.file)
    print(run(["pdfinfo", a.file]).strip())
    print()
    dwg = re.compile(r"\b\d{6}-\d{5}-\d{4}-[A-Z]{2}-[A-Z]{3}-\d{5}\b|\b[A-Z]{2,5}\d?-\d{4}-[A-Z]{2}-[A-Z]{3}-\d{5}\b")
    for p in range(1, n + 1):
        t = page_text(a.file, p, layout=False)
        chars = len(t.strip())
        nums = sorted(set(dwg.findall(t)))
        title = ""
        m = re.search(r"PROCESS FLOW DIAGRAM\s*\n?(.{0,160})", t)
        if m:
            title = " ".join(m.group(1).split())[:120]
        flag = "text" if chars > 200 else "IMAGE-ONLY (needs visual reading/OCR)"
        print(f"p{p:>3} [{flag}, {chars} chars] {title}")
        if nums:
            print("      dwg refs:", ", ".join(nums[:6]) + (" …" if len(nums) > 6 else ""))


def cmd_find(a):
    n = page_count(a.file)
    texts = {p: page_text(a.file, p, layout=False) for p in range(1, n + 1)}
    for tok in a.tokens:
        pat = re.compile(r"(?<![\w.-])" + re.escape(tok) + r"(?![\w.-])")
        hits = [p for p, t in texts.items() if pat.search(t)]
        print(f"{tok}: pages {', '.join(map(str, hits)) if hits else '-'}")


def cmd_text(a):
    sys.stdout.write(page_text(a.file, a.page, layout=not a.raw))


def cmd_render(a):
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    for p in parse_pages(a.pages):
        prefix = out / f"p{p:02d}"
        subprocess.run(["pdftoppm", "-f", str(p), "-l", str(p), "-r", str(a.dpi), "-png", "-singlefile", a.file, str(prefix)],
                       stderr=subprocess.DEVNULL, check=True)
        print(f"{prefix}.png")


def cmd_crop(a):
    from PIL import Image
    im = Image.open(a.image)
    W, H = im.size
    s = W / a.ref
    x0, y0, x1, y1 = a.box
    ranges = [(x0, x1)]
    if a.cols:
        ranges = [tuple(float(v) for v in c.split(":")) for c in a.cols.split(",")]
    parts = [im.crop((int(cx0 * s), int(y0 * s), int(cx1 * s), int(y1 * s))) for cx0, cx1 in ranges]
    w = sum(p.size[0] for p in parts)
    h = max(p.size[1] for p in parts)
    out = Image.new("RGB", (w, h), "white")
    x = 0
    for p in parts:
        out.paste(p, (x, 0))
        x += p.size[0]
    if a.zoom and a.zoom != 1:
        out = out.resize((int(w * a.zoom), int(h * a.zoom)))
    out.save(a.out)
    print(f"{a.out} {out.size[0]}x{out.size[1]} (source scale {s:.2f}px per ref unit)")


def cmd_xlsx(a):
    import openpyxl
    wb = openpyxl.load_workbook(a.file, data_only=True)
    wbf = openpyxl.load_workbook(a.file, data_only=False)  # formulas, shown when no cached value exists
    sheets = [wb[a.sheet]] if a.sheet else wb.worksheets
    for ws in sheets:
        wsf = wbf[ws.title]
        print(f"=== sheet: {ws.title}  dims={ws.dimensions}  max_row={ws.max_row} max_col={ws.max_column}")
        merged = {}
        for rng in ws.merged_cells.ranges:
            v = ws.cell(rng.min_row, rng.min_col).value
            for r in range(rng.min_row, rng.max_row + 1):
                for c in range(rng.min_col, rng.max_col + 1):
                    merged[(r, c)] = v
        for r in range(1, min(ws.max_row, a.max_rows) + 1):
            vals = []
            for c in range(1, min(ws.max_column, a.max_cols) + 1):
                v = ws.cell(r, c).value
                if v is None:
                    v = merged.get((r, c))
                if v is None:
                    f = wsf.cell(r, c).value
                    if isinstance(f, str) and f.startswith("="):
                        v = f"[no cached value: {f}]"
                vals.append("" if v is None else str(v).replace("\n", " ").strip())
            while vals and vals[-1] == "":
                vals.pop()
            if any(vals):
                print(f"R{r}\t" + "\t".join(vals))
        print()


def cmd_docx(a):
    import docx
    d = docx.Document(a.file)
    body = d.element.body
    ti = 0
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            t = "".join(n.text or "" for n in child.iter() if n.tag.endswith("}t")).strip()
            if t:
                print(t)
        elif tag == "tbl":
            tbl = d.tables[ti]
            ti += 1
            print(f"--- table {ti} ({len(tbl.rows)} rows)")
            for row in tbl.rows:
                cells = [c.text.replace("\n", " ").strip() for c in row.cells]
                print("\t".join(cells))
            print("--- end table")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info"); p.add_argument("file"); p.set_defaults(fn=cmd_info)
    p = sub.add_parser("find"); p.add_argument("file"); p.add_argument("tokens", nargs="+"); p.set_defaults(fn=cmd_find)
    p = sub.add_parser("text"); p.add_argument("file"); p.add_argument("page", type=int); p.add_argument("--raw", action="store_true"); p.set_defaults(fn=cmd_text)
    p = sub.add_parser("render"); p.add_argument("file"); p.add_argument("pages"); p.add_argument("outdir"); p.add_argument("--dpi", type=int, default=250); p.set_defaults(fn=cmd_render)
    p = sub.add_parser("crop"); p.add_argument("image"); p.add_argument("out")
    p.add_argument("--box", nargs=4, type=float, required=True, metavar=("X0", "Y0", "X1", "Y1"))
    p.add_argument("--cols", help="x-ranges to keep, e.g. 50:215,420:600")
    p.add_argument("--ref", type=float, default=2000, help="width of the reference coordinate space (default 2000)")
    p.add_argument("--zoom", type=float, default=1.0)
    p.set_defaults(fn=cmd_crop)
    p = sub.add_parser("xlsx"); p.add_argument("file"); p.add_argument("--sheet"); p.add_argument("--max-rows", type=int, default=400); p.add_argument("--max-cols", type=int, default=80); p.set_defaults(fn=cmd_xlsx)
    p = sub.add_parser("docx"); p.add_argument("file"); p.set_defaults(fn=cmd_docx)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
