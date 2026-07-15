#!/usr/bin/env python3
"""
East Money A-share market snapshot fetcher — stdlib only, multi-source.

Design:
- Each dimension tries multiple hosts / endpoints; output records `source_used`.
- Historical: push2ex pools + push2his index kline (range fetch, cached).
- Live supplement: push2 ulist / clist (labeled, never masquerade as history).
- Stable supplement: datacenter-web (northbound, etc.).

Usage:
    python3 fetch_market_data.py
    python3 fetch_market_data.py --date 20260710
    python3 fetch_market_data.py --days 7 --date 20260710
    python3 fetch_market_data.py --date 20260710 --lite   # skip slow breadth pagination
"""

from __future__ import annotations

import argparse
import json
import random
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, timedelta
from statistics import mean, median

UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://data.eastmoney.com/",
}
ZT_UT = "7eea3edcaed734bea9cbfc24409ed989"
FS_A = "m:0+t:6,m:0+t:80,m:0+t:81,m:1+t:2,m:1+t:23"
DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"

PUSH2_HOSTS = [
    "push2.eastmoney.com",
    "82.push2.eastmoney.com",
    "98.push2.eastmoney.com",
    "push2delay.eastmoney.com",
]
PUSH2HIS_HOSTS = ["push2his.eastmoney.com", "82.push2his.eastmoney.com"]
PUSH2EX_HOSTS = ["push2ex.eastmoney.com"]

INDEXES = [
    ("1.000001", "上证指数"),
    ("0.399001", "深证成指"),
    ("0.399006", "创业板指"),
    ("1.000688", "科创50"),
    ("1.000016", "上证50"),
    ("0.932000", "中证2000"),
]

# Sina finance symbol fallback when push2his is blocked
SINA_INDEX = {
    "1.000001": "sh000001",
    "0.399001": "sz399001",
    "0.399006": "sz399006",
    "1.000688": "sh000688",
    "1.000016": "sh000016",
    "0.932000": "sz932000",  # may be empty; push2his preferred
}

SINA_UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://finance.sina.com.cn/",
}

# module-level kline cache: (secid, beg, end) -> {yyyymmdd: row}
_KLINE_CACHE: dict[tuple[str, str, str], dict[str, dict]] = {}


def _sleep(base: float = 0.35, attempt: int = 0):
    time.sleep(base + random.uniform(0, 0.25) + attempt * 0.45)


