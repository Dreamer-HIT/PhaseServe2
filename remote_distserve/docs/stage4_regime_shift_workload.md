# Stage 4 Regime-Shift Workload

更新时间：2026-05-27

## 本阶段目标

构造一个更能证明 Phase/PBC 价值的动态 workload。该 workload 不再只测试单一 prompt-skew 或 decode-heavy 场景，而是在同一次 benchmark 中按时间顺序制造不同 pressure regime：

1. `prefill_skew`：长 prompt、短 output，主要压 TTFT 和 prefill batching。
2. `decode_heavy`：短/中 prompt、长 output，主要压 TPOT、decode queue 和 KV residency。
3. `mixed_slo`：长 prompt 与长 output 混合，制造跨阶段冲突。
4. `prefill_recovery`：回到 prefill-skew，测试系统能否从 decode/KV 压力恢复到 first-token-oriented scheduling。

这个 workload 的核心用途是验证：静态 `bps_kas` 只能固定组合 BPS 和 KAS，而 `phase` 应该通过 PBC 根据 pressure regime 动态调整预算和 decode utility intensity。

## 读取或修改的文件

新增：

- `benchmarks/phase_make_regime_shift_dataset.py`
- `scripts/run_phase_regime_shift_sweep.sh`

修改：

- `benchmarks/phase_native_benchmark.py`
- `scripts/run_phase_hetero_1p1d.sh`
- `scripts/run_phase_hetero_sweep.sh`

## 具体产物

### 1. Regime-shift dataset generator

`phase_make_regime_shift_dataset.py` 会生成两份文件：

- `.marshal`：DistServe 原生 `Dataset`，保持和现有 benchmark 兼容。
- `.metadata.json`：每个 request 的 `phase`、`phase_index`、`phase_request_index`、phase prompt/output mix、base request rate。

默认 profile 为 `regime_shift_v1`：

| phase | prompt mix | output mix | base rate |
|---|---|---|---:|
| `prefill_skew` | `64/512/1024/1536` | `32/64/128` | 6 |
| `decode_heavy` | `64/256/512` | `128/256/512/1024` | 3 |
| `mixed_slo` | `64/512/1024/1536` | `64/128/512/1024` | 4 |
| `prefill_recovery` | `64/512/1024/1536` | `32/64/128` | 6 |

### 2. Benchmark support for per-phase arrival rates

`phase_native_benchmark.py` 新增：

- `--request-metadata`
- `--phase-rate-schedule`
- `--phase-rate-scale`

当提供 request metadata 时，raw record 和 summary bucket 会新增：

- `workload_phase`
- `workload_phase_index`
- `phase_request_index`
- `phase_request_rate`
- `buckets.workload_phase`

这允许我们按 workload phase 分别分析 TTFT/TPOT/throughput，并将 workload phase 与 PBC regime metrics 对齐。

### 3. Sweep entry

`run_phase_regime_shift_sweep.sh` 默认配置：

```text
POLICIES="fcfs bps kas bps_kas phase"
PHASE_RATE_SCHEDULE="prefill_skew:6,decode_heavy:3,mixed_slo:4,prefill_recovery:6"
PHASE_REQUEST_COUNTS="24,24,24,24"
NUM_PROMPTS=96
MAX_TOTAL_TOKENS=2600
```

`RATES` 在该脚本中表示 phase-rate scale。例如 `RATES="0.75 1.0 1.25"` 会整体放大或缩小每个 phase 的 arrival rate。

## 最小验证

远端语法验证：

- `python -m py_compile benchmarks/phase_native_benchmark.py benchmarks/phase_make_regime_shift_dataset.py`
- `bash -n scripts/run_phase_hetero_1p1d.sh scripts/run_phase_hetero_sweep.sh scripts/run_phase_regime_shift_sweep.sh`

均通过。

远端 dataset smoke：

```text
/root/data/phase_scheduler_results/regime_shift_dataset_smoke
```

已确认 `.marshal` 和 `.metadata.json` 均可生成，四个 phase 的 prompt/output 分布符合预期。

## OPT-13B 小规模 smoke

结果目录：

