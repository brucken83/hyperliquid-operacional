from pathlib import Path
import json
ROOT = Path(__file__).resolve().parents[1]
WEB_DATA = ROOT / "web" / "data"
def ensure_file(name, default):
    p = WEB_DATA / name
    if not p.exists():
        p.write_text(json.dumps(default, indent=2, ensure_ascii=False), encoding="utf-8")
def main():
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    ensure_file("latest_status.json", [])
    ensure_file("signals.json", [])
    ensure_file("signals_history.json", [])
    ensure_file("paper_trades.json", [])
    ensure_file("meta.json", {"last_update":"","tracked_assets":0,"signals_now":0,"bull_count":0,"bear_count":0})
    print("ok")
if __name__ == "__main__":
    main()
