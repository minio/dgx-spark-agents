#!/bin/bash
# spark-vllm-docker mod: install the MemKV plugin into the vLLM container.
set -euo pipefail
pip install -q --no-deps memkv-vllm==1.0.11
python3 -c 'import memkv_vllm.spec'
echo '[memkv-vllm] installed 1.0.11'
