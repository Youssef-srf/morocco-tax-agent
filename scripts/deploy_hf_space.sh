#!/usr/bin/env bash
# Push the API to a Hugging Face Docker Space (free CPU tier).
#
# Usage (Git Bash):
#   scripts/deploy_hf_space.sh <hf-user>/<space-name>
#
# Needs: a Space created with SDK "Docker" and hardware "CPU basic" (free),
# git credentials for huggingface.co (an access token with write scope), and
# the Space secrets GEMINI_API_KEY, GEMINI_MODEL and DATABASE_URL set in its
# settings. See docs/deploy.md.
set -euo pipefail

space="${1:?usage: $0 <hf-user>/<space-name>}"
repo_root="$(git rev-parse --show-toplevel)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

git clone --depth 1 "https://huggingface.co/spaces/$space" "$work/space"
cd "$work/space"
git rm -rq --ignore-unmatch . >/dev/null

# Only what the image needs: no tests, raw PDFs, .env or evaluation cache.
cp "$repo_root"/{Dockerfile,.dockerignore,pyproject.toml,uv.lock,.python-version} .
cp "$repo_root/deploy/hf-space/README.md" README.md
mkdir -p data
cp -r "$repo_root/src" .
cp -r "$repo_root/data/processed" data/
find . -name __pycache__ -type d -prune -exec rm -rf {} +

git add -A
git commit -qm "Deploy $(git -C "$repo_root" rev-parse --short HEAD)" || echo "Nothing to deploy"
git push origin HEAD:main
echo "Pushed. Build logs: https://huggingface.co/spaces/$space"
