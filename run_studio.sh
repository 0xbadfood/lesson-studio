#!/usr/bin/env bash
# Lesson Studio: start | stop | restart | status. Lesson pipelines run detached and survive restarts.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
PORT="${PORT:-18610}"
PIDFILE=scivid-data/server.pid
mkdir -p scivid-data

# Installed as the systemd user unit lesson-studio.service (enabled at boot): delegate to it.
UNIT=lesson-studio.service
if systemctl --user cat "$UNIT" >/dev/null 2>&1; then
  case "${1:-start}" in
    start|stop|restart) systemctl --user "${1:-start}" "$UNIT"; systemctl --user --no-pager status "$UNIT" | head -3 ;;
    status) systemctl --user --no-pager status "$UNIT" | head -3 ;;
    *) echo "usage: $0 start|stop|restart|status"; exit 2 ;;
  esac
  exit
fi

running() { [[ -f $PIDFILE ]] && kill -0 "$(cat $PIDFILE)" 2>/dev/null; }

start() {
  if running; then echo "Lesson Studio already running (PID $(cat $PIDFILE))"; return; fi
  setsid nohup python3 -m scivid --port "$PORT" >> scivid-data/server.log 2>&1 < /dev/null &
  echo $! > $PIDFILE
  sleep 3
  if running; then echo "Lesson Studio running on port $PORT (PID $(cat $PIDFILE))"; else echo "Failed to start; see scivid-data/server.log"; exit 1; fi
}

stop() {
  if running; then kill "$(cat $PIDFILE)"; sleep 2; echo "Stopped"; else echo "Not running"; fi
  rm -f $PIDFILE
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) if running; then echo "Running (PID $(cat $PIDFILE))"; else echo "Not running"; fi ;;
  *) echo "usage: $0 start|stop|restart|status"; exit 2 ;;
esac