def _read_json(url: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _fetch_url(url: str, timeout: int = 25, retries: int = 6) -> dict:
    last = None
    for attempt in range(retries):
        try:
            return _read_json(url, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            last = e
            _sleep(attempt=attempt)
    raise last


def _fetch_hosts(path_query: str, hosts: list[str], timeout: int = 25, retries: int = 4) -> tuple[str, dict]:
    """path_query like '/api/qt/clist/get?pn=1...' — tries https on each host."""
    last = None
    for attempt in range(retries):
        for host in hosts:
            url = f"https://{host}{path_query}"
            try:
                return host, _read_json(url, timeout=timeout)
            except Exception as e:  # noqa: BLE001
                last = e
            _sleep(attempt=attempt)
    raise last


def safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001
        return {"_error": str(e), "source_status": "failed"}


def fmt_day(d: date | str | None = None) -> str:
    if d is None:
        return date.today().strftime("%Y%m%d")
    if isinstance(d, date):
        return d.strftime("%Y%m%d")
    return d.replace("-", "")[:8]


def parse_day(d: str) -> date:
    s = fmt_day(d)
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def trading_weekdays(n: int, end_day: str | None = None) -> list[date]:
    cur = parse_day(end_day) if end_day else date.today()
    out: list[date] = []
    while len(out) < n:
        if cur.weekday() < 5:
            out.append(cur)
        cur -= timedelta(days=1)
    return list(reversed(out))


def _pool(endpoint: str, day: str, sort: str, pagesize: int = 10000) -> dict:
    params = {
        "ut": ZT_UT,
        "dpt": "wz.ztzt",
        "Pageindex": "0",
        "pagesize": str(pagesize),
        "sort": sort,
        "date": fmt_day(day),
    }
    q = f"/{endpoint}?" + urllib.parse.urlencode(params)
    host, data = _fetch_hosts(q, PUSH2EX_HOSTS, retries=5)
    block = data.get("data") or {}
    pool = block.get("pool") or []
    return {
        "endpoint": endpoint,
        "host": host,
        "date": fmt_day(day),
        "total": block.get("tc", len(pool)),
        "pool": pool,
        "source_scope": "historical_by_date",
    }


def limit_up_pool(day: str | None = None) -> dict:
    d = fmt_day(day)
    p = _pool("getTopicZTPool", d, "fbt:asc")
    rows = p["pool"]
    max_lbc = max((r.get("lbc") or 0 for r in rows), default=0)
    industries = Counter(r.get("hybk") for r in rows if r.get("hybk"))
    return {
        "date": d,
        "source_used": f"push2ex/{p['endpoint']}@{p['host']}",
        "limit_up_count": p["total"],
        "max_consecutive_boards": max_lbc,
        "industry_limit_up_top": [{"name": k, "count": v} for k, v in industries.most_common(12)],
        "sample": [
            {
                "code": r.get("c"),
                "name": r.get("n"),
                "change_pct": r.get("zdp"),
                "boards": r.get("lbc"),
                "industry": r.get("hybk"),
                "first_limit_time": str(r.get("fbt", "")).zfill(6),
                "seal_money": r.get("fund"),
                "opened_times_while_sealed": r.get("zbc"),
            }
            for r in rows[:20]
        ],
        "source_scope": p["source_scope"],
    }


def limit_down_pool(day: str | None = None) -> dict:
    d = fmt_day(day)
    p = _pool("getTopicDTPool", d, "fund:asc")
    return {
        "date": d,
        "source_used": f"push2ex/{p['endpoint']}@{p['host']}",
        "limit_down_count": p["total"],
        "sample": [
            {
                "code": r.get("c"),
                "name": r.get("n"),
                "change_pct": r.get("zdp"),
                "industry": r.get("hybk"),
                "continuous_limit_down": r.get("lbc"),
            }
            for r in p["pool"][:20]
        ],
        "source_scope": p["source_scope"],
    }


def opened_board_pool(day: str | None = None) -> dict:
    d = fmt_day(day)
    p = _pool("getTopicZBPool", d, "fbt:asc", pagesize=5000)
    return {
        "date": d,
        "source_used": f"push2ex/{p['endpoint']}@{p['host']}",
        "opened_board_count": p["total"],
        "sample": [
            {
                "code": r.get("c"),
                "name": r.get("n"),
                "change_pct": r.get("zdp"),
                "industry": r.get("hybk"),
                "opened_times": r.get("zbc"),
            }
            for r in p["pool"][:20]
        ],
        "source_scope": p["source_scope"],
    }


def strong_pool(day: str | None = None) -> dict:
    d = fmt_day(day)
    p = _pool("getTopicQSPool", d, "zdp:desc", pagesize=500)
    return {
        "date": d,
        "source_used": f"push2ex/{p['endpoint']}@{p['host']}",
        "strong_count": p["total"],
        "sample": [
            {"code": r.get("c"), "name": r.get("n"), "change_pct": r.get("zdp"), "industry": r.get("hybk")}
            for r in p["pool"][:15]
        ],
        "source_scope": "historical_by_date",
    }


def zt_ladder(day: str | None = None) -> dict:
    d = fmt_day(day)
    p = _pool("getTopicZTPool", d, "fbt:asc")
    groups: dict[int, list] = defaultdict(list)
    for r in p["pool"]:
        groups[int(r.get("lbc") or 0)].append(r)
    return {
        "date": d,
        "source_used": f"push2ex/{p['endpoint']}@{p['host']}",
        "ladder_counts": {str(k): len(v) for k, v in sorted(groups.items()) if k > 0},
        "max_boards": max(groups.keys(), default=0),
        "top_names": {
            str(k): [x.get("n") for x in v[:8]]
            for k, v in sorted(groups.items(), key=lambda kv: -kv[0])[:4]
            if k > 0
        },
        "source_scope": "historical_by_date",
    }


def yesterday_zt_today(day: str | None = None) -> dict:
    d = fmt_day(day)
    p = _pool("getYesterdayZTPool", d, "zs:desc", pagesize=5000)
    rows = p["pool"]
    chgs = [r.get("zdp") for r in rows if isinstance(r.get("zdp"), (int, float))]
    if not chgs:
        return {"date": d, "sampled": 0, "source_used": f"push2ex/{p['endpoint']}", "source_scope": "historical_by_date"}
    red = sum(1 for x in chgs if x > 0)
    promoted = sum(1 for x in chgs if x >= 9.5)
    nuked = sum(1 for x in chgs if x <= -7)
    return {
        "date": d,
        "source_used": f"push2ex/{p['endpoint']}@{p['host']}",
        "yesterday_limit_up_count": p["total"],
        "sampled_today": len(chgs),
        "avg_change_pct": round(mean(chgs), 2),
        "median_change_pct": round(median(chgs), 2),
        "red_ratio": round(red / len(chgs), 4),
        "promotion_ratio": round(promoted / len(chgs), 4),
        "promoted_count": promoted,
        "nuked_lt_minus7pct_count": nuked,
        "sample": [
            {
                "code": r.get("c"),
                "name": r.get("n"),
                "change_pct": r.get("zdp"),
                "yesterday_boards": r.get("ylbc"),
                "industry": r.get("hybk"),
            }
            for r in rows[:20]
        ],
        "source_scope": "historical_by_date",
    }


def _day_iso(d: str) -> str:
    s = fmt_day(d)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def _fetch_sina_json(url: str) -> list | dict:
    req = urllib.request.Request(url, headers=SINA_UA)
    with urllib.request.urlopen(req, timeout=25) as resp:
        raw = resp.read().decode("utf-8", "replace")
    return json.loads(raw)


def index_sina_day(secid: str, name: str, day: str) -> dict | None:
    """Fallback: Sina daily kline — stable when push2his returns 502."""
    sym = SINA_INDEX.get(secid)
    if not sym:
        return None
    iso = _day_iso(day)
    url = (
        "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?"
        + urllib.parse.urlencode({"symbol": sym, "scale": "240", "ma": "no", "datalen": "20"})
    )
    try:
        rows = _fetch_sina_json(url)
        if not isinstance(rows, list) or not rows:
            return None
        by_day = {r.get("day"): r for r in rows if r.get("day")}
        row = by_day.get(iso)
        if not row:
            return None
        days_sorted = sorted(by_day.keys())
        idx = days_sorted.index(iso)
        prev_close = float(by_day[days_sorted[idx - 1]]["close"]) if idx > 0 else None
        close = float(row["close"])
        open_p = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])
        chg_pct = round((close - prev_close) / prev_close * 100, 2) if prev_close else None
        chg = round(close - prev_close, 2) if prev_close else None
        amp = round((high - low) / prev_close * 100, 2) if prev_close else None
        return {
            "secid": secid,
            "code": secid.split(".")[-1],
            "name": name,
            "date": iso,
            "date_key": fmt_day(day),
            "open": open_p,
            "close": close,
            "high": high,
            "low": low,
            "volume": float(row.get("volume") or 0),
            "amount": None,
            "amplitude_pct": amp,
            "change_pct": chg_pct,
            "change": chg,
            "turnover_pct": None,
            "source_used": f"sina/{sym}",
            "source_scope": "historical_by_date",
        }
    except Exception:  # noqa: BLE001
        return None


