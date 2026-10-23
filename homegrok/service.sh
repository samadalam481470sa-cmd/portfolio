#!/bin/sh
# Run HomeGrok in the background on macOS (launchd): starts at login, restarts if it crashes.
#   ./service.sh install [--port 8000]   start the web server + the autopilot (24/7 learning)
#   ./service.sh uninstall               stop and remove both
#   ./service.sh status                  show whether they are running
#   ./service.sh logs                    follow their output
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
LOGS="$DIR/workspace/logs"
PORT=8000
[ "$2" = "--port" ] && PORT="$3"

plist() { # label, nice, program, args...
  label="$1"; nice="$2"; prog="$3"; shift 3
  args=""
  for a in "$@"; do args="$args<string>$a</string>"; done
  cat > "$AGENTS/$label.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key><array><string>/usr/bin/caffeinate</string><string>-is</string><string>$prog</string>$args</array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>LANG</key><string>en_US.UTF-8</string>
    <key>PYTHONUNBUFFERED</key><string>1</string>
    <key>OLLAMA_KEEP_ALIVE</key><string>${OLLAMA_KEEP_ALIVE:-5m}</string>
    <key>OLLAMA_MAX_LOADED_MODELS</key><string>1</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>SoftResourceLimits</key><dict><key>NumberOfFiles</key><integer>4096</integer></dict>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>Nice</key><integer>$nice</integer>
  <key>StandardOutPath</key><string>$LOGS/$label.log</string>
  <key>StandardErrorPath</key><string>$LOGS/$label.log</string>
</dict></plist>
EOF
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  # launchd needs a moment to finish stopping the old copy before it accepts the new one.
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    launchctl print "gui/$(id -u)/$label" >/dev/null 2>&1 || break
    sleep 1
  done
  for attempt in 1 2 3; do
    launchctl bootstrap "gui/$(id -u)" "$AGENTS/$label.plist" 2>/dev/null && return 0
    sleep 2
  done
  echo "Could not start $label (see: launchctl print gui/$(id -u)/$label)"
  return 1
}

watchdog_plist() { # health check every 2 minutes (runs and exits; not kept alive)
  label=com.homegrok.watchdog
  {
    echo '<?xml version="1.0" encoding="UTF-8"?>'
    echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
    echo "<plist version=\"1.0\"><dict>"
    echo "  <key>Label</key><string>$label</string>"
    echo "  <key>ProgramArguments</key><array><string>$DIR/hg</string><string>watchdog</string></array>"
    echo "  <key>WorkingDirectory</key><string>$DIR</string>"
    echo "  <key>StartInterval</key><integer>120</integer>"
    echo "  <key>StandardOutPath</key><string>$LOGS/$label.log</string>"
    echo "  <key>StandardErrorPath</key><string>$LOGS/$label.log</string>"
    echo "</dict></plist>"
  } > "$AGENTS/$label.plist"
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  sleep 1
  launchctl bootstrap "gui/$(id -u)" "$AGENTS/$label.plist" 2>/dev/null || true
}

hub_plist() { # Wholesale Hub: its own process on port 8800, lower CPU priority
  label=com.wholesalehub.hub
  HUB="$HOME/wholesale-hub"
  [ -x "$HUB/.venv/bin/python" ] || return 0
  {
    echo '<?xml version="1.0" encoding="UTF-8"?>'
    echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
    echo "<plist version=\"1.0\"><dict>"
    echo "  <key>Label</key><string>$label</string>"
    echo "  <key>ProgramArguments</key><array><string>$HUB/.venv/bin/python</string><string>run.py</string></array>"
    echo "  <key>WorkingDirectory</key><string>$HUB</string>"
    echo "  <key>RunAtLoad</key><true/>"
    echo "  <key>KeepAlive</key><true/>"
    echo "  <key>ThrottleInterval</key><integer>30</integer>"
    echo "  <key>Nice</key><integer>10</integer>"
    echo "  <key>StandardOutPath</key><string>$LOGS/$label.log</string>"
    echo "  <key>StandardErrorPath</key><string>$LOGS/$label.log</string>"
    echo "</dict></plist>"
  } > "$AGENTS/$label.plist"
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  sleep 1
  launchctl bootstrap "gui/$(id -u)" "$AGENTS/$label.plist" 2>/dev/null || true
}

case "$1" in
  install)
    mkdir -p "$AGENTS" "$LOGS"
    [ -f "$DIR/workspace/tokenizer.json" ] || { echo "Run ./hg setup and ./hg pipeline first."; exit 1; }
    plist com.homegrok.serve 0 "$DIR/hg" serve --port "$PORT"
    plist com.homegrok.learn 10 "$DIR/hg" learn
    # open-source model on the Mac's GPU (backup brain when your Claude plan runs out)
    [ -x "$DIR/vendor/ollama/ollama" ] && OLLAMA_KEEP_ALIVE=5m plist com.homegrok.ollama 5 "$DIR/vendor/ollama/ollama" serve
    watchdog_plist
    hub_plist
    launchctl bootout "gui/$(id -u)/com.homegrok.evolve" 2>/dev/null || true
    rm -f "$AGENTS/com.homegrok.evolve.plist"
    echo "HomeGrok is running in the background: http://127.0.0.1:$PORT"
    ;;
  uninstall)
    for l in com.homegrok.serve com.homegrok.learn com.homegrok.ollama com.homegrok.watchdog com.wholesalehub.hub com.homegrok.evolve; do
      launchctl bootout "gui/$(id -u)/$l" 2>/dev/null || true
      rm -f "$AGENTS/$l.plist"
    done
    echo "HomeGrok background services removed."
    ;;
  status)
    for l in com.homegrok.serve com.homegrok.learn com.homegrok.ollama com.homegrok.watchdog com.wholesalehub.hub; do
      if launchctl print "gui/$(id -u)/$l" >/dev/null 2>&1; then echo "$l: running"; else echo "$l: not running"; fi
    done
    "$DIR/hg" status
    ;;
  logs)
    tail -f "$LOGS"/com.homegrok.*.log
    ;;
  *)
    sed -n '2,6p' "$0"; exit 1
    ;;
esac
