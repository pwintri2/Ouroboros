#!/bin/bash
# Docker test runner for Negesydd

cd /home/pwintri2/Negesydd

echo "================================"
echo "NEGESYDD DOCKER TEST SUITE"
echo "================================"
echo ""

# Test all modules
docker run --rm \
  -v /home/pwintri2/Negesydd:/negesydd \
  -v negesydd-dev:/negesydd/.venv \
  negesydd:dev-sandbox \
  python -m pytest tests/ -v --tb=short

exit $?
