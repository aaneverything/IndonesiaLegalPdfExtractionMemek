import json, re, unicodedata
from pathlib import Path
from typing import List, Dict, Optional

# ---------- Configure your PDFs ----------
PDF_FILES = [
    {"pdf": "pdf/UU Nomor 1 Tahun 2023.pdf", "uu_code": "UU_CIPTA_KERJA_2023", "uu_name": "Undang-Undang Cipta Kerja", "uu_number": "UU No. 1 Tahun 2023", "year": 2023, "valid_from": None, "valid_to": None},
    {"pdf": "pdf/UU Nomor 1 Tahun 2024.pdf", "uu_code": "UU_ITE_2024", "uu_name": "Undang-Undang Informasi dan Transaksi Elektronik (Perubahan 2024)", "uu_number": "UU No. 1 Tahun 2024", "year": 2024, "valid_from": None, "valid_to": None},
    {"pdf": "pdf/UU Nomor 6 Tahun 2023.pdf", "uu_code": "KUHP_2023", "uu_name": "Kitab Undang-Undang Hukum Pidana (KUHP)", "uu_number": "UU No. 6 Tahun 2023", "year": 2023, "valid_from": "2023-03-31", "valid_to": None},
    {"pdf": "pdf/UU Nomor 8 Tahun 1999.pdf", "uu_code": "UU_PERLINDUNGAN_KONSUMEN_1999", "uu_name": "Undang-Undang Perlindungan Konsumen", "uu_number": "UU No. 8 Tahun 1999", "year": 1999, "valid_from": None, "valid_to": None},
    {"pdf": "pdf/UU Nomor 16 Tahun 2019.pdf", "uu_code": "UU_PERKAWINAN_2019", "uu_name": "Undang-Undang Perkawinan", "uu_number": "UU No. 16 Tahun 2019", "year": 2019, "valid_from": None, "valid_to": None},
    {"pdf": "pdf/UU Nomor 27 Tahun 2022.pdf", "uu_code": "UU_PDP_2022", "uu_name": "Undang-Undang Perlindungan Data Pribadi", "uu_number": "UU No. 27 Tahun 2022", "year": 2022, "valid_from": None, "valid_to": None},
    {"pdf": "pdf/UU Nomor 35 Tahun 2009.pdf", "uu_code": "UU_NARKOTIKA_2009", "uu_name": "Undang-Undang Narkotika", "uu_number": "UU No. 35 Tahun 2009", "year": 2009, "valid_from": None, "valid_to": None},
    {"pdf": "pdf/UU Nomor 35 Tahun 2014.pdf", "uu_code": "UU_PERLINDUNGAN_ANAK_2014", "uu_name": "Undang-Undang Perlindungan Anak", "uu_number": "UU No. 35 Tahun 2014", "year": 2014, "valid_from": None, "valid_to": None}
]

OUTPUT_FILE = "final_corpus.jsonl"

# ---------- PDF extraction (pypdf / pdfminer fallback) ----------
def _extract_with_pypdf(pdf_path: str) -> str:
    from pypdf import PdfReader
    reader = PdfReader(pdf_path)
    pages = []
    for p in reader.pages:
        txt = p.extract_text() or ""
        pages.append(txt.replace("\r", ""))
    return "\n".join(pages)

def _extract_with_pdfminer(pdf_path: str) -> str:
    from pdfminer.high_level import extract_text
    txt = extract_text(pdf_path) or ""
    return txt.replace("\r", "")

def read_pdf_text(pdf_path: str) -> str:
    # try pypdf, fallback to pdfminer if text seems too short or pypdf fails
    try:
        txt = _extract_with_pypdf(pdf_path)
    except Exception:
        txt = ""
    if len(txt) < 500:  # heuristic threshold; adjust if needed
        try:
            alt = _extract_with_pdfminer(pdf_path)
            if len(alt) > len(txt):
                return alt
        except Exception:
            pass
    return txt

# ---------- Structure detection (Pasal / Buku / Bab / Bagian) ----------
PASAL_ANY_RE = re.compile(r'(?im)^\s*Pasal\s+((\d+[A-Za-z]?)|([IVXLCM]+))\s*$', re.MULTILINE)
BUKU_RE   = re.compile(r'(?im)^\s*BUKU\s+([IVXLC]+)\s*(.*)$')
BAB_RE    = re.compile(r'(?im)^\s*BAB\s+([IVXLC]+)\s*(.*)$')
BAGIAN_RE = re.compile(r'(?im)^\s*Bagian\s+([0-9IVXLC]+)\s*(.*)$')

