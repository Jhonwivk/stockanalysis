#!/usr/bin/env bash
# Install / uninstall local launchd schedule for daily A-share review (08:30 local time).
set -euo pipefail

LABEL="com.stockanalysis.daily-review"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_DST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="${HOME}/Library/Logs"
LOG_FILE="${LOG_DIR}/stockanalysis-daily-review.log"
TEMPLATE="${REPO}/scripts/${LABEL}.plist"
UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}"

resolve_runner() {
  if [[ -x "${REPO}/scripts/run_daily_email.sh" ]]; then
    echo "run_daily_email.sh"
  elif [[ -x "${REPO}/scripts/run_daily.sh" ]]; then
    echo "run_daily.sh"
  else
    echo "error: neither scripts/run_daily_email.sh nor scripts/run_daily.sh found (executable)" >&2
    exit 1
  fi
}

uninstall() {
  if launchctl print "${DOMAIN}/${LABEL}" &>/dev/null; then
    launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
  fi
  # Legacy load/unload fallback
  if [[ -f "$PLIST_DST" ]]; then
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    rm -f "$PLIST_DST"
  fi
  echo "Uninstalled ${LABEL}."
  echo "Log kept at: ${LOG_FILE}"
}

install() {
  if [[ ! -f "$TEMPLATE" ]]; then
    echo "error: missing template $TEMPLATE" >&2
    exit 1
  fi
  RUNNER="$(resolve_runner)"
  mkdir -p "${HOME}/Library/LaunchAgents" "$LOG_DIR"
  touch "$LOG_FILE"

  # Local timezone name (e.g. Asia/Shanghai); StartCalendarInterval uses Mac local clock
  TZ_NAME="$(readlink /etc/localtime 2>/dev/null | sed 's|.*/zoneinfo/||' || true)"
  if [[ -z "${TZ_NAME}" ]]; then
    TZ_NAME="Asia/Shanghai"
  fi

  # Unload existing before replace
  if launchctl print "${DOMAIN}/${LABEL}" &>/dev/null; then
    launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
  fi
  launchctl unload "$PLIST_DST" 2>/dev/null || true

  sed -e "s|__REPO__|${REPO}|g" \
      -e "s|__HOME__|${HOME}|g" \
      -e "s|__RUNNER__|${RUNNER}|g" \
      -e "s|__TZ__|${TZ_NAME}|g" \
      "$TEMPLATE" > "$PLIST_DST"

  if ! plutil -lint "$PLIST_DST" >/dev/null; then
    echo "error: generated plist invalid" >&2
    plutil -lint "$PLIST_DST" || true
    exit 1
  fi

  launchctl bootstrap "$DOMAIN" "$PLIST_DST"
  launchctl enable "${DOMAIN}/${LABEL}" 2>/dev/null || true
  # Kick so it's registered; does not force a full review run unless you want — skip RunAtLoad
  launchctl print "${DOMAIN}/${LABEL}" >/dev/null

  echo "Installed ${LABEL}"
  echo "  Schedule : every day 08:30 (Mac local timezone: ${TZ_NAME})"
  echo "  Script   : ${REPO}/scripts/${RUNNER}"
  echo "  Plist    : ${PLIST_DST}"
  echo "  Log      : ${LOG_FILE}"
  echo "  Uninstall: $0 uninstall"
}

usage() {
  cat <<USAGE
Usage: $0 [install|uninstall]
  install    (default) Install LaunchAgent for daily 08:30 local run
  uninstall  Remove LaunchAgent
USAGE
}

case "${1:-install}" in
  install) uninstall >/dev/null 2>&1 || true; install ;;
  uninstall) uninstall ;;
  -h|--help|help) usage ;;
  *) usage; exit 1 ;;
esac
