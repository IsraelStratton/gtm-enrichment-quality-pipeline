#!/usr/bin/env bash
# Start, or re-create, the local n8n container this build uses.
#
# The same container as before chapter 2 (same image, port and two data folders), plus one
# read-only folder: this repo's skins/, mounted at /home/node/gtm-skins. The chapter 2 workflow
# reads the routing playbook from there on every run, so editing SKILL.md changes the routing
# with no change to the workflow. Read-only: n8n can read the playbook but cannot change it.
#
# n8n keeps its workflows, credentials and executions in ~/.n8n, so re-creating the container
# loses nothing. Nothing here is scheduled; the container starts only when this script runs.
#
#   scripts/n8n_docker.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="${N8N_IMAGE:-n8nio/n8n}"
SKINS_IN_N8N="/home/node/gtm-skins"
PLAYBOOK_IN_N8N="$SKINS_IN_N8N/lead-routing/lead-routing-playbook/SKILL.md"

if docker ps -a --format '{{.Names}}' | grep -qx n8n; then
  docker stop n8n >/dev/null
  docker rm n8n >/dev/null
fi

docker run -d --name n8n \
  -p 5678:5678 \
  -v "$HOME/.n8n:/home/node/.n8n" \
  -v "$HOME/Documents/AI_Datasets:/home/node/AI_Datasets" \
  -v "$REPO/skins:$SKINS_IN_N8N:ro" \
  -e N8N_RESTRICT_FILE_ACCESS_TO="/home/node/.n8n-files;$SKINS_IN_N8N" \
  "$IMAGE" >/dev/null

curl -fsS --retry 60 --retry-all-errors --retry-delay 1 http://localhost:5678/healthz >/dev/null
echo "n8n is up: $(docker exec n8n n8n --version)"
docker exec n8n test -r "$PLAYBOOK_IN_N8N" && echo "The playbook is readable inside n8n at $PLAYBOOK_IN_N8N"
if docker exec n8n sh -c "touch $SKINS_IN_N8N/.write-test" 2>/dev/null; then
  echo "WARNING: the skins folder is writable from n8n" >&2
  exit 1
fi
echo "The skins folder is read-only inside n8n."
