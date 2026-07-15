#!/usr/bin/env bash
# 本地一键：拉数 → 定量复盘 md → 发邮
# 用法：./scripts/run_daily_email.sh [YYYYMMDD]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DATE="${1:-$(TZ=Asia/Shanghai date +%Y%m%d)}"

python3 "$ROOT/scripts/generate_daily_quant_review.py" --date "$DATE"
OUT="$ROOT/A股盘面复盘_${DATE:0:4}-${DATE:4:2}-${DATE:6:2}_定量.md"

# 若已有人工/Agent 正式稿，优先附上正式稿
HUMAN="$ROOT/A股盘面复盘_${DATE:0:4}-${DATE:4:2}-${DATE:6:2}.md"
PDF="$ROOT/A股盘面复盘_${DATE:0:4}-${DATE:4:2}-${DATE:6:2}.pdf"
FILES=("$OUT")
[[ -f "$HUMAN" ]] && FILES+=("$HUMAN")
[[ -f "$PDF" ]] && FILES+=("$PDF")

python3 "$ROOT/scripts/send_report_email.py" "${FILES[@]}" \
  --subject "A股盘面复盘 ${DATE:0:4}-${DATE:4:2}-${DATE:6:2}" \
  --body "自动发送：定量稿必附；若存在正式 md/pdf 一并附上。仅供研究，不构成投资建议。"
