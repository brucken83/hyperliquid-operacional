import os, json, time
from pathlib import Path
import pandas as pd, requests

API_URL = "https://api.hyperliquid.xyz/info"
ROOT = Path(__file__).resolve().parents[1]
WEB_DATA = ROOT / "web" / "data"
WEB_DATA.mkdir(parents=True, exist_ok=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
CONFIG = {"coins":["BTC","ETH"],"rsi2_threshold":7,"pullback_lookback_bars":5,"history_limit":25}

def post_info(body):
    r = requests.post(API_URL, json=body, headers={"Content-Type":"application/json"}, timeout=20)
    r.raise_for_status()
    return r.json()

def candle_snapshot(coin, interval, limit=120):
    now_ms = int(time.time()*1000)
    interval_ms = {"15m":900000,"4h":14400000}[interval]
    start_ms = now_ms - interval_ms*limit
    data = post_info({"type":"candleSnapshot","req":{"coin":coin,"interval":interval,"startTime":start_ms,"endTime":now_ms}})
    df = pd.DataFrame(data)
    for col in ["o","h","l","c","v"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["T"] = pd.to_datetime(df["T"], unit="ms", utc=True)
    return df.rename(columns={"o":"open","h":"high","l":"low","c":"close","v":"volume","T":"close_time"})

def meta_and_asset_ctxs():
    raw = post_info({"type":"metaAndAssetCtxs"})
    universe, ctxs = raw[0]["universe"], raw[1]
    out = {}
    for meta, ctx in zip(universe, ctxs):
        out[meta["name"]] = {"funding_hr_pct": float(ctx.get("funding", 0.0))*100.0, "mark_px": float(ctx.get("markPx", 0.0))}
    return out

def rsi(series, period=2):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return (100 - (100 / (1 + rs))).fillna(50)

def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(text)
        return
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=20).raise_for_status()

def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def main():
    ctxs = meta_and_asset_ctxs()
    rows, signals = [], []
    history = load_json(WEB_DATA / "signals_history.json", [])
    existing_keys = {(x.get("coin"), x.get("side"), x.get("time")) for x in history}

    for coin in CONFIG["coins"]:
        df15 = candle_snapshot(coin, "15m", 120)
        df4h = candle_snapshot(coin, "4h", 120)
        df15["ema20"] = df15["close"].ewm(span=20, adjust=False).mean()
        df15["rsi2"] = rsi(df15["close"], 2)
        df4h["sma50"] = df4h["close"].rolling(50).mean()
        last15, prev15 = df15.iloc[-1], df15.iloc[-2]
        last4h = df4h.dropna().iloc[-1]
        trend = "bull" if last4h["close"] > last4h["sma50"] else "bear"
        funding = ctxs.get(coin, {}).get("funding_hr_pct", 0.0)
        rows.append({"coin": coin, "price": float(last15["close"]), "trend": trend, "funding_hr_pct": funding, "rsi2": float(last15["rsi2"]), "time": str(last15["close_time"])})

        long_signal = trend == "bull" and df15.iloc[-CONFIG["pullback_lookback_bars"]:]["rsi2"].min() <= CONFIG["rsi2_threshold"] and last15["close"] > prev15["high"] and last15["close"] > last15["ema20"]
        short_signal = trend == "bear" and df15.iloc[-CONFIG["pullback_lookback_bars"]:]["rsi2"].max() >= (100 - CONFIG["rsi2_threshold"]) and last15["close"] < prev15["low"] and last15["close"] < last15["ema20"]

        if long_signal:
            stop = float(df15.iloc[-5:]["low"].min())
            sig = {"coin": coin, "side": "LONG", "entry": float(last15["close"]), "stop": stop, "target1": float(last15["close"]) + (float(last15["close"]) - stop), "target2": float(last15["close"]) + 2 * (float(last15["close"]) - stop), "funding_hr_pct": funding, "time": str(last15["close_time"])}
            signals.append(sig)
            send_telegram(f"⚡ {coin} LONG\nEntrada: {sig['entry']:.2f}\nStop: {sig['stop']:.2f}\nT1: {sig['target1']:.2f}\nT2: {sig['target2']:.2f}\nFunding: {funding:.4f}%/h")
        if short_signal:
            stop = float(df15.iloc[-5:]["high"].max())
            sig = {"coin": coin, "side": "SHORT", "entry": float(last15["close"]), "stop": stop, "target1": float(last15["close"]) - (stop - float(last15["close"])), "target2": float(last15["close"]) - 2 * (stop - float(last15["close"])), "funding_hr_pct": funding, "time": str(last15["close_time"])}
            signals.append(sig)
            send_telegram(f"⚡ {coin} SHORT\nEntrada: {sig['entry']:.2f}\nStop: {sig['stop']:.2f}\nT1: {sig['target1']:.2f}\nT2: {sig['target2']:.2f}\nFunding: {funding:.4f}%/h")

    for s in signals:
        k = (s.get("coin"), s.get("side"), s.get("time"))
        if k not in existing_keys:
            history.insert(0, s)
    history = history[:CONFIG["history_limit"]]

    save_json(WEB_DATA / "latest_status.json", rows)
    save_json(WEB_DATA / "signals.json", signals)
    save_json(WEB_DATA / "signals_history.json", history)
    paper = [{"coin": s["coin"], "side": s["side"], "entry": s["entry"], "stop": s["stop"], "target1": s["target1"], "target2": s["target2"], "status": "OPEN", "time": s["time"]} for s in signals]
    save_json(WEB_DATA / "paper_trades.json", paper)
    meta = {"last_update": rows[0]["time"] if rows else "", "tracked_assets": len(rows), "signals_now": len(signals), "bull_count": sum(1 for r in rows if r["trend"] == "bull"), "bear_count": sum(1 for r in rows if r["trend"] == "bear")}
    save_json(WEB_DATA / "meta.json", meta)

if __name__ == "__main__":
    main()
