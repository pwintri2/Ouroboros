#!/bin/sh
set -eu

cd "$(dirname "$0")"
exec python3 awake_keeper_launcher.py
