# Evidence for every number in the blog post

This page lists each number in the blog post *MemKV on Two DGX Sparks*, the file in this repository it comes from, and the command that reproduces it. Run the commands from the repository root. They read only files in `data/` and need no access to the DGX Sparks.

```
python3 harness/analyze.py restart data/openclaw-restart     # the restart test
python3 harness/analyze.py openclaw-fleet data/openclaw-fleet  # the 40-session test
python3 harness/cost.py                                        # every cost figure
```

## Resuming after a restart

Source: `data/openclaw-restart/`, three runs numbered 11, 12 and 13, with MemKV storing KV in 1 MiB blocks. Command: `analyze.py restart`. The blog shows the median and the range of the three runs.

| Blog figure | Value in the data | Field |
|---|---|---|
| Wait for the first word: 2.4 s (2.0–6.6) with MemKV, 58.7 s (31.2–68.5) without. Headline "24× sooner" | 2.4 / 58.7 s | `first_word_s` |
| Session size when it resumed: 70,000 to 139,000 tokens | 69,511 to 139,185 | `session_tokens` |
| Session tokens loaded from MemKV: 124,200 of 126,600 | 124,160 of 126,608 | `restored_tokens`, `session_tokens` |
| Prompt tokens the GPUs computed: 17,300 (11,500–21,400) and 131,300 (94,800–150,300). Headline "87% fewer" | 17,295 and 131,341 | `computed_tokens` |
| Time reading context: 15.1 s (9.3–19.5) and 62.2 s (45.4–76.6) | same | `prefill_s` |
| Data read from MemKV: 1.0 GB (0.57–1.09) | 1.016 GB (0.571–1.094) | `memkv_read_gb` |
| "About a minute" to reread a 120,000-token session | 58.7 s for 126,608 tokens (run 11) | `first_word_s` |
| MemKV was faster in all three pairs | true for every run | `first_word_s`, `prefill_s` |

**The network chart** is run 11: `data/openclaw-restart/nic-r11-memkv.jsonl` and `nic-r11-nomemkv.jsonl`, summed over both rails of both DGX Sparks. The restore took 1 to 2 seconds in every run, and the recompute 32 to 68 seconds (`nic_burst_s`). The recompute exchanged 100.7 to 202.3 GB (`nic_burst_gb`). The peaks are about 2.2 GB/s with MemKV and 3.7 GB/s without.

**The 200 Gb/s link** is what `ethtool` reports for both rails on both DGX Sparks: `data/network/link-speed.txt`.

## Forty agents share the server

Source: `data/openclaw-fleet/`. Command: `analyze.py openclaw-fleet`. This test ran on 7 October 2026 between 07:29 and 17:44 UTC, before MemKV moved to 1 MiB blocks, so it used MemKV's default of 4 MiB (see the last section).

| Blog figure | Value in the data |
|---|---|
| The 40 sessions held about 3.6 million tokens | 3,609,613 (`session_tokens_after_build`) |
| vLLM's GPU cache holds about 1.9 million tokens | 1,887,859 to 1,893,911 tokens in every run, from vLLM's startup log: `data/vllm/gpu-kv-cache-size.txt` |
| Prompt tokens the GPUs computed: round 1, 0.55 M against 4.61 M; round 2, 1.14 M against 5.42 M | `computed_mtok` of `memkv-r1`, `nomemkv-r1`, `memkv-r2`, `nomemkv-r2` |
| Share computed: 1.8% against 12% | 1.69 M of 94.45 M; 10.03 M of 83.64 M |
| Prompt tokens served per hour: 26.5 M against 21.8 M | 94.45 M in 3.56 h; 83.64 M in 3.84 h |
| 94 million and 84 million prompt tokens in the two setups | the same sums |
| No failed turns: 0 of 80 in each setup | `failed` |

## Cost