```text
/root/data/phase_scheduler_results/stage4_regime_shift_smoke_opt13b_20260527_204830
```

配置：

- model：`/root/data/models/opt-13b`
- serving：1P1D，2 x A800 40GB
- GPU memory utilization：`0.85`
- seed：`0`
- phase request counts：`8,8,8,8`
- policies：`fcfs`、`bps_kas`、`phase`
- total requests per policy：`32`

整体结果：

| policy | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | output tok/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fcfs | 0.0958 | 0.1949 | 0.2029 | 0.2177 | 0.0311 | 0.2713 | 0.3945 | 0.4259 | 201.12 |
| bps_kas | 0.0888 | 0.1954 | 0.2015 | 0.2193 | 0.0348 | 0.2631 | 0.3587 | 0.4936 | 197.64 |
| phase | 0.0814 | 0.1921 | 0.2036 | 0.2222 | 0.0349 | 0.2634 | 0.3581 | 0.4918 | 198.13 |

按 workload phase 的结果已经进入 `buckets.workload_phase`。小样本下不做性能结论，只记录机制链路：

| policy | component | records | mean decode utility intensity | regimes |
|---|---|---:|---:|---|
| bps_kas | context | 31 | 1.000 | `STATIC:31` |
| bps_kas | decode | 1592 | 1.000 | `STATIC:1560` |
| phase | context | 31 | 0.419 | `DECODE_HEAVY:12, MIXED_SLO:19` |
| phase | decode | 1588 | 0.201 | `DECODE_HEAVY:235, FIRST_TOKEN_LIMITED:365, MIXED_SLO:956` |

## 当前结论

这次 smoke 只证明三件事：

1. Regime-shift workload 生成、分阶段 arrival、原生 serving benchmark、summary、bucket analysis 全链路已打通。
2. `workload_phase` bucket 已进入 summary 和 sweep analysis，后续可以分别画 prefill/decode/mixed/recovery phase 的 TTFT/TPOT。
3. `phase` 的 PBC regime metrics 与静态 `bps_kas` 已经出现机制差异：`phase` 动态输出 `DECODE_HEAVY/FIRST_TOKEN_LIMITED/MIXED_SLO`，`bps_kas` 保持 `STATIC`。

这次不能作为论文结果，因为每个 phase 只有 8 个请求，tail 指标方差太大。

## 验收标准

已通过：

- 能生成 `.marshal` 和 `.metadata.json`。
- benchmark 能读取 request metadata。
- summary 中出现 `buckets.workload_phase`。
- sweep analysis 能处理新增 bucket type。
- OPT-13B 小规模 `fcfs/bps_kas/phase` 均完成。

待完成：

- 用 `24,24,24,24` 或更大 phase request count 跑 `fcfs/bps/kas/bps_kas/phase`。
- 至少跑 seed0/1。
- 增加 `RATES="0.75 1.0 1.25"` 或相邻区间，寻找 SLO/TTFT/TPOT 都有区分度的展示范围。
- 将 workload phase 与 PBC regime 的时间序列对齐，证明 PBC 的切换不是噪声。

## 风险和阻塞点

1. Regime shift 的 phase 顺序会带来 carry-over effect。例如 `prefill_recovery` 的 TPOT 可能反映前一个 phase 的 decode backlog，而不是自身 output 长度。这不是 bug，但论文中要解释为 pressure propagation。
2. 如果 phase 太短，PBC smoothing/hysteresis 可能来不及稳定；正式实验应使用每 phase 至少 24 或 48 个请求。
3. 如果 phase 太长，动态 workload 会退化成多个静态 workload 拼接；正式实验需要同时报告 phase-local metric 和 transition-window metric。
4. `RATES` 现在表示 phase-rate scale，不是直接 total req/s；论文图中必须换算并标注清楚。

## 高压 pilot：rate scale 1.5

用户判断“rates 大效果会更明显”。这一判断是对的，但需要避免直接进入完全过载区。为此先跑一个高压 pilot：

结果目录：

```text
/root/data/phase_scheduler_results/stage4_regime_shift_highrate_pilot_opt13b_20260527_205805
```

配置：