def _parse_kline_row(parts: list[str], secid: str, name: str) -> dict:
    d_raw = parts[0]
    d_key = d_raw.replace("-", "")
    return {
        "secid": secid,
        "code": secid.split(".")[-1],
        "name": name,
        "date": d_raw,
        "date_key": d_key,
        "open": float(parts[1]),
        "close": float(parts[2]),
        "high": float(parts[3]),
        "low": float(parts[4]),
        "volume": float(parts[5]),
        "amount": float(parts[6]),
        "amplitude_pct": float(parts[7]),
        "change_pct": float(parts[8]),
        "change": float(parts[9]),
        "turnover_pct": float(parts[10]) if len(parts) > 10 and parts[10] not in ("", "-") else None,
        "source_scope": "historical_by_date",
    }


def load_index_kline_range(beg: str, end: str) -> dict[str, dict[str, dict]]:
    """Fetch once per index for [beg,end], return {secid: {yyyymmdd: row}}."""
    global _KLINE_CACHE
    key_all = (beg, end)
    if key_all in _KLINE_CACHE:
        return _KLINE_CACHE[key_all]

    out: dict[str, dict[str, dict]] = {}
    for secid, name in INDEXES:
        rows_map: dict[str, dict] = {}
        q = (
            "/api/qt/stock/kline/get?"
            + urllib.parse.urlencode(
                {
                    "secid": secid,
                    "fields1": "f1,f2,f3,f4,f5,f6",
                    "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                    "klt": "101",
                    "fqt": "0",
                    "beg": beg,
                    "end": end,
                }
            )
        )
        last_err = None
        for attempt in range(2):
            for host in PUSH2HIS_HOSTS:
                try:
                    data = _read_json(f"https://{host}{q}", timeout=20)
                    klines = (data.get("data") or {}).get("klines") or []
                    for line in klines:
                        parts = line.split(",")
                        row = _parse_kline_row(parts, secid, name)
                        rows_map[row["date_key"]] = row
                    last_err = None
                    break
                except Exception as e:  # noqa: BLE001
                    last_err = e
                _sleep(attempt=attempt)
            if rows_map:
                break
        out[secid] = rows_map
        if not rows_map and last_err:
            out[secid]["_fetch_error"] = str(last_err)
        _sleep(base=0.2)

    _KLINE_CACHE[key_all] = out
    return out


