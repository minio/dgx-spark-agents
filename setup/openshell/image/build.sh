#!/bin/bash
# Build the OpenClaw sandbox image, then add a read-only Apache Iceberg checkout.
set -euo pipefail
cd "$(dirname "$0")"
docker build -t spark-agents:openclaw-2026.9.8 -f Dockerfile .
[ -d iceberg ] || { git clone -q https://github.com/apache/iceberg.git && git -C iceberg checkout -q c24eeea; }
docker build -t spark-agents:openclaw-iceberg -f Dockerfile.iceberg .
