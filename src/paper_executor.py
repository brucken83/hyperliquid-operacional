from pathlib import Path
import json
ROOT = Path(__file__).resolve().parents[1]
WEB_DATA = ROOT / "web" / "data"
def main():
    signals_path = WEB_DATA / "signals.json"
    paper_path = WEB_DATA / "paper_trades.json"
    if not signals_path.exists():
        return
    signals = json.loads(signals_path.read_text(encoding="utf-8"))
    paper = json.loads(paper_path.read_text(encoding="utf-8")) if paper_path.exists() else []
    existing = {(p["coin"], p["side"], p["time"]) for p in paper}
    for s in signals:
        k = (s["coin"], s["side"], s["time"])
        if k not in existing:
            paper.append({"coin": s["coin"], "side": s["side"], "entry": s["entry"], "stop": s["stop"], "target1": s["target1"], "target2": s["target2"], "status": "OPEN", "time": s["time"]})
    paper_path.write_text(json.dumps(paper, indent=2, ensure_ascii=False), encoding="utf-8")
if __name__ == "__main__":
    main()
