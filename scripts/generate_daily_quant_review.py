#!/usr/bin/env python3
"""Generate a quantitative A-share daily review markdown (no LLM).

Uses scripts/fetch_market_data.py --days 7. Output follows the project's
「执行优先」skeleton in a compact form suitable for email.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
FETCH = ROOT / "scripts" / "fetch_market_data.py"
TZ = ZoneInfo("Asia/Shanghai")


def run_fetch(date: str, days: int = 7) -> dict:
    cmd = [sys.executable, str(FETCH), "--days", str(days), "--date", date]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"fetch failed: {proc.stderr[-2000:] or proc.stdout[-2000:]}")
    return json.loads(proc.stdout)


def cluster(name: str | None) -> str:
    if not name:
        return "其他"
    rules = [
        ("半导体", "硬科技"), ("元件", "硬科技"), ("光学光电", "硬科技"),
        ("通信设备", "硬科技"), ("消费电子", "硬科技"), ("软件开发", "硬科技"),
        ("化学制药", "医药"), ("医疗服务", "医药"), ("医疗器械", "医药"), ("中药", "医药"),
        ("汽车零部", "汽车链"), ("电网设备", "电力设备"), ("白酒", "大消费"),
        ("影视", "大消费"), ("化学制品", "周期化工"),
    ]
    for k, v in rules:
        if k in name:
            return v
    return f"其他:{name}"


def build_md(data: dict, trade_date: str) -> str:
    hist = data["history"]
    h = hist[-1]
    prev = hist[-2] if len(hist) >= 2 else None
    em = h.get("emotion") or {}
    lu = h.get("limit_up") or {}
    ld = h.get("limit_down") or {}
    yz = h.get("yesterday_zt_today") or {}
    zt = h.get("zt_ladder") or {}
    amt = h.get("amount") or {}
    ob = h.get("opened_board") or {}

    tops = [(t["name"], t["count"]) for t in (lu.get("industry_limit_up_top") or [])[:5]]
    top1 = tops[0][0] if tops else None
    prev_top1 = None
    if prev:
        pt = (prev.get("limit_up") or {}).get("industry_limit_up_top") or []
        prev_top1 = pt[0]["name"] if pt else None

    # crude labels
    c_today = cluster(top1)
    c_prev = cluster(prev_top1) if prev_top1 else None
    switch = bool(c_prev and c_today != c_prev and prev and (prev.get("limit_up") or {}).get("limit_up_count", 0) >= 60)
    established = False
    if top1:
        consec = 0
        for row in reversed(hist):
            tlist = (row.get("limit_up") or {}).get("industry_limit_up_top") or []
            names = [x["name"] for x in tlist[:3]]
            if any(cluster(n) == c_today for n in names):
                consec += 1
            else:
                break
        established = consec >= 3 and not switch

    if established:
        main_line = f"确立倾向：{c_today}（近窗同簇连续）"
        candidate = "—"
        retired = "—"
    elif switch:
        main_line = "无确立主线"
        retired = f"退潮确认倾向：{c_prev}"
        candidate = f"观察候选：{c_today}（切换首日不升格）"
    else:
        main_line = "无确立主线（定量粗判）"
        retired = "—"
        candidate = f"相对最强：{c_today}（待人工确认是否候选）"

    idx_lines = []
    for i in (h.get("indices") or {}).get("indices") or []:
        idx_lines.append(f"| {i.get('name')} | {i.get('change_pct')} |")

    ladder = zt.get("ladder_counts") or {}
    top_names = zt.get("top_names") or {}

    traj = []
    for row in hist[-7:]:
        t = (row.get("limit_up") or {}).get("industry_limit_up_top") or []
        top3 = ",".join(f"{x['name']}{x['count']}" for x in t[:3])
        e = row.get("emotion") or {}
        y = (row.get("yesterday_zt_today") or {}).get("avg_change_pct")
        traj.append(f"| {row.get('date')} | {top3} | {e.get('score')} / {e.get('stage')} | yzt={y} |")

    tomorrow = (datetime.now(TZ).date()).isoformat()
    # next business day rough: just say T+1
    md = f"""# A股盘面复盘（定量稿）{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}

> **类型**：自动定量稿（无 LLM 叙事）  
> **生成**：{datetime.now(TZ).strftime('%Y-%m-%d %H:%M')} Asia/Shanghai  
> **说明**：主线标签为脚本粗判，正式口径仍以人工/Agent 复盘为准。近窗样本用于**验证逻辑**，不作永久军规。  
> **免责声明**：仅供研究参考，不构成投资建议。

---

## 摘要

情绪 **{em.get('score')} / {em.get('stage')}**；涨停 **{lu.get('limit_up_count')}** / 跌停 **{ld.get('limit_down_count')}** / 炸板 **{ob.get('opened_board_count')}**；封板率约 **{em.get('seal_rate')}**；昨涨停均收益 **{yz.get('avg_change_pct')}%**；成交约 **{amt.get('amount_trillion')}** 万亿。

| 三行 | 粗判 |
|---|---|
| 确立主线 | {main_line} |
| 退潮确认 | {retired} |
| 观察候选 | {candidate} |

---

## 一、策略卡（定量）

| 项 | 值 |
|---|---|
| 情绪 | {em.get('score')} / {em.get('stage')} |
| 赚钱效应 | yzt={yz.get('avg_change_pct')} 红盘率={yz.get('red_ratio')} 晋级={yz.get('promotion_ratio')} 大面={yz.get('nuked_lt_minus7pct_count')} |
| 最高板 | {zt.get('max_boards')} |
| 今日行业 Top | {tops} |
| 昨 Top1→今 Top1 | {prev_top1} → {top1} |
| 切换粗判 | {"是" if switch else "否"} |

---

## 二、明日操作提示（模板）

> 自动稿只给检查清单；完整 A–E 预案请在 Agent 复盘中展开。

```text
现金优先；同时最多 1 个方向
若切换粗判=是：空旧方向，新方向最多试错，不叫确立主线
收盘三问：有无确立？退潮是否仍成立？候选升级/否决/噪音？
下一交易日关注：昨涨停组表现、跌停是否扩散、Top 题材是否连续
```

---

## 三、指数

| 指数 | 涨跌% |
|---|---:|
{chr(10).join(idx_lines) if idx_lines else "| （无） | |"}

---

## 四、连板

| 高度 | 家数 | 代表 |
|---|---|---|
"""
    for k in sorted(ladder.keys(), key=lambda x: int(x), reverse=True):
        names = ",".join((top_names.get(str(k)) or top_names.get(k) or [])[:5])
        md += f"| {k} | {ladder[k]} | {names} |\n"

    md += f"""

---

## 五、近窗轨迹（验证用）

| 日期 | Top3 | 情绪 | yzt |
|---|---|---|---|
{chr(10).join(traj)}

---

## 数据

`--date {trade_date}` + `--days 7`；fetch_status={json.dumps(h.get('fetch_status') or data.get('fetch_status'), ensure_ascii=False)}
"""
    return md


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(TZ).strftime("%Y%m%d"))
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("-o", "--output", default="")
    args = ap.parse_args()

    data = run_fetch(args.date, args.days)
    md = build_md(data, args.date)
    out = Path(args.output) if args.output else ROOT / f"A股盘面复盘_{args.date[:4]}-{args.date[4:6]}-{args.date[6:]}_定量.md"
    out.write_text(md, encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
