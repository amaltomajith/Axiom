#!/bin/sh
# Runs before nginx starts (the official image executes /docker-entrypoint.d/*.sh).
# One image, any API: AXIOM_API_BASE overrides the API URL baked into config.json at build time.
set -eu
if [ -n "${AXIOM_API_BASE:-}" ]; then
  case "$AXIOM_API_BASE" in
    http://*|https://*) ;;
    *) echo "AXIOM_API_BASE must start with http:// or https://" >&2; exit 1 ;;
  esac
  printf '{ "apiBase": "%s" }\n' "${AXIOM_API_BASE%/}" > /usr/share/nginx/html/config.json
  echo "axiom-watch: API base set to ${AXIOM_API_BASE%/}"
fi
