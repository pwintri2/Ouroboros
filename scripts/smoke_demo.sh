#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:8000}"

printf 'Checking %s/health\n' "$API_BASE"
curl --fail --silent "$API_BASE/health" | python -m json.tool

printf '\nRunning personalised Ambient Sentinel demo\n'
curl --fail --silent -X POST "$API_BASE/demo/run" \
  -H 'Content-Type: application/json' \
  -d '{"inject_attack":true,"ticks":5,"user_profile":{"name":"Oma Els","language":"nl","tone":"reassuring"}}' \
  | python -m json.tool

printf '\nChecking current demo state\n'
curl --fail --silent "$API_BASE/demo/state" | python -m json.tool
