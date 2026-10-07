#!/bin/bash
# Start DeepSeek-V4-Flash across both DGX Sparks with spark-vllm-docker, with or
# without MemKV. Run it on the first DGX Spark, from a checkout of
# https://github.com/eugr/spark-vllm-docker.
#
#   launch.sh memkv <namespace> <log-file>
#   launch.sh nomemkv - <log-file>
#
# <namespace> is a MemKV key prefix. A new one starts with an empty cache; the
# same one finds the KV stored under it before.
#
# Needs: ~/.vllm-api-key, and ~/.memkv holding client.yaml and memkv.license.
set -euo pipefail
arm=$1 namespace=$2 log=$3
here=$(cd "$(dirname "$0")" && pwd)
: "${SPARK_VLLM_DOCKER:=$HOME/spark-vllm-docker}"
: "${SPARK_PEERS:=192.168.100.1 192.168.100.2}"
cd "$SPARK_VLLM_DOCKER"

# Start every run from the same memory state on both DGX Sparks.
for h in $SPARK_PEERS; do ssh "$h" "sync; echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null"; done

common=(deepseek-v4-flash-0731 --earlyoom --gpu-mem 0.82 -e PYTHONHASHSEED=0
        -e VLLM_PREFIX_CACHE_RETENTION_INTERVAL=4096)
serve=(--served-model-name dsv4flash --api-key "$(cat ~/.vllm-api-key)"
       --enable-cumem-allocator --max-num-batched-tokens 4096)

if [ "$arm" = memkv ]; then
  kv='{"kv_connector":"OffloadingConnector","kv_role":"kv_both","kv_connector_extra_config":{"spec_name":"MemKVOffloadingSpec","spec_module_path":"memkv_vllm.spec","memkv_scratch_medium":"host","memkv_spec_prefix":"'"$namespace"'"}}'
  ./run-recipe.sh "${common[@]}" --apply-mod "$here/memkv-vllm-mod" \
    -e MEMKV_CONFIG=/memkv/client.yaml -v "$HOME/.memkv:/memkv:ro" \
    -- "${serve[@]}" --kv-transfer-config "$kv" 2>&1 | tee "$log"
else
  ./run-recipe.sh "${common[@]}" -- "${serve[@]}" 2>&1 | tee "$log"
fi
