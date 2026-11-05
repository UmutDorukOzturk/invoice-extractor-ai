"""Read a folder of supplier invoices (PDF) into a checked Excel report and CSV files.

Usage:
    python extract.py sample_invoices           # rules only, no API key needed
    python extract.py sample_invoices --ai      # also send scans / unknown layouts to Claude
    python extract.py "C:\\Invoices\\October" --out-dir reports
"""
import argparse
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import anthropic

from invoice_extractor import ai, config, rules, validate
from invoice_extractor.excel_report import payable, write_csvs, write_report
from invoice_extractor.model import InvoiceRecord
from invoice_extractor.pdf_text import has_text_layer, read_text

ROOT = Path(__file__).resolve().parent


def step(n: int, text: str, result: str) -> None:
    print(f"[{n}/4] {(text + ' ').ljust(34, '.')} {result}", flush=True)


NO_KEY = "AI step skipped: no Claude API key found (set ANTHROPIC_API_KEY)"


def run_ai(records: list[InvoiceRecord], folder: Path, model: str) -> tuple[int, int]:
    """Send every record the rules could not complete to Claude. Returns (succeeded, failed)."""
    todo = [i for i, r in enumerate(records) if not r.has_text or r.missing()]
    done = failed = 0
    client = ai.make_client()
    for n, i in enumerate(todo):
        rec = records[i]
        try:
            new = ai.to_record(ai.extract_with_claude((folder / rec.file).read_bytes(), client, model), rec.file)
            new.has_text = rec.has_text
            records[i] = new
            done += 1
        except (anthropic.AuthenticationError, TypeError) as exc:
            # the SDK raises TypeError before sending anything when no credentials are configured
            if isinstance(exc, TypeError) and "authentication" not in str(exc):
                raise
            print(f"      {NO_KEY}")
            for j in todo[n:]:
                records[j].issues.append(NO_KEY)
            return done, failed + len(todo) - n
        except (ai.AIExtractionError, anthropic.AnthropicError) as exc:
            rec.issues.append(f"AI step failed: {exc}")
            failed += 1
    return done, failed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path, help="folder with the invoice PDFs")
    ap.add_argument("--ai", action="store_true", help="read scans and unknown layouts with Claude")
    ap.add_argument("--model", default=config.AI_MODEL, help=f"Claude model for --ai (default {config.AI_MODEL})")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "output")
    args = ap.parse_args()

    started, run_at = time.time(), datetime.now()
    files = sorted(args.folder.glob("*.pdf"), key=lambda p: p.name.lower())
    if not files:
        raise SystemExit(f"No PDF files found in {args.folder}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Invoice extractor · {len(files)} PDF files in '{args.folder.name}'\n")

    texts = {p: read_text(p) for p in files}
    scanned = sum(1 for p in files if not has_text_layer(texts[p]))
    step(1, "Reading PDFs", f"{len(files)} files · {len(files) - scanned} with text · {scanned} scanned")

    records = [rules.extract(texts[p], p.name) if has_text_layer(texts[p])
               else InvoiceRecord(file=p.name, has_text=False) for p in files]
    by_rules = sum(1 for r in records if r.has_text and not r.missing())
    if args.ai:
        done, failed = run_ai(records, args.folder, args.model)
        ai_note = f"{done} by AI" + (f" · {failed} failed" if failed else "")
    else:
        left = sum(1 for r in records if not r.has_text or r.missing())
        ai_note = f"{left} need AI (run with --ai)"
    step(2, "Extracting fields", f"{by_rules} by rules · {ai_note}")

    for rec in records:
        validate.check(rec)
    validate.mark_duplicates(records)
    for rec in records:
        validate.set_status(rec)
    counts = Counter(r.status for r in records)
    step(3, "Checking amounts & duplicates", f"{counts['OK']} OK · {counts['Check']} to check · "
                                             f"{counts['Duplicate']} duplicate · {counts['Unreadable']} unreadable")

    stamp = f"{run_at:%Y-%m-%d_%H%M}"
    out = args.out_dir / f"invoices_{stamp}.xlsx"
    write_report(records, out, run_at, args.folder.name, ai_used=args.ai)
    write_csvs(records, args.out_dir, stamp)
    shown = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    step(4, "Writing Excel + CSV", f"{shown}")

    to_pay = sum(r.total for r in records if payable(r))
    need = sum(1 for r in records if r.status != "OK")
    print(f"\nDone in {time.time() - started:.1f}s · {len(records)} invoices · €{to_pay:,.2f} to pay · "
          f"{need} need attention")


if __name__ == "__main__":
    main()