def detect_structure(full_text: str) -> List[Dict]:
    lines = full_text.splitlines()
    line_starts = []
    pos = 0
    for ln in lines:
        line_starts.append(pos)
        pos += len(ln) + 1

    buku_marks, bab_marks, bagian_marks = [], [], []
    for i, ln in enumerate(lines):
        m = BUKU_RE.match(ln)
        if m:
            buku_marks.append((line_starts[i], ("BUKU", m.group(1).strip(), (m.group(2) or "").strip())))
        m = BAB_RE.match(ln)
        if m:
            bab_marks.append((line_starts[i], ("BAB", m.group(1).strip(), (m.group(2) or "").strip())))
        m = BAGIAN_RE.match(ln)
        if m:
            bagian_marks.append((line_starts[i], ("BAGIAN", m.group(1).strip(), (m.group(2) or "").strip())))

    def nearest_tag(idx, marks):
        prev = None
        for (p, tag) in marks:
            if p <= idx:
                prev = tag
            else:
                break
        return prev

    matches = list(PASAL_ANY_RE.finditer(full_text))
    out = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i+1].start() if i+1 < len(matches) else len(full_text)
        pasal_label = m.group(1).strip()
        body = full_text[start:end].strip()
        # remove "Pasal X" header line only
        body = re.sub(r'(?im)^\s*Pasal\s+' + re.escape(pasal_label) + r'\s*$', '', body).strip()
        # tidy whitespace but preserve long separator lines and ayat markers
        body = re.sub(r'[ \t]+', ' ', body)
        out.append({
            "pasal_number": pasal_label,
            "text": body,
            "buku": nearest_tag(start, buku_marks),
            "bab": nearest_tag(start, bab_marks),
            "bagian": nearest_tag(start, bagian_marks)
        })
    return out

# ---------- Minimal cleaning (preserve separators and ayat markers) ----------
def minimal_clean(t: str) -> str:
    if t is None:
        return t
    # remove null bytes, normalize Unicode, join hyphenation like "da-\nri" -> "dari"
    t = t.replace('\x00', '')
    t = unicodedata.normalize('NFKC', t)
    t = re.sub(r'-\n\s*', '', t)
    # trim trailing whitespace on each line
    lines = [ln.rstrip() for ln in t.splitlines()]
    # collapse 4+ newlines into two, but keep 1-3 as-is (so separator lines remain)
    text = "\n".join(lines)
    text = re.sub(r'\n{4,}', '\n\n', text)
    # replace multiple spaces/tabs with single space (but keep newlines)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()

# ---------- Build per-pasal record (no id, unit=pasal) ----------
def build_records_per_pdf(cfg: Dict) -> List[Dict]:
    pdf_path = Path(cfg["pdf"])
    raw_text = read_pdf_text(pdf_path)
    if not raw_text or not raw_text.strip():
        return []
    blocks = detect_structure(raw_text)
    records = []
    for blk in blocks:
        pasal = blk.get("pasal_number")
        body = blk.get("text", "")
        # minimal cleaning only; do NOT split ayat -> keep (1)/(2) markers in text
        cleaned = minimal_clean(body)
        buku_obj = blk.get("buku")
        bab_obj = blk.get("bab")
        bagian_obj = blk.get("bagian")

        rec = {
            "uu_code": cfg.get("uu_code"),
            "uu_name": cfg.get("uu_name"),
            "uu_number": cfg.get("uu_number"),
            "year": cfg.get("year"),
            "section_type": "PASAL",
            "title": f"Pasal {pasal}",
            "pasal_number": pasal,
            "ayat_number": None,               # per-pasal output like your example
            "buku": (buku_obj[1] if buku_obj else None),
            "bab": (bab_obj[1] if bab_obj else None),
            "bagian": (bagian_obj[1] if bagian_obj else None),
            "valid_from": cfg.get("valid_from"),
            "valid_to": cfg.get("valid_to"),
            "source_file": pdf_path.name,
            "text": cleaned
        }
        records.append(rec)
    return records

# ---------- Write output ----------
def write_jsonl(records: List[Dict], out_path: str):
    with open(out_path, "a", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

# ---------- Main ----------
def main():
    outp = Path(OUTPUT_FILE)
    outp.write_text("", encoding="utf-8")  # clear
    total = 0
    for cfg in PDF_FILES:
        p = Path(cfg["pdf"])
        if not p.exists():
            print(f"❌ Missing file: {cfg['pdf']}  (skipping)")
            continue
        try:
            recs = build_records_per_pdf(cfg)
        except Exception as e:
            print(f"⚠️ Error processing {cfg['pdf']}: {e}")
            continue
        write_jsonl(recs, OUTPUT_FILE)
        print(f"✅ {p.name} -> {len(recs)} records")
        total += len(recs)
    print(f"\nWROTE TOTAL: {total} records → {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
