#!/usr/bin/env bash
# fetch → review → PDF → email (PDF only)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DATE="${1:-$(TZ=Asia/Shanghai date +%Y%m%d)}"
STAMP="${DATE:0:4}-${DATE:4:2}-${DATE:6:2}"
OUT_DIR="$ROOT/output"
mkdir -p "$OUT_DIR"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

OUT_MD="$OUT_DIR/A股盘面复盘_${STAMP}.md"
OUT_QUANT="$OUT_DIR/A股盘面复盘_${STAMP}_定量.md"
OUT_PDF="$OUT_DIR/A股盘面复盘_${STAMP}.pdf"

if [[ -n "${DEEPSEEK_API_KEY:-}${OPENAI_API_KEY:-}" ]]; then
  python3 "$ROOT/scripts/generate_llm_review.py" --date "$DATE" -o "$OUT_MD"
  SRC_MD="$OUT_MD"
else
  python3 "$ROOT/scripts/generate_quant_review.py" --date "$DATE" -o "$OUT_QUANT"
  SRC_MD="$OUT_QUANT"
fi

python3 "$ROOT/scripts/md_to_pdf.py" "$SRC_MD" -o "$OUT_PDF"
rm -f "$SRC_MD"

if [[ -z "${SMTP_USER:-}" || -z "${SMTP_PASS:-}" || -z "${EMAIL_TO:-}" ]]; then
  echo "PDF saved: $OUT_PDF"
  exit 0
fi

python3 "$ROOT/scripts/send_email.py" "$OUT_PDF" \
  --subject "A股盘面复盘 ${STAMP}" \
  --body "附件为 PDF 复盘。仅供研究，不构成投资建议。"
