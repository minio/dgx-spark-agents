#!/bin/bash
# Create an OpenClaw sandbox and point OpenClaw at vLLM on the DGX Sparks.
#
#   setup-openclaw.sh [name]
#
# Needs the spark-agents:openclaw-iceberg image (see image/) and the spark-vllm
# provider (see ../../README.md).
set -euo pipefail
NAME=${1:-openclaw}
VLLM_URL=${VLLM_URL:?set VLLM_URL to vLLM on the first DGX Spark, for example http://192.0.2.10:8000}
here=$(cd "$(dirname "$0")" && pwd)
openshell sandbox delete "$NAME" >/dev/null 2>&1 || true
while openshell sandbox list 2>/dev/null | grep -q "^$NAME "; do sleep 2; done
openshell sandbox create --name "$NAME" --from spark-agents:openclaw-iceberg \
  --policy "$here/agent-policy.yaml" --provider spark-vllm --detach \
  --env TMPDIR=/tmp --env SQLITE_TMPDIR=/tmp </dev/null
openshell sandbox exec -n "$NAME" --timeout 600 --workdir /sandbox -- bash -c "
  set -e
  export PATH=/opt/node24/bin:\$PATH
  openclaw onboard --non-interactive --accept-risk --skip-health --mode local \
    --auth-choice vllm --custom-base-url $VLLM_URL/v1 \
    --custom-api-key \"\$VLLM_API_KEY\" --custom-model-id dsv4flash >/dev/null
  openclaw config set models.providers.vllm.timeoutSeconds 300 >/dev/null
  openclaw config set 'models.providers.vllm.models[0].contextWindow' 1000000 >/dev/null
  openclaw config set 'models.providers.vllm.models[0].maxTokens' 16384 >/dev/null
  openclaw config validate
  echo \"node \$(node --version), \$(openclaw --version)\"
"