def index_snapshot_ulist() -> dict:
    secids = ",".join(s for s, _ in INDEXES)
    q = f"/api/qt/ulist.np/get?secids={secids}&fields=f2,f3,f6,f12,f14"
    host, data = _fetch_hosts(q, PUSH2_HOSTS, retries=5)
    diff = (data.get("data") or {}).get("diff") or []
    items = list(diff.values() if isinstance(diff, dict) else diff)
    rows = []
    for d in items:
        rows.append(
            {
                "code": d.get("f12"),
                "name": d.get("f14"),
                "point": round((d.get("f2") or 0) / 100, 2),
                "change_pct": round((d.get("f3") or 0) / 100, 2),
                "amount": d.get("f6"),
                "source_scope": "latest_realtime_snapshot",
            }
        )
    by_name = {r["name"]: r for r in rows}
    large = by_name.get("上证50", {}).get("change_pct")
    small = by_name.get("中证2000", {}).get("change_pct")
    spread = round(large - small, 2) if isinstance(large, (int, float)) and isinstance(small, (int, float)) else None
    return {
        "source_used": f"push2/ulist.np@{host}",
        "indices": rows,
        "large_vs_small_spread": spread,
        "source_scope": "latest_realtime_snapshot",
        "warning": "实时指数快照；历史日报告需优先使用 kline 按日数据。",
    }


