from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
WEB_DATA = ROOT / "web" / "data"

def ensure_file(name, default):
    path = WEB_DATA / name
    if not path.exists():
        path.write_text(json.dumps(default, indent=2), encoding="utf-8")

def main():
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    ensure_file("latest_status.json", [])
    ensure_file("signals.json", [])
    ensure_file("paper_trades.json", [])
    print("Arquivos do dashboard garantidos.")

if __name__ == "__main__":
    main()
