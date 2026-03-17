import os, json, time
from pathlib import Path
import pandas as pd
import requests

API_URL = "https://api.hyperliquid.xyz/info"
COINGLASS_API_URL = "https://open-api-v4.coinglass.com/api/futures/longShortRate/history"
ROOT = Path(__file__).resolve().parents[1]
WEB_DATA = ROOT / "web" / "data"
WEB_DATA.mkdir(parents=True, exist_ok=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
COINGLASS_API_KEY = os.getenv("COINGLASS_API_KEY", "")

CONFIG = {"coins":["BTC","ETH"],"rsi2_threshold":7,"pullback_lookback_bars":5,"history_limit":25,"coinglass_enabled":True}

def post_info(body):
    r = requests.post(API_URL, json=body, headers={"Content-Type":"application/json"}, timeout=20)
    r.raise_for_status()
    return r.json()

def candle_snapshot(coin, interval, limit=160):
    now_ms = int(time.time()*1000)
    interval_ms = {"15m":900000,"4h":14400000}[interval]
    start_ms = now_ms - interval_ms*limit
    data = post_info({"type":"candleSnapshot","req":{"coin":coin,"interval":interval,"startTime":start_ms,"endTime":now_ms}})
    df = pd.DataFrame(data)
    if df.empty:
        raise RuntimeError(f"Sem candles para {coin} {interval}")
    for col in ["o","h","l","c","v"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["T"] = pd.to_datetime(df["T"], unit="ms", utc=True)
    return df.rename(columns={"o":"open","h":"high","l":"low","c":"close","v":"volume","T":"close_time"})

def meta_and_asset_ctxs():
    raw = post_info({"type":"metaAndAssetCtxs"})
    universe, ctxs = raw[0]["universe"], raw[1]
    out = {}
    for meta, ctx in zip(universe, ctxs):
        open_interest = None
        for key in ["openInterest","open_interest","oi","dayNtlVlm"]:
            if key in ctx and ctx.get(key) not in (None, ""):
                try:
                    open_interest = float(ctx.get(key)); break
                except Exception:
                    pass
        try:
            funding = float(ctx.get("funding", 0.0))*100.0
        except Exception:
            funding = 0.0
        try:
            mark_px = float(ctx.get("markPx", 0.0))
        except Exception:
            mark_px = 0.0
        out[meta["name"]] = {"funding_hr_pct": funding, "mark_px": mark_px, "open_interest": open_interest}
    return out

def rsi(series, period=2):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return (100 - (100 / (1 + rs))).fillna(50)

def calc_cvd(df15):
    signed_volume = df15.apply(lambda r: r["volume"] if r["close"] >= r["open"] else -r["volume"], axis=1)
    return float(signed_volume.cumsum().iloc[-1]), float(signed_volume.tail(12).sum())

def get_long_short_ratio(coin):
    if not COINGLASS_API_KEY or not CONFIG.get("coinglass_enabled", True):
        return None
    symbol = "BTC" if coin == "BTC" else "ETH"
    params = {"exchange":"Hyperliquid","symbol":symbol,"interval":"1h","limit":"1"}
    headers = {"CG-API-KEY": COINGLASS_API_KEY, "accept":"application/json"}
    try:
        r = requests.get(COINGLASS_API_URL, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json().get("data")
        if isinstance(data, list) and data:
            row = data[-1]
            for k in ["longShortRate","longShortRatio","ratio"]:
                if k in row: return float(row[k])
        if isinstance(data, dict):
            for key in ["list","data","items"]:
                if key in data and data[key]:
                    row = data[key][-1]
                    for k in ["longShortRate","longShortRatio","ratio"]:
                        if k in row: return float(row[k])
    except Exception as e:
        print(f"Coinglass ratio error {coin}: {e}")
    return None

def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(text); return
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id":TELEGRAM_CHAT_ID,"text":text}, timeout=20).raise_for_status()

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
    market_metrics = {}

    for coin in CONFIG["coins"]:
        df15 = candle_snapshot(coin, "15m", 160)
        df4h = candle_snapshot(coin, "4h", 120)
        df15["ema20"] = df15["close"].ewm(span=20, adjust=False).mean()
        df15["rsi2"] = rsi(df15["close"], 2)
        df4h["sma50"] = df4h["close"].rolling(50).mean()
        last15, prev15 = df15.iloc[-1], df15.iloc[-2]
        last4h = df4h.dropna().iloc[-1]
        trend = "bull" if last4h["close"] > last4h["sma50"] else "bear"
        funding = ctxs.get(coin, {}).get("funding_hr_pct", 0.0)
        oi = ctxs.get(coin, {}).get("open_interest", None)
        cvd_total, cvd_12 = calc_cvd(df15)
        ls_ratio = get_long_short_ratio(coin)

        rows.append({"coin": coin, "price": float(last15["close"]), "trend": trend, "funding_hr_pct": funding, "rsi2": float(last15["rsi2"]), "time": str(last15["close_time"])})
        market_metrics[coin] = {"funding_hr_pct": funding, "open_interest": oi, "cvd_total": cvd_total, "cvd_12bars": cvd_12, "long_short_ratio": ls_ratio}

        long_signal = trend == "bull" and df15.iloc[-CONFIG["pullback_lookback_bars"]:]["rsi2"].min() <= CONFIG["rsi2_threshold"] and last15["close"] > prev15["high"] and last15["close"] > last15["ema20"]
        short_signal = trend == "bear" and df15.iloc[-CONFIG["pullback_lookback_bars"]:]["rsi2"].max() >= (100-CONFIG["rsi2_threshold"]) and last15["close"] < prev15["low"] and last15["close"] < last15["ema20"]

        if long_signal:
            stop = float(df15.iloc[-5:]["low"].min())
            sig = {"coin":coin,"side":"LONG","entry":float(last15["close"]),"stop":stop,"target1":float(last15["close"])+(float(last15["close"])-stop),"target2":float(last15["close"])+2*(float(last15["close"])-stop),"funding_hr_pct":funding,"time":str(last15["close_time"])}
            signals.append(sig)
            send_telegram(f"⚡ {coin} LONG\nEntrada: {sig['entry']:.2f}\nStop: {sig['stop']:.2f}\nT1: {sig['target1']:.2f}\nT2: {sig['target2']:.2f}\nFunding: {funding:.4f}%/h\nOI: {oi}\nL/S Ratio: {ls_ratio}")
        if short_signal:
            stop = float(df15.iloc[-5:]["high"].max())
            sig = {"coin":coin,"side":"SHORT","entry":float(last15["close"]),"stop":stop,"target1":float(last15["close"])-(stop-float(last15["close"])),"target2":float(last15["close"])-2*(stop-float(last15["close"])),"funding_hr_pct":funding,"time":str(last15["close_time"])}
            signals.append(sig)
            send_telegram(f"⚡ {coin} SHORT\nEntrada: {sig['entry']:.2f}\nStop: {sig['stop']:.2f}\nT1: {sig['target1']:.2f}\nT2: {sig['target2']:.2f}\nFunding: {funding:.4f}%/h\nOI: {oi}\nL/S Ratio: {ls_ratio}")

    for s in signals:
        k = (s.get("coin"), s.get("side"), s.get("time"))
        if k not in existing_keys:
            history.insert(0, s)
    history = history[:CONFIG["history_limit"]]
    save_json(WEB_DATA / "latest_status.json", rows)
    save_json(WEB_DATA / "signals.json", signals)
    save_json(WEB_DATA / "signals_history.json", history)
    paper = [{"coin":s["coin"],"side":s["side"],"entry":s["entry"],"stop":s["stop"],"target1":s["target1"],"target2":s["target2"],"status":"OPEN","time":s["time"]} for s in signals]
    save_json(WEB_DATA / "paper_trades.json", paper)
    meta = {"last_update":rows[0]["time"] if rows else "","tracked_assets":len(rows),"signals_now":len(signals),"bull_count":sum(1 for r in rows if r["trend"]=="bull"),"bear_count":sum(1 for r in rows if r["trend"]=="bear")}
    save_json(WEB_DATA / "meta.json", meta)
    save_json(WEB_DATA / "market_metrics.json", market_metrics)

if __name__ == "__main__":
    main()
