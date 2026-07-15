#!/usr/bin/env bash
# 本地/CI：拉数 → DeepSeek 完整复盘 → 发邮（无 Key 则回退定量稿）
# 用法：./scripts/run_daily_email.sh [YYYYMMDD]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DATE="${1:-$(TZ=Asia/Shanghai date +%Y%m%d)}"
STAMP="${DATE:0:4}-${DATE:4:2}-${DATE:6:2}"

# load .env if present
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

OUT_LLM="$ROOT/A股盘面复盘_${STAMP}.md"
OUT_QUANT="$ROOT/A股盘面复盘_${STAMP}_定量.md"
PRIMARY=""

if [[ -n "${DEEPSEEK_API_KEY:-}${OPENAI_API_KEY:-}" ]]; then
  echo "Using DeepSeek/OpenAI-compatible LLM review..."
  python3 "$ROOT/scripts/generate_llm_review.py" --date "$DATE" -o "$OUT_LLM"
  PRIMARY="$OUT_LLM"
else
  echo "No DEEPSEEK_API_KEY; fallback quantitative review."
  python3 "$ROOT/scripts/generate_daily_quant_review.py" --date "$DATE" -o "$OUT_QUANT"
  PRIMARY="$OUT_QUANT"
fi

PDF="$ROOT/A股盘面复盘_${STAMP}.pdf"
FILES=("$PRIMARY")
# also attach quant snapshot if LLM ran
if [[ "$PRIMARY" == "$OUT_LLM" && -f "$OUT_QUANT" ]]; then
  :
fi
if [[ -f "$PDF" ]]; then
  FILES+=("$PDF")
fi

if [[ -z "${SMTP_USER:-}" || -z "${SMTP_PASS:-}" || -z "${EMAIL_TO:-}" ]]; then
  echo "SMTP not configured; report saved: $PRIMARY"
  exit 0
fi

python3 "$ROOT/scripts/send_report_email.py" "${FILES[@]}" \
  --subject "A股盘面复盘 ${STAMP}" \
  --body "自动复盘（优先 DeepSeek 完整稿；无 Key 则为定量稿）。仅供研究，不构成投资建议。"
