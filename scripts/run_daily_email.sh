#!/usr/bin/env bash
# 拉数 → DeepSeek 复盘 → PDF → 仅邮件发送 PDF（不附 Markdown）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DATE="${1:-$(TZ=Asia/Shanghai date +%Y%m%d)}"
STAMP="${DATE:0:4}-${DATE:4:2}-${DATE:6:2}"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

OUT_MD="$ROOT/A股盘面复盘_${STAMP}.md"
OUT_QUANT="$ROOT/A股盘面复盘_${STAMP}_定量.md"
OUT_PDF="$ROOT/A股盘面复盘_${STAMP}.pdf"

if [[ -n "${DEEPSEEK_API_KEY:-}${OPENAI_API_KEY:-}" ]]; then
  echo "Using DeepSeek LLM review..."
  python3 "$ROOT/scripts/generate_llm_review.py" --date "$DATE" -o "$OUT_MD"
  SRC_MD="$OUT_MD"
else
  echo "No DEEPSEEK_API_KEY; quantitative fallback."
  python3 "$ROOT/scripts/generate_daily_quant_review.py" --date "$DATE" -o "$OUT_QUANT"
  SRC_MD="$OUT_QUANT"
fi

echo "Converting to PDF..."
python3 "$ROOT/scripts/md_to_pdf.py" "$SRC_MD" -o "$OUT_PDF"

if [[ -z "${SMTP_USER:-}" || -z "${SMTP_PASS:-}" || -z "${EMAIL_TO:-}" ]]; then
  echo "SMTP not configured; PDF saved: $OUT_PDF"
  exit 0
fi

python3 "$ROOT/scripts/send_report_email.py" "$OUT_PDF" \
  --subject "A股盘面复盘 ${STAMP}" \
  --body "附件为 PDF 复盘。仅供研究，不构成投资建议。"
