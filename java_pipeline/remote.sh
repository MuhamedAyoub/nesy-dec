#!/usr/bin/env bash
# Drive the GPU server from this machine over SSH (vast.ai or any host).
#
#   bash java_pipeline/remote.sh push   HOST PORT   # build the bundle, upload, unpack
#   bash java_pipeline/remote.sh start  HOST PORT   # run_server.sh detached on the server
#   bash java_pipeline/remote.sh status HOST PORT   # progress counts and log tails
#   bash java_pipeline/remote.sh pull   HOST PORT   # fetch results, unpack here, build the Phase 7 tables
#   bash java_pipeline/remote.sh ssh    HOST PORT   # interactive shell in the run directory
#
# Environment: REMOTE_USER (default root), REMOTE_DIR (required: the run directory on the server),
# SMOKE, SEEDS, RLDEC_JOBS, RLDEC and ABLATIONS are passed through to run_server.sh on start.
set -euo pipefail
ACTION="${1:?usage: remote.sh push|start|status|pull|ssh HOST PORT}"
HOST="${2:?host}"
PORT="${3:?port}"
USER_="${REMOTE_USER:-root}"
DIR="${REMOTE_DIR:?set REMOTE_DIR to the run directory on the server}"
RUN="$DIR/$(basename "$(cd "$(dirname "$0")/.." && pwd)")"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
SSH=(ssh -p "$PORT" -o ServerAliveInterval=30 "$USER_@$HOST")

case "$ACTION" in
  push)
    bash "$HERE/java_pipeline/make_bundle.sh"
    "${SSH[@]}" "mkdir -p $DIR"
    scp -P "$PORT" "$HERE/../java_gpu_bundle.tar.gz" "$HERE/../java_gpu_bundle.tar.gz.sha256" "$USER_@$HOST:$DIR/"
    "${SSH[@]}" "cd $DIR && sha256sum -c java_gpu_bundle.tar.gz.sha256 && tar xzf java_gpu_bundle.tar.gz && echo unpacked in $RUN"
    ;;
  start)
    # the subshell detaches fully, so the SSH session returns instead of waiting on the job
    "${SSH[@]}" "cd $RUN && mkdir -p logs && (SMOKE='${SMOKE:-0}' SEEDS='${SEEDS:-42 1 7}' RLDEC_JOBS='${RLDEC_JOBS:-6}' RLDEC='${RLDEC:-1}' ABLATIONS='${ABLATIONS:-}' \
      setsid nohup bash java_pipeline/run_server.sh > logs/run_server.out 2>&1 < /dev/null &); echo started; sleep 5; tail -n 5 $RUN/logs/run_server.out"
    ;;
  status)
    "${SSH[@]}" "cd $RUN && SEEDS='${SEEDS:-42 1 7}' bash java_pipeline/run_server.sh status; tail -n 4 logs/run_server.out 2>/dev/null; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader"
    ;;
  pull)
    # rsync resumes a broken transfer (a 1.3 GB scp dropped once); retry until the checksum matches
    want=$("${SSH[@]}" "sha256sum $RUN/results_java_gpu.tar.gz" | awk '{print $1}')
    for attempt in 1 2 3 4 5 6 7 8; do
      rsync -a --partial --append-verify -e "ssh -p $PORT -o ServerAliveInterval=15" \
        "$USER_@$HOST:$RUN/results_java_gpu.tar.gz" "$HERE/results_java_gpu.tar.gz" || true
      [[ "$(sha256sum "$HERE/results_java_gpu.tar.gz" | awk '{print $1}')" == "$want" ]] && break
      echo "transfer incomplete, retry $attempt"; sleep 5
    done
    [[ "$(sha256sum "$HERE/results_java_gpu.tar.gz" | awk '{print $1}')" == "$want" ]] || { echo "checksum mismatch"; exit 1; }
    (cd "$HERE" && tar xzf results_java_gpu.tar.gz && mkdir -p results/gpu_logs && cp -r logs/. results/gpu_logs/ && rm -rf logs)
    (cd "$HERE" && python3 -m java_pipeline.results)
    echo "results unpacked; GPU logs in results/gpu_logs/"
    ;;
  ssh)
    ssh -t -p "$PORT" "$USER_@$HOST" "cd $RUN && exec bash -l"
    ;;
  *)
    echo "unknown action $ACTION" >&2; exit 2;;
esac
