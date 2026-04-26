#!/usr/bin/env bash
# Install (or remove) a launchd job that runs reflect_bank.py weekly.
#
# Default schedule: Sundays at 03:00 local time. Reflects each bank listed
# in ~/.hindsight/known-banks.txt and retains the synthesis back into the bank.
#
# Usage:
#   bash install_launchd.sh                  # install
#   bash install_launchd.sh --uninstall      # remove
#   bash install_launchd.sh --weekday 2      # Tuesday (0=Sun..6=Sat per launchd)
#   bash install_launchd.sh --hour 9
#
# Logs:
#   ~/.hindsight/reflect.out.log
#   ~/.hindsight/reflect.err.log

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="com.kevinhill.review-with-memory.reflect"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
BANKS_FILE="$HOME/.hindsight/known-banks.txt"
LOG_DIR="$HOME/.hindsight"

WEEKDAY=0
HOUR=3
UNINSTALL=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --weekday) WEEKDAY="$2"; shift 2 ;;
    --hour) HOUR="$2"; shift 2 ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ $UNINSTALL -eq 1 ]]; then
  if [[ -f "$PLIST" ]]; then
    launchctl unload "$PLIST" 2>/dev/null || true
    rm "$PLIST"
    echo "uninstalled $LABEL"
  else
    echo "$LABEL not installed"
  fi
  exit 0
fi

mkdir -p "$LOG_DIR" "$(dirname "$PLIST")"
if [[ ! -f "$BANKS_FILE" ]]; then
  cat > "$BANKS_FILE" <<EOF
# One Hindsight bank ID per line. Lines starting with # are ignored.
# Default per-project format from the Claude Code plugin: kh-::<repo-name>
kh-::coding-toolbelt
EOF
  echo "created $BANKS_FILE — edit to add more banks"
fi

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$SCRIPT_DIR/reflect_bank.py</string>
    <string>--banks-file</string>
    <string>$BANKS_FILE</string>
    <string>--window</string>
    <string>weekly</string>
    <string>--budget</string>
    <string>mid</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key>
    <integer>$WEEKDAY</integer>
    <key>Hour</key>
    <integer>$HOUR</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/reflect.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/reflect.err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "installed $LABEL"
echo "  schedule: weekday=$WEEKDAY (0=Sun) hour=$HOUR"
echo "  banks:    $BANKS_FILE"
echo "  logs:     $LOG_DIR/reflect.out.log, $LOG_DIR/reflect.err.log"
echo
echo "To run once now:"
echo "  $SCRIPT_DIR/reflect_bank.py --banks-file $BANKS_FILE --window weekly"