def index_snapshot(day: str | None = None, kline_range: tuple[str, str] | None = None) -> dict:
    d = fmt_day(day)
    beg, end = kline_range or (d, d)
    cache = load_index_kline_range(beg, end)

    rows = []
    sources = []
    for secid, name in INDEXES:
        sec_rows = cache.get(secid, {})
        if not isinstance(sec_rows, dict):
            sec_rows = {}
        row = sec_rows.get(d)
        if row and "change_pct" in row:
            rows.append({**row, "source_used": row.get("source_used") or "push2his/kline"})
            sources.append(row.get("source_used") or "push2his/kline")
        else:
            sina_row = index_sina_day(secid, name, d)
            if sina_row:
                rows.append(sina_row)
                sources.append(sina_row["source_used"])
            else:
                err = sec_rows.get("_fetch_error") or "no data from push2his or sina"
                rows.append({"secid": secid, "name": name, "_error": err, "source_status": "missing"})

    by_name = {r.get("name"): r for r in rows if "change_pct" in r}
    large = by_name.get("上证50", {}).get("change_pct")
    small = by_name.get("中证2000", {}).get("change_pct")
    spread = round(large - small, 2) if isinstance(large, (int, float)) and isinstance(small, (int, float)) else None

    ok = sum(1 for r in rows if "change_pct" in r)
    result = {
        "date": d,
        "indices": rows,
        "large_vs_small_spread": spread,
        "source_scope": "historical_by_date",
        "source_used": sources[0] if sources else None,
        "coverage": f"{ok}/{len(INDEXES)}",
        "source_mix": sorted(set(sources)),
    }
    # 仅当请求日为「今天」时，才用实时 ulist 补充缺失项（避免历史日误用最新价）
    if ok < len(INDEXES) and d == fmt_day(date.today()):
        live = safe(index_snapshot_ulist)
        if isinstance(live, dict) and live.get("indices"):
            result["live_supplement"] = live
            result["live_supplement_note"] = "仅补充「今日」仍缺失的指数项；非今日历史数据不可用实时价替代。"
    elif ok < len(INDEXES):
        result["recovery_hint"] = "指数K线未完整返回，可重试或 WebSearch 当日收评；勿用实时快照冒充历史。"
    return result


def market_amount(day: str | None = None, kline_range: tuple[str, str] | None = None) -> dict:
    snap = index_snapshot(day, kline_range)
    amount = 0.0
    used = []
    for r in snap.get("indices", []):
        if r.get("name") in ("上证指数", "深证成指") and isinstance(r.get("amount"), (int, float)):
            amount += r["amount"]
            used.append(r["name"])
    # 仅今日允许用 live supplement 估算成交额
    if not used and fmt_day(day) == fmt_day(date.today()):
        live = snap.get("live_supplement") or {}
        for r in live.get("indices", []):
            if r.get("name") in ("上证指数", "深证成指") and isinstance(r.get("amount"), (int, float)):
                amount += r["amount"]
                used.append(r["name"] + "(live)")
    return {
        "date": fmt_day(day),
        "sh_sz_amount_yuan": amount if amount else None,
        "amount_trillion": round(amount / 1e12, 2) if amount else None,
        "components": used,
        "source_scope": "historical_by_date_index_kline",
        "coverage": snap.get("coverage"),
    }


def _clist_page(fs: str, fid: str, fields: str, pn: int, pz: int, po: str = "1") -> dict:
    q = (
        "/api/qt/clist/get?"
        + urllib.parse.urlencode(
            {
                "pn": str(pn),
                "pz": str(pz),
                "po": po,
                "np": "1",
                "fltt": "2",
                "invt": "2",
                "fid": fid,
                "fs": fs,
                "fields": fields,
            }
        )
    )
    host, data = _fetch_hosts(q, PUSH2_HOSTS, retries=4)
    block = data.get("data") or {}
    diff = block.get("diff") or []
    page = list(diff.values() if isinstance(diff, dict) else diff)
    return {"host": host, "total": block.get("total"), "rows": page}


def market_breadth(day: str | None = None, lite: bool = False) -> dict:
    if lite:
        return {
            "requested_date": fmt_day(day),
            "source_scope": "skipped_lite_mode",
            "warning": "lite 模式跳过全市场分页统计；可用涨跌停池侧面观察活跃度。",
        }

    fields = "f12,f14,f3"
    rows: list[dict] = []
    total = None
    host_used = None
    pz = 5000
    pn = 1
    while pn <= 4:
        try:
            page = _clist_page(FS_A, "f12", fields, pn, pz, po="0")
            host_used = page["host"]
            total = page.get("total", total)
            rows.extend(page["rows"])
            if not page["rows"] or (total and len(rows) >= total):
                break
        except Exception as e:  # noqa: BLE001
            if rows:
                break
            return {"_error": str(e), "source_status": "failed"}
        pn += 1
        _sleep(base=0.4)

    chgs = [r.get("f3") for r in rows if isinstance(r.get("f3"), (int, float))]
    up = sum(1 for x in chgs if x > 0)
    down = sum(1 for x in chgs if x < 0)
    flat = sum(1 for x in chgs if x == 0)
    big_up = sum(1 for x in chgs if x >= 5)
    big_down = sum(1 for x in chgs if x <= -5)
    return {
        "requested_date": fmt_day(day),
        "source_used": f"push2/clist@{host_used}",
        "source_scope": "latest_realtime_snapshot",
        "warning": "clist 无 date 参数；仅代表最新快照，不可冒充历史宽度。",
        "total_from_api": total,
        "sampled_stocks": len(chgs),
        "is_complete": total is not None and len(chgs) >= total,
        "up": up,
        "down": down,
        "flat": flat,
        "up_ratio": round(up / len(chgs), 4) if chgs else None,
        "big_up_gt5pct": big_up,
        "big_down_lt5pct": big_down,
    }


