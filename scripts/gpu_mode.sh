#!/usr/bin/env bash
# Switch the lab's single RTX 3090 between the local LLM and the media models.
#
#   scripts/gpu_mode.sh llm      # local Qwen 3.8 27B (vLLM, :7001) owns the GPU
#   scripts/gpu_mode.sh media    # Qwen Image (:8075) and VibeVoice may load again
#   scripts/gpu_mode.sh status
#
# The media services stay resident and load their models on demand under the shared GPU lock
# (/tmp/infofilm-rtx3090.lock, used by infofilm and Lesson Studio). In llm mode a small holder
# process keeps that lock, so image and narration jobs wait for media mode instead of running
# out of GPU memory. Switching waits for any job that holds the lock to finish.
set -euo pipefail

LOCK=${GPU_LOCK:-/tmp/infofilm-rtx3090.lock}
QWEN_DIR=${QWEN_DIR:-$HOME/qwen38-27b-rtx3090}
LLM_URL=${LLM_URL:-http://127.0.0.1:7001}
IMAGE_URL=${IMAGE_URL:-http://127.0.0.1:8075}
STATE=${XDG_RUNTIME_DIR:-/tmp}/gpu-mode
HOLDER=$STATE/lock-holder.pid
WAIT_LOCK=${WAIT_LOCK:-3600}     # seconds to wait for a running image/voice job
WAIT_READY=${WAIT_READY:-1200}   # first vLLM start compiles kernels (up to ~15 min)
mkdir -p "$STATE"

log() { printf '[gpu-mode] %s\n' "$*"; }
# This account reaches Docker through sudo (the shell aliases docker to "sudo docker").
if docker info >/dev/null 2>&1; then DOCKER=(docker); else DOCKER=(sudo -n docker); fi
llm_running() { "${DOCKER[@]}" ps --format '{{.Names}}' | grep -qx 'qwen-vllm-single-1'; }
llm_ready() { curl -sf -m 5 "$LLM_URL/health" >/dev/null; }
gpu_used() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1; }
holder_alive() { [[ -f $HOLDER ]] && kill -0 "$(cat "$HOLDER")" 2>/dev/null; }

take_lock() {
    holder_alive && { log "already holding the GPU lock (pid $(cat "$HOLDER"))"; return; }
    log "waiting for the GPU lock (an image or narration job may be running)…"
    # The holder takes the lock, then sleeps until media mode kills it.
    setsid flock -w "$WAIT_LOCK" -x "$LOCK" sleep infinity </dev/null >/dev/null 2>&1 &
    local pid=$!
    for _ in $(seq 1 "$WAIT_LOCK"); do
        # flock's child (sleep) appears once the lock is held; flock itself exits if it timed out.
        if pgrep -P "$pid" -x sleep >/dev/null; then echo "$pid" >"$HOLDER"; log "GPU lock held (pid $pid)"; return; fi
        kill -0 "$pid" 2>/dev/null || { log "could not get the GPU lock within ${WAIT_LOCK}s"; exit 1; }
        sleep 1
    done
}

release_lock() {
    if holder_alive; then
        local pid; pid=$(cat "$HOLDER")
        pkill -P "$pid" -x sleep 2>/dev/null || true
        kill "$pid" 2>/dev/null || true
        log "GPU lock released"
    fi
    rm -f "$HOLDER"
}

case ${1:-status} in
llm)
    take_lock
    # Free the image model if it is loaded (VibeVoice releases the GPU after each job by itself).
    curl -sf -m 30 -X POST "$IMAGE_URL/api/unload" >/dev/null 2>&1 || true
    if ! llm_running; then
        log "starting local Qwen (vLLM)…"
        (cd "$QWEN_DIR" && "${DOCKER[@]}" compose --profile single up -d >/dev/null)
    fi
    for _ in $(seq 1 $((WAIT_READY / 5))); do
        llm_ready && { log "llm mode: $LLM_URL ready, GPU $(gpu_used)MiB used"; exit 0; }
        llm_running || { log "the vLLM container stopped; see: docker logs qwen-vllm-single-1"; release_lock; exit 1; }
        sleep 5
    done
    log "vLLM not ready after ${WAIT_READY}s; still holding the lock (run '$0 media' to give the GPU back)"
    exit 1
    ;;
media)
    if llm_running; then
        log "stopping local Qwen (vLLM)…"
        (cd "$QWEN_DIR" && "${DOCKER[@]}" compose --profile single stop >/dev/null)
    fi
    for _ in $(seq 1 60); do
        (( $(gpu_used) < 4000 )) && break
        sleep 2
    done
    release_lock
    log "media mode: GPU $(gpu_used)MiB used; Qwen Image and VibeVoice load on demand"
    ;;
status)
    if llm_running; then
        llm_ready && mode="llm (ready at $LLM_URL)" || mode="llm (starting)"
    else
        mode=media
    fi
    holder_alive && lock="held by gpu-mode (pid $(cat "$HOLDER"))" || lock="not held by gpu-mode"
    log "mode: $mode; GPU lock: $lock; GPU memory used: $(gpu_used)MiB"
    ;;
*)
    echo "usage: $0 llm|media|status" >&2; exit 2 ;;
esac
