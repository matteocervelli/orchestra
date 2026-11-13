#!/usr/bin/env bash
# usage: spawn.sh <slug> <claude|codex|pi> <model> <effort> <workdir> <task-file>
# Source extraction only: this repository does not install or activate the launcher.
set -euo pipefail

if [[ $# -ne 6 ]]; then
  echo "usage: spawn.sh <slug> <claude|codex|pi> <model> <effort> <workdir> <task-file>" >&2
  exit 2
fi

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
orchestra_root=${ORCHESTRA_ROOT:-$repo_root}
slug=$1
tool=$2
model=$3
effort=$4
workdir=$5
task=$6

case "$tool" in
  codex)
    cmd=(zsh -c 'source ~/.config/shell/functions.sh && codexdanger "$@"' codexdanger exec --json -m "$model" -c "model_reasoning_effort=\"$effort\"" -C "$workdir")
    ;;
  pi)
    # shellcheck disable=SC2016 # $1 is evaluated by the child zsh process.
    cmd=(zsh -ic 'pidanger -p "$1"' pidanger)
    ;;
  claude)
    cmd=(claude -p --output-format stream-json --verbose --model "$model" --effort "$effort" --dangerously-skip-permissions)
    ;;
  *)
    echo "unsupported tool: $tool" >&2
    exit 2
    ;;
esac

prompt="Read the task file $task and do it. You are a non-interactive child of the orchestrator (away mode): never wait for input; if blocked, say so in your final report."
cmd+=("$prompt")
mkdir -p "$orchestra_root/logs"
log="$orchestra_root/logs/$slug"
printf -v quoted_command '%q ' "${cmd[@]}"

last_index=$(timeout 30 tmux list-windows -t orchestra -F '#{window_index}' | sort -n | tail -1)
index=$(( ${last_index:-0} + 1 ))
timeout 30 tmux new-window -d -t "orchestra:$index" -n "$slug" -c "$workdir" \
  "start=\$(date +%s); $quoted_command < /dev/null > $(printf '%q' "$log.jsonl") 2> $(printf '%q' "$log.err"); rc=\$?; echo wall=\$(( \$(date +%s)-start )) >> $(printf '%q' "$log.err"); echo EXIT=\$rc >> $(printf '%q' "$log.err"); tmux kill-pane -t \$TMUX_PANE"

watch="$orchestra_root/scripts/watch.sh"
if [[ -x "$watch" ]]; then
  timeout 30 tmux split-window -d -v -l 85% -t "orchestra:$index" "$watch $slug 60" || \
    echo "watch pane failed for $slug (child still running)" >&2
fi

python3 - "$log" "$slug" "$tool" "$model" "$effort" "$workdir" "$task" <<'PY'
import json
import sys
import time

log, slug, tool, model, effort, workdir, task = sys.argv[1:]
row = {
    "slug": slug,
    "tool": tool,
    "model": model,
    "effort": effort,
    "workdir": workdir,
    "task": task,
    "start": int(time.time()),
}
with open(f"{log.rsplit('/', 1)[0]}/spawns.jsonl", "a", encoding="utf-8") as handle:
    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
PY

echo "spawned orchestra:$slug ($tool $model $effort) in $workdir"