def sector_rank(day: str | None = None, sector_type: str = "industry", top: int = 15) -> dict:
    fs = "m:90+t:2" if sector_type == "industry" else "m:90+t:3"
    fields = "f12,f14,f3,f62,f6,f104,f105,f106"

    def slim(rows: list[dict], host: str | None):
        return [
            {
                "code": r.get("f12"),
                "name": r.get("f14"),
                "change_pct": r.get("f3"),
                "main_net_inflow": r.get("f62"),
                "amount": r.get("f6"),
                "up_count": r.get("f104"),
                "down_count": r.get("f105"),
                "flat_count": r.get("f106"),
            }
            for r in rows
        ], host

    try:
        chg_page = _clist_page(fs, "f3", fields, 1, top, po="1")
        flow_page = _clist_page(fs, "f62", fields, 1, top, po="1")
        by_change, h1 = slim(chg_page["rows"], chg_page["host"])
        by_flow, h2 = slim(flow_page["rows"], flow_page["host"])
    except Exception as e:  # noqa: BLE001
        return {"_error": str(e), "source_status": "failed"}

    return {
        "requested_date": fmt_day(day),
        "type": sector_type,
        "source_used": f"push2/clist@{h1},{h2}",
        "source_scope": "latest_realtime_snapshot",
        "warning": "板块排行无 date；历史题材需 WebSearch 或当日实时快照。",
        "by_change_pct": by_change,
        "by_main_inflow": by_flow,
    }


def top_movers(top: int = 10) -> dict:
    fields = "f12,f14,f3,f6,f62"
    try:
        gain = _clist_page(FS_A, "f3", fields, 1, top, po="1")
        loss = _clist_page(FS_A, "f3", fields, 1, top, po="0")
    except Exception as e:  # noqa: BLE001
        return {"_error": str(e), "source_status": "failed"}

    def slim(rows):
        return [{"code": r.get("f12"), "name": r.get("f14"), "change_pct": r.get("f3"), "amount": r.get("f6")} for r in rows]

    return {
        "source_used": f"push2/clist@{gain['host']}",
        "source_scope": "latest_realtime_snapshot",
        "top_gainers": slim(gain["rows"]),
        "top_losers": slim(list(reversed(loss["rows"])) if loss["rows"] else []),
    }


def northbound_flow(days: int = 5) -> dict:
    """Datacenter — usually more stable than push2 for fund flow history."""
    params = {
        "sortColumns": "TRADE_DATE",
        "sortTypes": "-1",
        "pageSize": str(max(days, 5)),
        "pageNumber": "1",
        "reportName": "RPT_MUTUAL_DEAL_HISTORY",
        "columns": "ALL",
        "source": "WEB",
        "client": "WEB",
        "filter": '(MUTUAL_TYPE="005")',  # 北向资金
    }
    url = DC + "?" + urllib.parse.urlencode(params)
    try:
        data = _fetch_url(url, retries=4)
        rows = (data.get("result") or {}).get("data") or []
    except Exception as e:  # noqa: BLE001
        return {"_error": str(e), "source_status": "failed"}

    out = []
    for r in rows[:days]:
        out.append(
            {
                "date": (r.get("TRADE_DATE") or "")[:10],
                "net_deal_amt": r.get("NET_DEAL_AMT"),
                "buy_amt": r.get("BUY_AMT"),
                "sell_amt": r.get("SELL_AMT"),
                "fund_inflow": r.get("FUND_INFLOW"),
                "hold_market_cap": r.get("HOLD_MARKET_CAP"),
            }
        )
    return {
        "source_used": "datacenter/RPT_MUTUAL_DEAL_HISTORY",
        "source_scope": "historical_by_date",
        "type": "北向资金",
        "history": out,
    }