Source: `harness/cost.py`, which reads the two tests above. Prices were checked on 7 October 2026 at [claude.com/pricing](https://claude.com/pricing), [developers.openai.com/api/docs/pricing](https://developers.openai.com/api/docs/pricing) and [ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing). The DGX Spark price is [NVIDIA's list price](https://forums.developer.nvidia.com/t/2-23-2026-price-change-announcement/361713).

| Blog figure | How it is computed |
|---|---|
| $0.017 per million prompt tokens with MemKV around the clock, $0.044 at 8 hours a day | ($9,398 over 3 years, plus 2 × 240 W at $0.17/kWh) ÷ 26.5 M prompt tokens per hour |
| $0.020 and $0.053 without MemKV | the same ÷ 21.8 M per hour |
| A task: about 850,000 prompt tokens, 17,000 computed, 8,000 written | the median resume with MemKV: run 13, 850,063 / 17,295 / 8,236 |
| API cost with a cache hit | (cached tokens × cache-read price + computed tokens × cache-write price + written tokens × output price) |
| API cost after the cache expired | (all prompt tokens × input price + written tokens × output price) |
| Break-even: about 23,000 tasks against Claude Opus 5.5, about 46,000 against Claude Sonnet 5.5 | $9,398 ÷ (API cost per task − electricity per task) |
| Frontier APIs charge ten to twenty times more once the cache expires | input price ÷ cache-read price in `APIS`: 10× to 20× |

## Memory, capacity and energy

| Blog figure | Evidence |
|---|---|
| 7.5 and 8.3 GB of memory available while vLLM serves | `data/memory/free-while-serving.txt`, the `available` column |
| One KV value is 1,002,240 bytes | `memkv_write_bytes_total ÷ memkv_write_total` in `data/memkv/metrics-after-restart-tests.txt` |
| Each value uses one 1 MiB slot | `memkv_storage_used_bytes ÷ memkv_blocks_total` = 1,048,576 in the same file, and the console screenshot `images/memkv-console.png` |
| Each 1 TiB file has 1,048,575 slots of 1 MiB | `memkv_storage_usable_bytes ÷ 1,048,576` in the same file, and the screenshot |
| A KV block covers 256 tokens and is stored as two values, one per GPU | the restored token counts are multiples of 256 (124,160 = 485 × 256); there are two tensor-parallel workers |
| About 7,830 bytes of KV per token | 2 × 1,002,240 ÷ 256 |
| A RAM cache would hold about 2 million tokens, about 16 sessions | (7.5 + 8.3) GB ÷ 7,830 bytes; 2.0 M ÷ 126,600 |
| MemKV holds about 190 million tokens | 2 files × 1,048,575 slots ÷ 2 values per block × 256 tokens × 70% (MemKV starts evicting at 70% full) |
| 1 MiB fits about four times as many tokens as 4 MiB | one value per slot either way, and 4 MiB slots are four times larger |
| Recomputing a 103,000-token session: GPUs at 62 and 64 W for 53 s, about 1.8 Wh; 12 W idle | `data/power/power.json`, measured with `harness/power_probe.py` |

## Versions

`data/versions.json` records the version of every component in the blog's "What we ran" table.

## What the data does not show

- **Sample sizes are small.** The restart test is three pairs, always run with MemKV first. The 40-session test is one run of each setup, one after the other.
- **Answer quality was not graded.** MemKV does not change the model or its settings, but we did not compare the two setups' answers.
- **More than four agents at once was not tested.** The 40-session test kept four agents active.

## Which tests used which MemKV storage block size

MemKV logs each storage file it creates, with its block size. `data/memkv/filestore-log-spark1.jsonl` and `filestore-log-spark2.jsonl` hold those lines from both DGX Sparks:

| Storage file created (UTC) | Block size | Tests that ran on it |
|---|---|---|
| 2026-10-06 04:12 | 4 MiB (`block_size_bytes` 4194304, 262,143 slots) | Hermes restart test, 2026-10-06 05:27–06:38. Hermes 40 sessions, 2026-10-06 from 09:24. OpenClaw 40 sessions, 2026-10-07 07:29–17:44. |
| 2026-10-07 21:12 | 1 MiB (`block_size_bytes` 1048576, 1,048,575 slots) | OpenClaw restart test, 2026-10-07 21:31–22:42. |

The test times come from `results.jsonl`, `ocfleet-windows.jsonl` and `hfleet-*.t0` in `data/`.
