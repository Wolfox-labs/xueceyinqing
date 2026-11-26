import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from db.vector_store import get_store, init_knowledge_base

QUERY_FILE = ROOT / "knowledge" / "evaluation" / "queries.json"
REPORT_FILE = ROOT / "knowledge" / "evaluation" / "report.json"


def main() -> None:
    init_knowledge_base()
    queries = json.loads(QUERY_FILE.read_text(encoding="utf-8"))
    store = get_store()
    rows = []
    passed = 0
    for item in queries:
        details = store.search_knowledge_details(item["query"], n_results=3)
        text = " ".join(detail["text"] for detail in details).lower()
        hit = any(keyword.lower() in text for keyword in item["expected"])
        passed += 1 if hit else 0
        rows.append({
            "query": item["query"],
            "expected": item["expected"],
            "hit": hit,
            "top_results": [
                {
                    "knowledge_point": (detail.get("metadata") or {}).get("knowledge_point", ""),
                    "path": (detail.get("metadata") or {}).get("path", ""),
                }
                for detail in details
            ],
        })
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(rows),
        "passed": passed,
        "pass_rate": round(passed / max(1, len(rows)), 4),
        "results": rows,
    }
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("total", "passed", "pass_rate")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
