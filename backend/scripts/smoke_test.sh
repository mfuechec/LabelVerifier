#!/usr/bin/env bash
# Smoke test: build and run the Docker image locally, hit health endpoint.
# Usage: cd backend && bash scripts/smoke_test.sh

set -euo pipefail

IMAGE_NAME="labelverify-backend"
CONTAINER_NAME="labelverify-smoke"
PORT=8000

echo "==> Building Docker image..."
docker build -t "$IMAGE_NAME" .

echo "==> Starting container on port $PORT..."
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
docker run -d --name "$CONTAINER_NAME" \
  -p "$PORT:$PORT" \
  -e PORT="$PORT" \
  -e GROQ_API_KEY="test-smoke-key" \
  "$IMAGE_NAME"

echo "==> Waiting for startup..."
sleep 3

echo "==> Hitting health endpoint..."
RESPONSE=$(curl -sf "http://localhost:$PORT/api/v1/health" || true)

echo "==> Cleaning up..."
docker rm -f "$CONTAINER_NAME" >/dev/null

if [ -z "$RESPONSE" ]; then
  echo "FAIL: Health endpoint did not respond."
  exit 1
fi

echo "Health response: $RESPONSE"

# Check that response contains expected fields
if echo "$RESPONSE" | python3 -c "
import json, sys
data = json.load(sys.stdin)['data']
assert 'status' in data, 'missing status'
assert 'checks' in data, 'missing checks'
assert 'version' in data, 'missing version'
print(f\"Status: {data['status']}, Version: {data['version']}, Checks: {data['checks']}\")
"; then
  echo "PASS: Smoke test succeeded."
else
  echo "FAIL: Health response missing expected fields."
  exit 1
fi