def datacenter_margin_summary(days: int = 5) -> dict:
    params = {
        "sortColumns": "DIM_DATE",
        "sortTypes": "-1",
        "pageSize": str(max(days, 5)),
        "pageNumber": "1",
        "reportName": "RPTA_RZRQ_LSHJ",
        "columns": "ALL",
        "source": "WEB",
        "client": "WEB",
    }
    url = DC + "?" + urllib.parse.urlencode(params)
    try:
        data = _fetch_url(url, retries=3)
        if not data.get("success"):
            raise RuntimeError(data.get("message") or "datacenter failed")
        rows = (data.get("result") or {}).get("data") or []
    except Exception as e:  # noqa: BLE001
        return {"_error": str(e), "source_status": "failed", "note": "融资融券汇总接口可能变更，失败时不影响主报告。"}

    hist = []
    for r in rows[:days]:
        hist.append(
            {
                "date": (r.get("DIM_DATE") or r.get("DATE") or "")[:10],
                "rzrqye": r.get("RZRQYE") or r.get("RZRQYE_SUM"),
                "rzye": r.get("RZYE"),
                "rqye": r.get("RQYE"),
            }
        )
    return {"source_used": "datacenter/RPTA_RZRQ_LSHJ", "source_scope": "historical_by_date", "history": hist}


def emotion_score(day_bundle: dict) -> dict:
    zt = day_bundle.get("limit_up", {}) or {}
    dt = day_bundle.get("limit_down", {}) or {}
    zb = day_bundle.get("opened_board", {}) or {}
    yz = day_bundle.get("yesterday_zt_today", {}) or {}
    breadth = day_bundle.get("breadth", {}) or {}

    zt_count = zt.get("limit_up_count") or 0
    dt_count = dt.get("limit_down_count") or 0
    touched = zt_count + (zb.get("opened_board_count") or 0)
    seal_rate = zt_count / touched if touched else None
    break_rate = 1 - seal_rate if seal_rate is not None else None
    max_boards = zt.get("max_consecutive_boards") or 0
    avg_yz = yz.get("avg_change_pct") or 0
    red = yz.get("red_ratio") or 0.5
    up_ratio = breadth.get("up_ratio")

    score = 20.0
    score += min(zt_count / 100, 1.2) * 20
    score += min(max_boards / 5, 1) * 15
    if seal_rate is not None:
        score += seal_rate * 15
    score += max(min(avg_yz, 5), -5) / 5 * 15
    score += red * 10
    score -= min(dt_count / 20, 1.5) * 10
    if isinstance(up_ratio, (int, float)):
        score += (up_ratio - 0.5) * 10
    score = max(0, min(100, round(score, 1)))

    if score >= 78:
        stage = "高潮"
    elif score >= 63:
        stage = "分歧" if (break_rate or 0) >= 0.48 else "发酵"
    elif score >= 48:
        stage = "分歧" if (break_rate or 0) >= 0.45 else "修复/启动"
    elif score >= 33:
        stage = "分歧/退潮"
    else:
        stage = "冰点/退潮末"
    return {
        "score": score,
        "stage": stage,
        "seal_rate": round(seal_rate, 4) if seal_rate is not None else None,
        "break_rate": round(break_rate, 4) if break_rate is not None else None,
    }


def _fetch_status(bundle: dict) -> dict:
    dims = [
        "indices", "amount", "limit_up", "limit_down", "opened_board", "zt_ladder",
        "yesterday_zt_today", "breadth", "sectors_industry", "sectors_concept",
        "strong_pool", "top_movers", "northbound", "margin",
    ]
    ok, fail, skip = [], [], []
    for k in dims:
        v = bundle.get(k)
        if not v:
            skip.append(k)
        elif isinstance(v, dict) and (v.get("_error") or v.get("source_status") == "failed"):
            fail.append(k)
        elif isinstance(v, dict) and v.get("source_scope", "").startswith("skipped"):
            skip.append(k)
        else:
            ok.append(k)
    return {"ok": ok, "failed": fail, "skipped": skip, "coverage_pct": round(100 * len(ok) / max(len(dims) - len(skip), 1), 1)}


