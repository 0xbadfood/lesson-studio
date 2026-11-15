#!/bin/bash
# Switches the amdserver's GPUs between modes through its mode switch (:8099) and waits until the new mode is ready.
# Usage: switchamd.sh --mode <image|video|llm|off>     switchamd.sh --status
# The switch's key is read from ~/.config/gpu-mode/api-key and never printed.
set -u
URL=${AMD_MODE_URL:-http://10.8.0.8:8099}
KEY_FILE=$HOME/.config/gpu-mode/api-key
WAIT=${AMD_MODE_WAIT:-900}                 # seconds; LLM mode takes about a minute, image a little less

usage() { echo "usage: $0 --mode <image|video|llm|off> | --status" >&2; exit 2; }
status() { curl -s -m 8 "$URL/status"; }
field() { python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('$1') or '')"; }
summary() { python3 -c "import json,sys; d=json.load(sys.stdin); s=d.get('services',{}); print(f\"mode={d.get('mode')} phase={d.get('phase')} image={s.get('image')} llm={s.get('llm')} video={s.get('video')} vram_gb={s.get('gpu_vram_used_gb')}\" + (f\" detail={d['detail']}\" if d.get('detail') else ''))"; }

[ $# -ge 1 ] || usage
case $1 in
  --status) s=$(status) || { echo "FAILED mode switch at $URL not reachable" >&2; exit 1; }; echo "$s" | summary; exit 0 ;;
  --mode) [ $# -eq 2 ] || usage; MODE=$2 ;;
  *) usage ;;
esac
case $MODE in image|video|llm|off) ;; *) usage ;; esac
[ -s "$KEY_FILE" ] || { echo "FAILED no key in $KEY_FILE" >&2; exit 1; }

now=$(status) || { echo "FAILED mode switch at $URL not reachable" >&2; exit 1; }
if [ "$(echo "$now" | field mode)" = "$MODE" ] && [ "$(echo "$now" | field phase)" = ready ]; then
  echo "already in $MODE mode"; echo "$now" | summary; exit 0
fi

# the key goes to curl through a header file on stdin, so it never appears on a command line
code=$(printf 'Authorization: Bearer %s\nX-Caller: switchamd.sh\n' "$(cat "$KEY_FILE")" |
       curl -s -m 15 -o /dev/null -w '%{http_code}' -X POST -H @- "$URL/mode/$MODE")
case $code in
  200|202) echo "switching to $MODE..." ;;
  401) echo "FAILED the mode switch refused the key in $KEY_FILE" >&2; exit 1 ;;
  409) echo "FAILED another switch is running; try again when it finishes:" >&2; status | summary >&2; exit 1 ;;
  *) echo "FAILED mode switch answered $code" >&2; exit 1 ;;
esac

start=$(date +%s); last=
while :; do
  s=$(status) || s='{}'
  phase=$(echo "$s" | field phase 2>/dev/null)
  [ "$phase" != "$last" ] && [ -n "$phase" ] && { echo "  $(date +%T) $phase"; last=$phase; }
  if [ "$phase" = ready ] && [ "$(echo "$s" | field mode)" = "$MODE" ]; then echo "$s" | summary; exit 0; fi
  [ "$phase" = failed ] && { echo "FAILED switch to $MODE:" >&2; echo "$s" | summary >&2; exit 1; }
  [ $(( $(date +%s) - start )) -gt "$WAIT" ] && { echo "FAILED not ready after ${WAIT}s:" >&2; echo "$s" | summary >&2; exit 1; }
  sleep 5
done
