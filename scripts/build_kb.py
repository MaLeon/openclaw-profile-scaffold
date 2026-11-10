#!/usr/bin/env python3
"""Build a profile knowledge base from a Q&A source document.

Supports .docx (python-docx), .txt/.md (paragraph per line), .xlsx (openpyxl).

Output (in --out dir):
  faq_<lang>.md   continuous QA-1..N, four sections per entry
  services.md     scope table skeleton + verification points
  qa.json         intermediate for review
"""
import argparse
import json
import os
import re
import sys

LABELS = {
    "zh": ("客户问题", "精准回答", "销售引导/下一步", "依据与合规提示"),
    "id": ("Pertanyaan Klien", "Jawaban Presisi", "Ajakan / Langkah Berikutnya", "Dasar & Catatan Kepatuhan"),
    "en": ("Customer Question", "Precise Answer", "Sales CTA / Next Step", "Basis & Compliance Note"),
}
DEFAULT_CTA = {
    "zh": "请补充需求信息与目标日期，顾问核对范围与缺件后给出书面方案与报价。",
    "id": "Mohon lengkapi data kebutuhan dan target waktu; tim kami akan memeriksa ruang lingkup lalu menyiapkan solusi dan penawaran tertulis.",
    "en": "Share your requirement details and target date; our team will check scope and gaps, then provide a written solution and quotation.",
}
HEADER = {
    "zh": ("# {entity} — 知识库（中文）", "## 使用方式", "## 目录 / Index"),
    "id": ("# {entity} — Basis Pengetahuan Layanan (Bahasa Indonesia)", "## Cara Penggunaan", "## 目录 / Daftar Isi / Index"),
    "en": ("# {entity} — Service Knowledge Base (English)", "## How to Use", "## 目录 / Index"),
}


def read_source(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        import docx
        d = docx.Document(path)
        return [p.text.strip() for p in d.paragraphs if p.text.strip()]
    if ext in (".txt", ".md"):
        return [ln.strip() for ln in open(path, encoding="utf-8").read().splitlines() if ln.strip()]
    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        out = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
                if cells:
                    out.extend(cells)
        return out
    sys.exit(f"unsupported source type: {ext}")


Q_PREFIX = re.compile(r"^(q\s*\d*\s*[.:：)]|pertanyaan\s*\d*\s*[.:：)]|问\s*\d*\s*[.:：]|question\s*\d*\s*[.:：)])\s*", re.I)
A_PREFIX = re.compile(r"^(a\s*\d*\s*[.:：)]|jawaban\s*\d*\s*[.:：)]|答\s*\d*\s*[.:：]|answer\s*\d*\s*[.:：)])\s*", re.I)


def pair_entries(paras):
    pairs = []
    i, n = 0, len(paras)
    while i < n:
        p = paras[i]
        if Q_PREFIX.match(p):
            q = Q_PREFIX.sub("", p)
            ans, j = [], i + 1
            while j < n and not Q_PREFIX.match(paras[j]):
                ans.append(A_PREFIX.sub("", paras[j]))
                j += 1
            if q and ans:
                pairs.append((q, " ".join(ans).strip()))
            i = j
            continue
        if p.endswith("?") and i + 1 < n and not paras[i + 1].endswith("?") and len(paras[i + 1]) > 40:
            pairs.append((p, paras[i + 1]))
            i += 2
            continue
        i += 1
    return pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lang", default="id", choices=list(LABELS))
    ap.add_argument("--entity", required=True)
    ap.add_argument("--expect", type=int, default=0)
    ap.add_argument("--chapters", help="JSON: {chapter_title: {service, stage, cta, basis}}")
    ap.add_argument("--source-note", default="")
    a = ap.parse_args()

    labels = LABELS[a.lang]
    pairs = pair_entries(read_source(a.source))
    if not pairs:
        sys.exit("no Q&A pairs detected — inspect the source and add Q/A prefixes")
    if a.expect and len(pairs) != a.expect:
        sys.exit(f"expected {a.expect} pairs, detected {len(pairs)} — refine parsing before publishing")

    chapters = json.load(open(a.chapters, encoding="utf-8")) if a.chapters else {}
    os.makedirs(a.out, exist_ok=True)
    title, usage_h, toc_h = HEADER[a.lang]
    note = a.source_note or f"Source: {os.path.basename(a.source)} ({len(pairs)} Q&A)"

    entries, seen = [], {}
    for idx, (q, ans) in enumerate(pairs, 1):
        meta = next((v for k, v in chapters.items() if k in q or k in ans), {})
        topic = meta.get("service", "General")
        stage = meta.get("stage", "温线索 / Warm")
        cta = meta.get("cta") or DEFAULT_CTA[a.lang]
        basis = meta.get("basis", "官方系统/法规复核")
        seen[topic] = seen.get(topic, 0) + 1
        entries.append(
            f"### QA-{idx} ｜ {topic} ｜ {stage} ｜ {q[:60]}\n\n"
            f"**{labels[0]}：** {q}\n\n"
            f"**{labels[1]}：** {ans}\n\n"
            f"**{labels[2]}：** {cta}\n\n"
            f"**{labels[3]}：** {basis}\n"
        )

    toc = [f"{i}. {t}（{c}）" for i, (t, c) in enumerate(seen.items(), 1)]
    with open(os.path.join(a.out, f"faq_{a.lang}.md"), "w", encoding="utf-8") as f:
        f.write(title.format(entity=a.entity) + "\n\n")
        f.write(f"> {note}\n> Entity: {a.entity} | Language: {a.lang}\n\n")
        f.write(usage_h + "\n\n")
        f.write("1. Filter by chapter/scenario/customer intent, then tailor the wording.\n")
        f.write("2. Every answer advances one next step: documents, consultation, quotation, or authorization.\n")
        f.write("3. Never promise prices, ETAs, approvals or outcomes; route commitments to the business team.\n")
        f.write("4. Verify regulations and official portals before any filing.\n\n---\n\n")
        f.write(toc_h + "\n\n" + "\n".join(toc) + "\n\n---\n\n")
        f.write("\n---\n\n".join(entries) + "\n")

    with open(os.path.join(a.out, "services.md"), "w", encoding="utf-8") as f:
        f.write(f"""# {a.entity} — 服务范围与核验点 / Service Scope & Verification

> 来源：{os.path.basename(a.source)}。本文只列服务范围与必须核验的事项，不含价格、时效与 SLA。

## 服务范围 / Scope

| 服务 | 关键内容 | 交付/结果 | 必须核验 |
|---|---|---|---|
| （按业务补充） |  |  | 官方系统/团队确认 |

## 提交前需确认的信息 / Required Before Quotation

1. 客户/主体与用途
2. 具体品类、范围或标的
3. 时间要求与截止点
4. 已有资料清单
5. 特殊要求（合规、温控、保险等）

## 官方核验入口 / Official Verification

| 主题 | 核验渠道 |
|---|---|
| 价格、合同、付款 | 业务团队书面报价 |
| 时效与排期 | 运营团队确认 |
| 法规与许可 | 官方系统最新规则 |
""")

    with open(os.path.join(a.out, "qa.json"), "w", encoding="utf-8") as f:
        json.dump([{"n": i + 1, "q": q, "a": ans} for i, (q, ans) in enumerate(pairs)],
                  f, ensure_ascii=False, indent=1)

    print(f"entries: {len(entries)}")
    print(f"themes: {len(seen)} -> {seen}")
    print(f"written: {os.path.join(a.out, 'faq_' + a.lang + '.md')}, services.md, qa.json")


if __name__ == "__main__":
    main()
