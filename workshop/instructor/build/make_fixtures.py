"""Write fixtures/batches/*.csv and instructor/gold_labels.csv from batches_data.py."""
import csv, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from batches_data import BATCHES

ROOT = Path(__file__).resolve().parents[2]
PII = [r"\b000-\d{2}-\d{4}\b", r"\b000000\d{6}\b", r"\(\d{3}\) 555-01\d{2}"]

def redact(t):
    for p in PII:
        t = re.sub(p, "[REDACTED]", t)
    return t

def main():
    (ROOT / "fixtures/batches").mkdir(parents=True, exist_ok=True)
    gold = []
    for b, rows in BATCHES.items():
        with open(ROOT / f"fixtures/batches/batch_{b:02d}.csv", "w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["complaint_id", "date_received", "channel", "narrative"])
            for cid, d, ch, n, g in rows:
                w.writerow([cid, d, ch, n])
                ev = g[4]
                if ev:
                    assert ev in redact(n), (cid, ev)
                    assert len(ev.split()) <= 20, (cid, len(ev.split()))
                assert (ev != "") == ("Y" in g[2:4]), cid
                gold.append([f"batch_{b:02d}", cid, *g, len(n.split())])
    with open(ROOT / "instructor/gold_labels.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["batch", "complaint_id", "product", "issue", "udaap_flag", "fair_lending_flag", "evidence", "narrative_words"])
        w.writerows(gold)

if __name__ == "__main__":
    main()
