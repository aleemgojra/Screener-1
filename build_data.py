#!/usr/bin/env python3
"""Scans NASDAQ and NYSE common stocks and writes data.json.

A stock is kept only if ALL three hold:
  1. trailing P/E is above 0 and below 20
  2. latest daily volume is above 2x the average of the 20 sessions before it
  3. 14-day Wilder RSI on daily closes is above 50

Stages: (1) symbol lists from nasdaqtrader.com, (2) bulk daily history from
Yahoo Finance via yfinance, which gives RSI and volume ratio for every ticker,
(3) trailing P/E, fetched only for tickers that already pass RSI and volume.
"""
import csv, io, json, re, sys, time, datetime as dt
from concurrent.futures import ThreadPoolExecutor
import urllib.request

PE_MAX, VOL_MULT, RSI_MIN = 20.0, 2.0, 50.0
RSI_N, AVG_N = 14, 20
INCLUDE_EXCHANGES = {"N": "NYSE"}          # add "A": "NYSE American", "P": "NYSE Arca" if wanted
BATCH = 400
NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
BAD_NAME = re.compile(r"\b(warrants?|rights?|units?|preferred|depositary|notes?|debentures?|subordinated)\b", re.I)
SYM_OK = re.compile(r"^[A-Z]{1,5}([.-][A-Z])?$")


def rsi_wilder(closes, n=RSI_N):
    """Wilder's RSI of the last close. Needs at least n+1 closes."""
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    ag, al = gains / n, losses / n
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0.0)) / n
        al = (al * (n - 1) + max(-d, 0.0)) / n
    if al == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + ag / al)


def volume_ratio(volumes, n=AVG_N):
    """Latest volume divided by the mean of the n sessions before it."""
    if len(volumes) < n + 1:
        return None, None
    prev = volumes[-(n + 1):-1]
    avg = sum(prev) / n
    if avg <= 0:
        return None, None
    return volumes[-1] / avg, avg


def parse_universe(nasdaq_txt, other_txt):
    out = {}
    for row in csv.DictReader(io.StringIO(nasdaq_txt), delimiter="|"):
        s = (row.get("Symbol") or "").strip()
        if not s or s.startswith("File Creation"):
            continue
        if row.get("ETF") == "Y" or row.get("Test Issue") == "Y":
            continue
        out[s] = (row["Security Name"], "NASDAQ")
    for row in csv.DictReader(io.StringIO(other_txt), delimiter="|"):
        s = (row.get("ACT Symbol") or "").strip()
        if not s or s.startswith("File Creation"):
            continue
        ex = INCLUDE_EXCHANGES.get(row.get("Exchange"))
        if not ex or row.get("ETF") == "Y" or row.get("Test Issue") == "Y":
            continue
        out[s] = (row["Security Name"], ex)
    clean = {}
    for s, (name, ex) in out.items():
        if not SYM_OK.match(s) or BAD_NAME.search(name):
            continue
        clean[s.replace(".", "-")] = (name.split(" - ")[0].strip(), ex)   # Yahoo uses BRK-B
    return clean


def fetch_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def scan_history(symbols):
    import yfinance as yf
    hits, scanned = [], 0
    for i in range(0, len(symbols), BATCH):
        chunk = symbols[i:i + BATCH]
        try:
            df = yf.download(chunk, period="4mo", interval="1d", group_by="ticker",
                             auto_adjust=True, threads=True, progress=False)
        except Exception as e:
            print("batch failed", i, e, file=sys.stderr)
            continue
        for s in chunk:
            try:
                sub = df[s] if len(chunk) > 1 else df
                sub = sub.dropna(subset=["Close", "Volume"])
                closes, vols = sub["Close"].tolist(), sub["Volume"].tolist()
            except Exception:
                continue
            scanned += 1
            r = rsi_wilder(closes)
            ratio, avg = volume_ratio(vols)
            if r is None or ratio is None:
                continue
            if r > RSI_MIN and ratio > VOL_MULT:
                prev = closes[-2] if len(closes) > 1 else closes[-1]
                hits.append({"sym": s, "price": closes[-1], "chg": (closes[-1] / prev - 1) * 100 if prev else 0,
                             "rsi": r, "ratio": ratio, "vol": vols[-1], "avgVol": avg,
                             "asOf": str(sub.index[-1].date())})
        print(f"history {min(i + BATCH, len(symbols))}/{len(symbols)}  candidates so far: {len(hits)}", flush=True)
    return hits, scanned


def trailing_pe(sym):
    import yfinance as yf
    for attempt in range(2):
        try:
            info = yf.Ticker(sym).info
            pe = info.get("trailingPE")
            return float(pe) if pe is not None else None
        except Exception:
            time.sleep(1.5)
    return None


def main():
    uni = parse_universe(fetch_text(NASDAQ_URL), fetch_text(OTHER_URL))
    counts = {ex: sum(1 for v in uni.values() if v[1] == ex) for ex in {v[1] for v in uni.values()}}
    print("universe", counts)
    cands, scanned = scan_history(sorted(uni))
    with ThreadPoolExecutor(8) as pool:
        pes = list(pool.map(trailing_pe, [c["sym"] for c in cands]))
    stocks, no_pe = [], 0
    for c, pe in zip(cands, pes):
        if pe is None:
            no_pe += 1
            continue
        if 0 < pe < PE_MAX:
            c["pe"], c["name"], c["exch"] = pe, uni[c["sym"]][0], uni[c["sym"]][1]
            stocks.append(c)
    stocks.sort(key=lambda x: -x["ratio"])
    out = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "rules": {"peMax": PE_MAX, "volMult": VOL_MULT, "rsiMin": RSI_MIN},
           "universe": counts, "scanned": scanned, "passedRsiVolume": len(cands), "noPe": no_pe,
           "stocks": stocks}
    with open("data.json", "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"done: {len(stocks)} stocks match all three rules")


if __name__ == "__main__":
    main()
