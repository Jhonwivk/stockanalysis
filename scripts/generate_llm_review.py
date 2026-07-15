#!/usr/bin/env python3
"""Generate full A-share daily review via DeepSeek (OpenAI-compatible API).

Uses prompts/report-template.md + prompts/writing-rules.md.
No Cursor/Claude Skill required.

Env:
  DEEPSEEK_API_KEY   required for LLM path
  DEEPSEEK_BASE_URL  default https://api.deepseek.com
  DEEPSEEK_MODEL     default deepseek-chat
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
FETCH = ROOT / "scripts" / "fetch_market_data.py"
TEMPLATE = ROOT / "prompts" / "report-template.md"
RULES = ROOT / "prompts" / "writing-rules.md"
TZ = ZoneInfo("Asia/Shanghai")


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def run_fetch(date: str, days: int = 7) -> dict:
    cmd = [sys.executable, str(FETCH), "--days", str(days), "--date", date]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"fetch failed: {proc.stderr[-2000:] or proc.stdout[-2000:]}")
    return json.loads(proc.stdout)


def slim_day(h: dict) -> dict:
    lu = h.get("limit_up") or {}
    ld = h.get("limit_down") or {}
    yz = h.get("yesterday_zt_today") or {}
    zt = h.get("zt_ladder") or {}
    em = h.get("emotion") or {}
    ob = h.get("opened_board") or {}
    amt = h.get("amount") or {}
    indices = []
    for i in (h.get("indices") or {}).get("indices") or []:
        indices.append({"name": i.get("name"), "change_pct": i.get("change_pct"), "close": i.get("close")})
    # sectors may be live snapshot
    si = h.get("sectors_industry") or {}
    strong = []
    for x in (si.get("by_change_pct") or [])[:8]:
        strong.append({"name": x.get("name"), "change_pct": x.get("change_pct")})
    inflow = []
    for x in (si.get("by_main_inflow") or [])[:6]:
        inflow.append({"name": x.get("name"), "change_pct": x.get("change_pct"), "main_net_inflow": x.get("main_net_inflow")})
    ld_sample = []
    for s in (ld.get("sample") or [])[:15]:
        ld_sample.append({"name": s.get("name"), "industry": s.get("industry")})
    return {
        "date": h.get("date"),
        "emotion": em,
        "limit_up_count": lu.get("limit_up_count"),
        "limit_down_count": ld.get("limit_down_count"),
        "opened_board_count": ob.get("opened_board_count"),
        "industry_limit_up_top": lu.get("industry_limit_up_top"),
        "yesterday_zt_today": {
            "avg_change_pct": yz.get("avg_change_pct"),
            "red_ratio": yz.get("red_ratio"),
            "promotion_ratio": yz.get("promotion_ratio"),
            "nuked_lt_minus7pct_count": yz.get("nuked_lt_minus7pct_count"),
            "yesterday_limit_up_count": yz.get("yesterday_limit_up_count"),
        },
        "zt_ladder": {
            "max_boards": zt.get("max_boards"),
            "ladder_counts": zt.get("ladder_counts"),
            "top_names": zt.get("top_names"),
        },
        "amount_trillion": amt.get("amount_trillion"),
        "indices": indices,
        "sectors_strong": strong,
        "sectors_inflow": inflow,
        "limit_down_sample": ld_sample,
    }


def build_context_pack(data: dict) -> dict:
    hist = [slim_day(h) for h in data.get("history") or []]
    return {
        "window": {"start": data.get("start_date"), "end": data.get("end_date"), "days": data.get("days")},
        "history": hist,
        "limit_up_industry_continuity": data.get("limit_up_industry_continuity"),
        "note": "板块排行多为最新快照；池类按日期。禁止把当日涨停冠军直接写成确立主线。",
    }


SYSTEM_PROMPT = """你是 A 股短线盘面复盘助手。必须严格按用户提供的「报告模板」章节顺序与标题输出完整 Markdown 报告。

硬性规则（违反则不合格）：
1. 主线三行制：确立主线 / 退潮确认 / 观察候选+脉冲；禁止「今日主线=涨停冠军」。
2. 切换日：只确认旧方向退潮；新方向当日再强也只能写「主线候选」，不得写「主线切换完成」「新确立主线」。
3. 白酒/影视等一日强 = 脉冲，不配主仓。
4. §二 明日推演至少 A–E 多预案，含时间窗、仓位上下限、收盘三问。
5. §三 含暗流表与环境变化触发表。
6. 事实与推断分离；缺数据写「不可得」，禁止臆造涨停家数等量化字段——必须使用 JSON 中的数。
7. 中文、正式、简洁；免责声明保留。
8. 只输出报告正文 Markdown，不要用 ```markdown 包裹全文。
"""


def call_deepseek(messages: list[dict], *, api_key: str, base_url: str, model: str) -> str:
    url = base_url.rstrip("/") + "/v1/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 8192,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek HTTP {e.code}: {err[:1500]}") from e
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"unexpected response: {json.dumps(body, ensure_ascii=False)[:1500]}") from e


def strip_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1]
        if t.endswith("```"):
            t = t[: t.rfind("```")]
    return t.strip()


def main() -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(TZ).strftime("%Y%m%d"))
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("-o", "--output", default="")
    args = ap.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("Missing DEEPSEEK_API_KEY (or OPENAI_API_KEY). Put it in .env or Actions secrets.")

    base_url = os.environ.get("DEEPSEEK_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "https://api.deepseek.com"
    model = os.environ.get("DEEPSEEK_MODEL") or os.environ.get("OPENAI_MODEL") or "deepseek-chat"

    print(f"fetch market data {args.date} ...", flush=True)
    data = run_fetch(args.date, args.days)
    pack = build_context_pack(data)
    if not TEMPLATE.exists() or not RULES.exists():
        raise SystemExit(f"missing prompts: {TEMPLATE.name} / {RULES.name}")

    template = TEMPLATE.read_text(encoding="utf-8")
    rules = RULES.read_text(encoding="utf-8")

    trade_fmt = f"{args.date[:4]}-{args.date[4:6]}-{args.date[6:]}"
    user_prompt = f"""请根据下列量化数据包，撰写「{trade_fmt}」的完整 A 股盘面复盘。

# 报告模板（必须遵循结构）
{template}

# 写作规则（§一/二/三仓位与手法必须映射）
{rules}

# 量化数据包（唯一事实来源）
```json
{json.dumps(pack, ensure_ascii=False)}
```

文首注明：自动复盘；数据截至收盘。仅输出报告正文。
"""

    print(f"calling {model} @ {base_url} ...", flush=True)
    content = call_deepseek(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    md = strip_fence(content)
    out_dir = ROOT / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = Path(args.output) if args.output else out_dir / f"A股盘面复盘_{trade_fmt}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md + "\n", encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
