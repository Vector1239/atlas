#!/usr/bin/env bash
# Install (or update) the Germany-life scripts and skills into Hermes.
#
#   ./install.sh            # detects the terminal backend Hermes uses
#   ./install.sh docker     # skills point at /workspace/germany-life (Docker sandbox)
#   ./install.sh local      # skills point at this folder
#
# Safe to re-run after you edit anything. It never touches your secrets, and it never
# overwrites profile.md or anything in data/.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
BACKEND="${1:-}"

if [[ -z "$BACKEND" ]]; then
  if command -v hermes >/dev/null 2>&1 && hermes config get terminal.backend 2>/dev/null | grep -qi docker; then
    BACKEND=docker
  else
    BACKEND=local
  fi
fi
case "$BACKEND" in
  docker) AGENT_HOME="/workspace/germany-life" ;;
  local)  AGENT_HOME="$HERE" ;;
  *) echo "usage: ./install.sh [docker|local]" >&2; exit 2 ;;
esac

# 1. Your files: created from templates only if they don't exist yet.
mkdir -p "$HERE/data" "$HERE/state"
[[ -f "$HERE/profile.md" ]] || cp "$HERE/templates/profile.md" "$HERE/profile.md"
for f in deadlines.toml worklog.csv job_feedback.csv; do
  [[ -f "$HERE/data/$f" ]] || cp "$HERE/templates/$f" "$HERE/data/$f"
done

# 2. Cron scripts: Hermes only runs scripts that live under ~/.hermes/scripts/.
SCRIPTS="$HERMES_HOME/scripts/germany_life"
mkdir -p "$SCRIPTS"
cp "$HERE"/scripts/*.py "$SCRIPTS/"
printf '%s\n' "$HERE" > "$SCRIPTS/germany_life_home.txt"

# 3. Skills, with {{GL}} replaced by the path the agent sees.
SKILLS="$HERMES_HOME/skills/germany-life"
mkdir -p "$SKILLS"
for dir in "$HERE"/skills/*/; do
  name="$(basename "$dir")"
  rm -rf "${SKILLS:?}/$name"
  mkdir -p "$SKILLS/$name"
  sed "s|{{GL}}|$AGENT_HOME|g" "$dir/SKILL.md" > "$SKILLS/$name/SKILL.md"
done

echo "Installed for the '$BACKEND' backend."
echo "  scripts → $SCRIPTS"
echo "  skills  → $SKILLS  (trier-morning-brief, job-scan, germany-admin)"
echo "  data    → $HERE/data   profile → $HERE/profile.md"
if [[ "$BACKEND" == docker ]]; then
  cat <<EOF

Docker sandbox: make sure ~/.hermes/config.yaml has these mounts under terminal:
(merge into an existing docker_volumes list rather than adding a second one)

  terminal:
    backend: docker
    docker_volumes:
      - "$HERE/gl:/workspace/germany-life/gl:ro"
      - "$HERE/scripts:/workspace/germany-life/scripts:ro"
      - "$HERE/config:/workspace/germany-life/config:ro"
      - "$HERE/profile.md:/workspace/germany-life/profile.md:ro"
      - "$HERE/data:/workspace/germany-life/data"

state/ (chat history, saved API keys) is deliberately not mounted: with web tools on,
nothing the agent can read should be worth stealing. Replace any older
"$HERE:/workspace/germany-life:ro" line with the ones above.

Then restart the gateway: hermes gateway restart
EOF
fi
echo
echo "Next: ./gl check   then create the cron jobs in cron/JOBS.md"