def daily_snapshot(
    day: str | None = None,
    include_live: bool = True,
    lite: bool = False,
    kline_range: tuple[str, str] | None = None,
    include_flow: bool = True,
) -> dict:
    d = fmt_day(day)
    bundle: dict = {
        "date": d,
        "indices": safe(index_snapshot, d, kline_range),
        "amount": safe(market_amount, d, kline_range),
        "limit_up": safe(limit_up_pool, d),
        "limit_down": safe(limit_down_pool, d),
        "opened_board": safe(opened_board_pool, d),
        "zt_ladder": safe(zt_ladder, d),
        "yesterday_zt_today": safe(yesterday_zt_today, d),
        "strong_pool": safe(strong_pool, d),
    }
    if include_live:
        bundle["breadth"] = safe(market_breadth, d, lite)
        bundle["sectors_industry"] = safe(sector_rank, d, "industry", 12)
        bundle["sectors_concept"] = safe(sector_rank, d, "concept", 12)
        bundle["top_movers"] = safe(top_movers, 10)
        if d == fmt_day(date.today()):
            bundle["indices_live"] = safe(index_snapshot_ulist)
    else:
        bundle["breadth"] = {"requested_date": d, "source_scope": "skipped_historical_day"}
        bundle["sectors_industry"] = {"requested_date": d, "source_scope": "skipped_historical_day"}
        bundle["sectors_concept"] = bundle["sectors_industry"]

    if include_flow:
        bundle["northbound"] = safe(northbound_flow, 5)
        bundle["margin"] = safe(datacenter_margin_summary, 5)

    bundle["emotion"] = emotion_score(bundle)
    bundle["fetch_status"] = _fetch_status(bundle)
    return bundle


def multi_day(days: int, end_day: str | None = None, lite: bool = False) -> dict:
    dates = trading_weekdays(days, end_day)
    ds = [fmt_day(d) for d in dates]
    kline_range = (ds[0], ds[-1])
    load_index_kline_range(ds[0], ds[-1])

    history = []
    for i, d in enumerate(ds):
        is_last = i == len(ds) - 1
        history.append(
            safe(
                daily_snapshot,
                d,
                include_live=is_last,
                lite=lite,
                kline_range=kline_range,
                include_flow=is_last,
            )
        )
        _sleep(base=0.25)

    industry_counts: Counter[str] = Counter()
    for item in history:
        for row in (item.get("limit_up", {}) or {}).get("industry_limit_up_top", []):
            industry_counts[row["name"]] += 1

    return {
        "start_date": ds[0],
        "end_date": ds[-1],
        "days": days,
        "history": history,
        "limit_up_industry_continuity": [{"name": k, "appeared_days": v} for k, v in industry_counts.most_common(12)],
        "northbound": safe(northbound_flow, days + 2),
        "data_sources": {
            "pools": "push2ex (date=YYYYMMDD)",
            "indices_history": "push2his kline range + push2 ulist live fallback",
            "breadth_sectors": "push2 clist (live only, end day)",
            "northbound_margin": "datacenter-web",
        },
        "fetch_status": _fetch_status(history[-1] if history else {}),
    }


def main():
    parser = argparse.ArgumentParser(description="Multi-source A-share market snapshot")
    parser.add_argument("--date", default="", help="YYYYMMDD")
    parser.add_argument("--days", type=int, default=0, help="Last N weekdays ending at --date")
    parser.add_argument("--no-live", action="store_true", help="Skip live clist breadth/sectors")
    parser.add_argument("--lite", action="store_true", help="Skip slow breadth pagination")
    args = parser.parse_args()

    if args.days and args.days > 1:
        out = multi_day(args.days, args.date or None, lite=args.lite)
    else:
        out = daily_snapshot(
            args.date or None,
            include_live=not args.no_live,
            lite=args.lite,
            include_flow=True,
        )
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