- model：`/root/data/models/opt-13b`
- serving：1P1D，2 x A800 40GB
- GPU memory utilization：`0.85`
- seed：`0`
- phase request counts：`24,24,24,24`
- rate scale：`1.5`
- effective phase rates：`prefill_skew=9 req/s`，`decode_heavy=4.5 req/s`，`mixed_slo=6 req/s`，`prefill_recovery=9 req/s`
- policies：`fcfs`、`bps_kas`、`phase`

整体结果：

| policy | SLO | TTFT p50 | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p50 | TPOT p90 | TPOT p95 | TPOT p99 | output tok/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fcfs | 0.667 | 0.173 | 34.100 | 36.724 | 46.752 | 0.075 | 0.720 | 0.756 | 0.817 | 267.45 |
| bps_kas | 0.677 | 0.165 | 33.385 | 35.898 | 47.706 | 0.072 | 0.614 | 0.811 | 0.872 | 251.09 |
| phase | 0.677 | 0.176 | 32.812 | 34.990 | 47.736 | 0.071 | 0.634 | 0.821 | 0.879 | 252.92 |

相对 FCFS：

| policy | SLO delta | TTFT p90 | TTFT p95 | TTFT p99 | TPOT p90 | TPOT p95 | TPOT p99 | output tok/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| bps_kas | +1.04 pp | 0.979 | 0.978 | 1.020 | 0.852 | 1.073 | 1.067 | 0.939 |
| phase | +1.04 pp | 0.962 | 0.953 | 1.021 | 0.881 | 1.085 | 1.075 | 0.946 |

按 workload phase 拆分：

| phase | policy | SLO | TTFT p90 | TTFT p99 | TPOT p90 | TPOT p99 |
|---|---|---:|---:|---:|---:|---:|
| prefill_skew | fcfs | 1.000 | 0.195 | 0.251 | 0.059 | 0.063 |
| prefill_skew | phase | 1.000 | 0.219 | 0.284 | 0.053 | 0.062 |
| decode_heavy | fcfs | 1.000 | 0.076 | 0.084 | 0.194 | 0.232 |
| decode_heavy | phase | 1.000 | 0.083 | 0.092 | 0.133 | 0.183 |
| mixed_slo | fcfs | 0.667 | 23.459 | 24.895 | 0.512 | 0.616 |
| mixed_slo | phase | 0.708 | 18.996 | 21.591 | 0.418 | 0.538 |
| prefill_recovery | fcfs | 0.000 | 42.794 | 46.779 | 0.785 | 0.820 |
| prefill_recovery | phase | 0.000 | 38.142 | 48.299 | 0.845 | 0.881 |

机制指标：

| policy | component | records | mean decode utility intensity | regimes | mean prefill budget ratio |
|---|---|---:|---:|---|---:|
| bps_kas | context | 12716 | 1.000 | `STATIC:12716` | 1.000 |
| bps_kas | decode | 3020 | 1.000 | `STATIC:2924` | n/a |
| phase | context | 12550 | 0.364 | `DECODE_HEAVY:4036, FIRST_TOKEN_LIMITED:8494, MIXED_SLO:20` | 0.901 |
| phase | decode | 3016 | 0.335 | `DECODE_HEAVY:836, FIRST_TOKEN_LIMITED:1463, MIXED_SLO:621` | n/a |

### 高压 pilot 结论

1. rate scale `1.5` 比 smoke 的 `1.0` 更有区分度：FCFS 的 SLO 降到 `66.7%`，TTFT p90/p99 被拉到 `34.1s/46.8s`。
2. `phase` 在整体 TTFT p90/p95 上优于 FCFS，也略优于 `bps_kas`；在 `mixed_slo` phase 同时改善 TTFT p90 和 TPOT p90。
3. 代价是 TPOT p95/p99 和 output throughput 变差，尤其在 `prefill_recovery` 阶段有 carry-over pressure。
4. 因此更高 rate 的方向是对的，但 `1.5` 已接近“展示 tradeoff”的区间，而不是无条件更好。正式实验应扫 `1.25/1.5/1.75`，并把 claim 定位为 high-pressure regime shift 下的 SLO/TTFT-p90/phase-local tradeoff，而不是所有 tail 指标同时提升。
