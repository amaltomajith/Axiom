#!/bin/sh
# Runs before nginx starts (the official image executes /docker-entrypoint.d/*.sh).
# One image, any API: AXIOM_API_BASE overrides the API URL baked into config.json at build time, and
# AXIOM_HUB_URL (optional) the "All of Axiom" link. Unset values fall back to the app's defaults.
set -eu
check() {
  case "$2" in
    http://*|https://*) ;;
    *) echo "$1 must start with http:// or https://" >&2; exit 1 ;;
  esac
}
if [ -n "${AXIOM_API_BASE:-}" ] || [ -n "${AXIOM_HUB_URL:-}" ]; then
  json='{'
  if [ -n "${AXIOM_API_BASE:-}" ]; then
    check AXIOM_API_BASE "$AXIOM_API_BASE"
    json="$json \"apiBase\": \"${AXIOM_API_BASE%/}\""
    echo "axiom-watch: API base set to ${AXIOM_API_BASE%/}"
  fi
  if [ -n "${AXIOM_HUB_URL:-}" ]; then
    check AXIOM_HUB_URL "$AXIOM_HUB_URL"
    [ "$json" = '{' ] || json="$json,"
    json="$json \"hubUrl\": \"${AXIOM_HUB_URL%/}\""
  fi
  printf '%s }\n' "$json" > /usr/share/nginx/html/config.json
fi
