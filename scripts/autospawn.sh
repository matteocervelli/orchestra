#!/usr/bin/env bash
# Poll the legacy file queue. Source extraction only; Nexus must own live dispatch.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
orchestra_root=${ORCHESTRA_ROOT:-$repo_root}
poll_seconds=${ORCHESTRA_POLL_SECONDS:-60}
once=${ORCHESTRA_ONCE:-0}
cd "$orchestra_root"

mkdir -p logs scratch
touch scratch/running.txt scratch/spawn-queue.txt

while :; do
  running=0
  read -r -a running_slugs < scratch/running.txt || true
  for slug in "${running_slugs[@]}"; do
    grep -q '^EXIT=' "logs/$slug.err" 2>/dev/null || running=$((running + 1))
  done

  if [[ -e scratch/ci-hold ]]; then
    printf '%s held by chat-ci n=%s q=%s\n' "$(date -u +%H:%M)" "$running" "$(wc -l < scratch/spawn-queue.txt)" > logs/autospawn.heartbeat
  else
    cap=$(cat scratch/spawn-cap 2>/dev/null || echo 6)
    if [[ $running -lt $cap && -s scratch/spawn-queue.txt ]]; then
      read -r slug tool model effort workdir task < scratch/spawn-queue.txt
      sed -i 1d scratch/spawn-queue.txt
      if ! scripts/spawn.sh "$slug" "$tool" "$model" "$effort" "$workdir" "$orchestra_root/$task"; then
        echo "$slug $tool $model $effort $workdir $task" >> scratch/spawn-queue.txt
        echo "$(date -u +%H:%M) spawn FAILED $slug, requeued"
      else
        keep=()
        read -r -a active_slugs < scratch/running.txt || true
        for active in "${active_slugs[@]}"; do
          grep -q '^EXIT=' "logs/$active.err" 2>/dev/null || keep+=("$active")
        done
        printf '%s\n' "${keep[*]} $slug" | xargs > scratch/running.txt
        echo "$(date -u +%H:%M) spawned $slug (running was $running)"
      fi
    else
      printf '%s idle n=%s q=%s\n' "$(date -u +%H:%M)" "$running" "$(wc -l < scratch/spawn-queue.txt)" > logs/autospawn.heartbeat
    fi
  fi

  [[ "$once" == 1 ]] && break
  sleep "$poll_seconds"
done
