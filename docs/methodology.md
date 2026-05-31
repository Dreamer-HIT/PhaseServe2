# PhaseServe 方法论设计文档

本文档定义 PhaseServe 的方法论、算法接口、系统边界和验证指标。

## 方法主线

PhaseServe 是一个 **typed regime-aware pressure-budgeted phase scheduling** 方法。它面向 prefill-decode disaggregated LLM serving，包含一个核心控制器 PBC，以及两个受预算、瓶颈 regime、跨阶段冲突仲裁与输出尾部 eligibility 约束的执行策略 BPS 和 KAS。

本文档只记录 PhaseServe 的方法定义、算法接口、系统边界和验证条件。核心主线是：

> 在 prefill-decode 解耦之后，decode-side queue、KV block、bridge queue 和 swap pressure 仍然会向 prefill 反向传播；PhaseServe 将这种运行时压力转化为 typed admission budget、regime owner、phase intensity 和 output-tail eligibility，并让 prefill/decode 在该预算、瓶颈归属与冲突仲裁下执行阶段特化调度。

PhaseServe 的核心机制聚焦在运行时调度与预算控制：

1. PBC 负责本地 pressure-to-budget control，并根据 pressure signature 识别当前瓶颈 regime；当 first-token pressure 与 decode-tail pressure 同时升高时，PBC 用显式 conflict owner 决定优先释放哪条 pressure path。
2. BPS 和 KAS 负责 prefill/decode 两个阶段的 budgeted execution；二者的执行强度由 PBC 的 regime 判断、bridge pressure 和 output-tail eligibility 共同仲裁。
3. 以机制信号、SLO goodput、regime-local bottleneck metric、tail latency、公平性和开销作为验证对象；绝对 speedup 作为结果报告项。

PhaseServe 的核心定义是：

> PhaseServe 是一个面向 prefill-decode 解耦式 LLM serving 的 regime-aware pressure-budgeted online scheduling framework。PBC 将 first-token、decode-side queue、KV block、bridge queue 和 swap pressure 映射为 admission budget、safety margin、decode utility intensity、conflict owner 和 output-tail eligibility；BPS 在该 budget 下执行 known-size prefill shaping；KAS 在 hard feasibility gates 下执行 intensity-controlled active-set shaping，并在 bridge/first-token pressure 高时通过 completion drain 释放可回收 KV footprint。

PBC 是一个有原则的 pressure-to-budget-regime controller：PBC 明确定义 pressure vector、budget vector、regime classifier、归一化方法、monotonic mapping、hysteresis/smoothing 和 bounded-pressure 论证。BPS 和 KAS 是同一个 budgeted online scheduling framework 在 prefill 和 decode 两个阶段上的实例化；PBC 决定二者在当前 workload regime 中谁承担主要 bottleneck metric。

## 方法主张

PhaseServe 是一个 regime-aware pressure-budgeted phase scheduling system for phase-disaggregated LLM serving。在完成 prefill/decode 静态资源解耦之后，剩余关键瓶颈同时包含阶段内调度不匹配，以及 decode 侧队列、KV 和 swap 压力通过 bridge 对 prefill 形成的反向约束。PhaseServe 将这些运行时压力持续转化为 admission budget、safety margin 和 phase-local utility intensity，并在该预算下执行 prefill batch shaping 与 KV-constrained decode active-set shaping，从而改善 workload 的瓶颈指标，例如 TTFT queueing、TPOT tail、SLO goodput 或不同长度 bucket 的公平性。

PhaseServe 按 workload regime 定义瓶颈指标，并显式报告 tradeoff。例如，prompt-skew / first-token-limited regime 以降低 TTFT tail 和 context queueing 为主要目标；decode-heavy / output-variance regime 以降低 TPOT tail 和 short-output slowdown 为主要目标；KV/swap-limited regime 以降低 infeasible rounds、swap stall 和 SLO miss 为主要目标。full PhaseServe 的端到端结果按 regime-local primary metric、SLO goodput 和 secondary tradeoff metrics 共同呈现。

这个主张的范围有三点：

1. 它和 DistServe 的关系清楚：DistServe 解决阶段解耦和资源配置，PhaseServe 解决解耦之后的运行时压力预算问题。
2. 它把局部 prefill/decode scheduling 放到一个统一的 pressure-to-budget-regime 控制框架下，使 PBC 的预算接口和 regime intensity 成为 BPS 和 KAS 的共同约束入口。
3. 它能做干净消融：regime-aware pressure-budget controller、prefill shaping、decode active-set shaping 可以分别打开和关闭。

## 最终算法呈现

最终方法由 **3 个算法** 呈现：一个核心 regime-aware pressure-budget controller，加两个 budgeted execution policies。

这 3 个算法分别回答 regime-aware pressure-budgeted phase scheduling 的三个问题：

| 算法 | 回答的问题 | 主要优化指标 | 允许的 tradeoff |
|---|---|---|---|
| Algorithm 1: PBC, Regime-Aware Pressure-Budget Controller | 如何把 decode-side queue/KV/swap pressure 转成 prefill/decode admission budget 与 phase utility intensity | SLO goodput、pressure overshoot、regime-local primary metric、bridge queue、swap pressure | 在不同 regime 下把收益集中到 TTFT、TPOT 或 memory-safety 指标，非瓶颈指标可能作为 tradeoff 报告 |
| Algorithm 2: BPS, Budgeted Prefill Shaping | 在 PBC 给定 budget 下如何选择 prefill batch | TTFT median/tail、context queue time、prefill utilization、KV handoff footprint | 在 decode pressure 高时可能牺牲部分 prefill token throughput |
| Algorithm 3: KAS, Output-Tail Eligible KV-Constrained Attained-Service Scheduling | 在 KV/swap budget、decode utility intensity、bridge pressure 和 output-tail eligibility 下如何选择 decode active set | TPOT P50/P90/P99、decode queue time、short-output slowdown、swap/infeasible rounds | short-output/prompt-skew regime 下 KAS 退化为 FCFS-compatible decode，以避免把 BPS 的 TTFT 收益转移成 decode-side first-token delay；bridge pressure 高时 KAS 优先完成可释放 KV 的近尾部请求；long-output/decode-heavy regime 下 KAS 使用 full attained-service/KV-aware priority |

算法说明顺序是：

1. 先给出一个统一的 **pressure-budget model**，定义 observable pressure、admission budget 和 workload bottleneck metric。
2. 再给出核心算法 PBC：将 decode-side pressure 转成 prefill budget、decode budget、safety margin 和 phase utility intensity。
3. 最后给出两个 budgeted execution policies：BPS 在 prefill 侧执行 batch shaping，KAS 在 decode 侧执行 intensity-controlled active-set shaping。

PhaseServe 的方法叙事是：

> PhaseServe converts runtime pressure into admission budgets and bottleneck-regime intensities, then uses budgeted prefill and decode shaping policies to optimize the regime-local bottleneck while bounding fairness and scheduling overhead.

中文表述：

> PhaseServe 将运行时压力转化为 admission budget 与瓶颈 regime intensity，再用受预算约束的 prefill/decode shaping 策略优化当前 regime 的瓶颈，同时约束公平性和调度开销。

## 核心研究命题

Phase-disaggregated LLM serving 将 prefill 和 decode 拆分到不同资源池，以减少两个阶段之间的直接干扰。DistServe 和 Splitwise 已经证明这种方向是合理的。

但是，拆分之后并不意味着调度问题消失。相反，系统暴露出两个结构不同的局部在线调度问题：

- **Prefill 阶段**：prompt length 在执行前已知，prefill 计算量和 KV footprint 可以被粗略估计。
- **Decode 阶段**：最终输出长度未知，请求跨多个 decoding iteration 持续占用 KV cache 和 batch slot。

因此，disaggregated serving runtime 使用 regime-aware pressure-budgeted phase scheduling，在统一预算接口下分别处理 prefill 与 decode 的不同信息结构：

- 使用 PBC 将 decode-side queue、KV block 和 swap 压力转化为 admission budget。
- 使用 BPS 在 prefill 侧执行受预算约束的 cost-compatible batching。
- 使用 KAS 在 decode 侧执行受 KV/swap 约束的 attained-service active-set shaping。

这个命题产生了明确、可证伪、可实现的系统假设。

## 和已有系统的定位

PhaseServe 的方法论清楚地区分于以下相关系统：

- **DistServe**：将 prefill 和 decode 解耦，并联合优化资源分配和并行策略，以满足 TTFT 与 TPOT SLO。它是 PhaseServe 的直接 baseline 和实现基座。
- **Splitwise**：同样强调 prompt computation 与 token generation 的分离，并关注不同阶段的硬件和资源配置。
- **Sarathi / Sarathi-Serve**：在 colocated serving 场景中通过 chunked prefill 和 piggybacked decode 改善 batch 效率，但它没有重点研究 phase disaggregation 之后的阶段内调度。
- **vLLM / PagedAttention**：重点是 KV cache 内存管理和 continuous batching，而不是 disaggregated architecture 下的 phase-specialized scheduling。
- **Mooncake**：将 KV cache 管理作为生产级 disaggregated LLM serving 的核心，包括过载行为和 early rejection。它明确了 KV-centric 方法需要覆盖的系统边界。

主要参考系统：

- DistServe: https://arxiv.org/abs/2401.09670
- Splitwise: https://arxiv.org/abs/2311.18677
- Sarathi: https://arxiv.org/abs/2308.16369
- vLLM / PagedAttention: https://arxiv.org/abs/2309.06180
- Mooncake: https://arxiv.org/abs/2407.00079

定位矩阵如下：

| 系统 | 已解决的问题 | 没有重点解决的问题 | PhaseServe 的新增层次 | Baseline / ablation |
|---|---|---|---|---|
| DistServe | prefill/decode disaggregation、资源配置、SLO-aware placement | 解耦后的 runtime pressure propagation、阶段内 scheduler mismatch | 在 DistServe 资源规划之上增加 pressure-budgeted online scheduling | DistServe FCFS、DistServe + BPS、DistServe + KAS、PhaseServe full |
| Splitwise | prompt/generation 分离、异构硬件配置 | 在线 admission budget、KV/swap pressure feedback | 把 phase split 后的 runtime scheduling 作为主问题 | Splitwise-style static split 或等价静态配置 |
| Sarathi / Sarathi-Serve | colocated 场景下的 chunked prefill、decode piggybacking | disaggregated bridge queue、跨阶段 KV handoff pressure | 在解耦部署下控制 prefill 对 decode 的压力注入 | chunked prefill / size-aware prefill ablation |
| vLLM / PagedAttention | continuous batching、paged KV cache、KV 内存效率 | prefill/decode 解耦后的 phase-specific pressure budget | 使用 KV pressure 作为 scheduling constraint | FCFS continuous batching、pure LAS、KV-unaware LAS |
| Mooncake | KV-centric disaggregated serving、KV cache transfer 与 overload handling | 本文聚焦的轻量 scheduler/admission extension | 使用 KV pressure 作为 admission 和 scheduling 约束 | swap/residency 指标对比，避免泛化到 KV architecture |

PhaseServe 的主线是 **在 phase-disaggregated runtime 中把下游 pressure 转化为上游和本地 active-set 的预算约束**。因此，PBC 的 pressure chain、BPS 的 prefill shaping 和 KAS 的 KV-constrained active-set shaping 共同构成方法闭环；KV cache architecture 和 cluster-level routing 属于相邻系统层次。

## 系统抽象

方法论使用一个简洁抽象来描述运行时调度问题。

一个请求在系统中经过三个逻辑状态：

1. 等待 prefill。
2. prefill 完成后等待 decode admission。
3. 在 decode 阶段 active 或 suspended。

系统主要管理三个资源预算：

1. prefill batch 的 token budget。
2. decode active batch 的 request/token budget。
3. GPU/CPU KV block budget。

调度器只依赖低成本、运行时容易获得的信号：

1. prompt length。
2. waiting age。
3. generated token count。
4. current context length。
5. KV block residency 和 available block budget。

这个抽象足够支撑一个可实现的系统方法，因为它使用稳定可观测信号，并保留 serving engine 的主体结构。

## 统一 Pressure-Budget 问题

PhaseServe 的统一 pressure-budget optimization view 如下：

```text
observe pressure vector p(t)
compute admission budget vector b(t) = PBC(p(t), b(t-1))
run phase-local schedulers under b(t)
```

其中，`p(t)` 是由运行时低成本信号组成的归一化压力向量：

```text
p(t) = [
  q_bridge(t),      # bridge / unaccepted queue pressure
  f_first(t),       # first-token / handoff pressure
  q_decode(t),      # decode waiting pressure
  u_kv(t),          # GPU KV block utilization pressure
  s_swap(t),        # swap-in / swap-out pressure
  a_prefill(t)      # oldest prefill waiting pressure
]
```

每个分量都被归一化到 `[0, 1]`，并使用部署时可解释的容量或 SLO 阈值作为分母：

```text
q_bridge  = min(bridge_queue_len / bridge_queue_target, 1)
f_first   = min(first_decode_wait / first_decode_wait_target, 1)
q_decode  = min(decode_waiting_tokens_or_reqs / decode_queue_target, 1)
u_kv      = active_and_waiting_kv_blocks / gpu_block_capacity
s_swap    = min(swap_bytes_per_sec / swap_bandwidth_budget, 1)
a_prefill = min(oldest_prefill_wait / tau_prefill, 1)
```

PBC 输出的 `b(t)` 是结构化预算向量：

```text
b(t) = [
  c_prefill_tok(t),     # prefill token budget
  m_prefill_blk(t),     # prefill KV block safety margin
  s_decode_swap(t),     # decode swap-in budget per iteration
  l_decode_scan(t),     # decode scan limit
  i_decode_util(t),     # KAS utility intensity
  allow_oldest(t)       # bounded-progress override
]
```

PhaseServe 的统一目标是用低开销在线控制近似求解一个 bounded-pressure / goodput-maximization problem：

```text
maximize    SLO_goodput(b(t))
subject to  q_bridge(t) <= q_bridge_target
            f_first(t)  <= first_decode_wait_target
            q_decode(t) <= q_decode_target
            u_kv(t)     <= u_kv_target
            s_swap(t)   <= s_swap_target
            starvation_prefill <= tau_prefill
            starvation_decode  <= skip_threshold + infeasible_rounds
```

PBC 的角色是把这个约束问题转化为每轮可执行的预算 `b(t)`。换言之，PBC 是一个低开销近似求解器：当 pressure 低时扩大 feasible region 以提高 goodput，当 downstream pressure 接近约束边界时单调收缩 feasible region 以降低 pressure drift，并用 monotone feasible-region shrinking 近似 bounded-pressure goodput maximization。

### Pressure-Drift Surrogate

PBC 的“近似求解器”定义建立在一个可在线观测的 pressure-drift surrogate 上。设每类 pressure 的目标区间为 `theta_i`，超额压力为：

```text
d_i(t) = max(0, p_i(t) - theta_i)
```

系统压力势能定义为：

```text
Phi(t) =
  w_bridge * d_bridge(t)^2
  + w_first * d_first(t)^2
  + w_decode * d_decode(t)^2
  + w_kv     * d_kv(t)^2
  + w_swap   * d_swap(t)^2
```

预算 `b(t)` 影响两个可观测动作强度：

```text
I_prefill(t) =
  selected_prefill_tokens(t) / max_prefill_tokens
  + eta_kv * selected_prefill_blocks(t) / gpu_block_capacity

I_decode_swap(t) =
  admitted_swap_bytes(t) / swap_budget_per_iter
```

其中 `I_prefill` 近似刻画 prefill 向 bridge/decode/KV 注入的新压力，`I_decode_swap` 近似刻画 decode iteration 引入的 swap 压力。PBC 的在线目标可以写成：

```text
minimize_b  J(b; t)

J(b; t) =
  Phi_hat(t + 1 | b)
  - lambda_g * GoodputCapacity(b)
  + lambda_s * SmoothCost(b, b(t-1))
  + lambda_f * ProgressDebt(t)
```

`Phi_hat(t + 1 | b)` 是基于当前 pressure 与预算动作强度估计的下一轮压力势能：

```text
Phi_hat(t + 1 | b) =
  Phi(t)
  + c_prefill_to_bridge * I_prefill(b) * d_bridge(t)
  + c_prefill_to_decode * I_prefill(b) * d_decode(t)
  + c_prefill_to_kv     * I_prefill(b) * d_kv(t)
  + c_swap_to_decode    * I_decode_swap(b) * d_swap(t)
  - c_service           * ServiceCapacity(b)
```

PhaseServe 使用 typed monotonic mapping 作为这个 surrogate 的闭式近似：

```text
high d_bridge, d_first or d_decode -> decrease prefill_token_budget
high d_kv or d_swap       -> increase prefill_block_margin
high d_swap               -> decrease decode_swap_budget_per_iter
high d_kv or d_swap       -> decrease decode_scan_limit
high d_first with low hard pressure -> decrease KAS utility intensity
high d_decode or d_swap             -> increase KAS utility intensity
high progress debt        -> enable bounded-progress path
```

这个 surrogate 给出 PBC 的实验可验证对象：`Phi(t)`、`I_prefill(t)`、`I_decode_swap(t)`、budget movement、pressure overshoot 和 SLO goodput。PBC 的消融实验展示 typed budget mapping 是否同时降低 pressure drift 与保持 goodput capacity。

### Typed Pressure-Budget Dependency Graph

PBC 被定义为 typed pressure-to-budget-regime controller。PhaseServe 的关键设计是把不同类型的 pressure 映射到不同类型的 budget knob 和 utility intensity，并让这些 knob 分别约束 BPS 和 KAS 的动作空间。

因此，PBC 使用 typed dependency graph，将不同 pressure 分量映射到不同 budget knob：

| Pressure type | Budget knob | 约束的执行动作 | 预期降低的 pressure | 验证指标 |
|---|---|---|---|---|
| `p_bridge` | `prefill_token_budget` | BPS 限制每轮 context 注入的 prefill tokens | bridge / unaccepted queue 增长 | bridge queue、context dispatch selected tokens、TTFT-to-decode |
| `p_first` / `p_bridge` | `decode_utility_intensity`, `output_tail_eligibility` | KAS 在 first-token-limited 且无硬 KV/swap 压力时降低 attained-service / resident 排序强度；短输出 workload 退化为 FCFS-compatible decode | first-token handoff delay、BPS TTFT 收益被 decode 排序抵消 | KAS intensity、short-output gate、first-decode wait、TTFT tail |
| `p_first` / `p_bridge` 与 `p_decode` 同时高 | `conflict_owner`, `bridge_completion_drain` | PBC 默认将 owner 设为 first-token-limited；KAS 在 hard pressure 未触发时优先 first-decode、resident、近完成和高 KV-release 请求 | context-finished-but-unaccepted、bridge pressure、first-decode wait，同时释放 decode KV footprint | conflict owner、bridge completion drain active ratio、selected remaining output、protected blocked、context unaccepted |
| `p_decode` | `prefill_token_budget` | BPS 在 decode backlog 高时减少新的 decode arrivals | decode waiting pressure、TPOT tail | decode queue、TPOT p90/p99、SLO goodput |
| `p_decode` | `decode_utility_intensity`, `output_tail_eligibility` | KAS 在 decode-heavy 且输出尾部足够长时恢复或增强 attained-service active-set shaping | TPOT tail、short-output slowdown | KAS intensity、long-output gate、TPOT p50/p90/p99、short-output slowdown |
| `p_kv` | `prefill_block_margin` | BPS 为 decode 保留 GPU KV blocks，降低新 handoff footprint | GPU KV pressure、context-finished-but-unaccepted | free GPU blocks、protected blocked、bridge queue |
| `p_kv` | `decode_scan_limit` | KAS 缩小昂贵候选扫描范围，优先 resident / cheap active set | append-block contention、decode iteration stall | selected requests、resident ratio、infeasible GPU blocks |
| `p_kv` | hard feasibility gates | KAS 对 append block、swap-in block 和 resident state 做 admission feasibility | KV infeasible rounds、decode stall | append/swap infeasible rounds、resident ratio |
| `p_swap` | `decode_swap_budget_per_iter` | KAS 限制每轮 swap-in 请求数 | swap stall、TPOT tail | swap-ins、swap bytes、iteration stall |
| `p_swap` | `decode_scan_limit` | KAS 降低会触发 swap 的候选暴露度 | swap queue 与 swap-induced stall | swap budget infeasible rounds |
| `p_swap` | `decode_utility_intensity` | KAS 在 swap/TPOT 成为瓶颈时恢复 KV-aware active-set shaping，并保持 swap budget 硬约束 | swap-induced TPOT tail | KAS intensity、swap bytes、TPOT tail |
| `p_age` | `allow_protected_oldest` | BPS 允许 protected oldest 绕过 pressure budget，但不绕过物理可行性 | prefill starvation | protected feasible dispatch ratio、long-prompt max wait |
| `skip pressure` | starved tie-break | KAS 对 ready 且资源可行的 starved 请求提高同级优先级 | decode starvation | max skips、starved admission ratio |

这张 graph 是 PhaseServe 和普通 backpressure 的核心区别。普通 backpressure 往往只决定“是否继续放行”；PhaseServe 的 PBC 决定“收紧哪一个动作空间”：减少 prefill token injection、增加 KV safety margin、降低 swap-in admission，或触发 bounded-progress override。实验按这张 graph 验证 pressure、budget、action 和结果指标之间的链路。

PBC 的因果链如下：

```text
pressure approaches target
  -> PBC shrinks pressure-increasing feasible region
  -> BPS injects less KV footprint and KAS admits cheaper active sets
  -> bridge queue / swap pressure / pressure overshoot decreases
  -> more requests satisfy TTFT/TPOT SLO
  -> SLO goodput improves
```

PBC 的验证以这条 pressure chain 为核心，并同时报告 latency percentile、budget movement 和 pressure signal。

### Regime-Aware Pressure Arbitration

PBC 不只输出“收紧或放宽”的预算，还输出当前 workload 的瓶颈归属。瓶颈归属由 pressure signature 决定，并通过预算与 `decode_utility_intensity` 同时作用到 BPS 和 KAS。

| Regime | Pressure signature | Primary objective | BPS action | KAS action | Expected mechanism signal | Tradeoff |
|---|---|---|---|---|---|---|
| Prompt-skew / first-token-limited | `p_first` 或 `p_bridge` 高，`p_kv`/`p_swap` 未进入硬压力区间，平均目标输出较短 | TTFT tail、context queue time | 使用 cost-compatible batching，保护 oldest，避免大 KV footprint 注入 | short-output gate 使 KAS 退化为 FCFS-compatible decode；bridge pressure 高时启用 completion drain，优先 first-decode、resident 和近完成请求；始终保留 hard feasibility gates | selected prefill tokens 更集中、short-output gate 与 bridge completion drain 触发、TTFT tail 下降、protected blocked 下降 | TPOT tail 可能少于 full KAS 收益，但 completion drain 可以通过释放 KV footprint 改善部分 TPOT tail |
| Decode-heavy / output-variance | `p_decode` 高，output length variance 高，平均目标输出较长，first-token pressure 不是主导 | TPOT tail、short-output slowdown | 保持正常 prefill budget，必要时限制新增 decode arrivals | long-output gate 使 KAS 使用 full attained-service 和 resident preference | KAS intensity 高、long-output gate 触发、TPOT p50/p90/p99 下降、short-output slowdown 下降 | TTFT median/tail 可能不作为主收益 |
| KV/swap-limited | `p_kv` 或 `p_swap` 高，infeasible 或 swap stall 出现 | memory safety、swap stall、SLO goodput | 提高 block margin，缩小高 KV footprint handoff | hard feasibility gates 优先，swap budget 和 resident admission 主导 | infeasible rounds、swap bytes、iteration stall 下降 | admission 更保守，throughput 可能下降 |
| Mixed-SLO-limited | 多个 pressure 接近阈值但无单一硬瓶颈 | SLO goodput、pressure overshoot | budgeted BPS，控制 pressure injection | 中等 `decode_utility_intensity`，在 TPOT 和 TTFT 之间平滑折中 | pressure potential 与 overshoot 下降，SLO attainment 上升 | 单个 percentile 未必同时最优 |

`decode_utility_intensity` 的范围为 `[0, 1]`。当它接近 `0` 时，KAS 的 attained-service / resident preference 被弱化，decode 调度更接近 ready-time order；当它接近 `1` 时，KAS 使用完整的 attained-service 与 KV-aware priority。`output_tail_eligibility` 是更高优先级的离散 gate：短输出 workload 直接关闭 KAS 的局部重排，长输出 workload 直接启用 full KAS，中间区域才使用连续 intensity。无论 intensity 如何，batch size、GPU block、append block 和 swap budget 都是硬约束。

这个 regime arbitration 给出 PhaseServe 的效果边界：BPS 是 TTFT 的主要 owner，KAS 是 TPOT 与 KV/swap stall 的主要 owner，PBC 是 pressure drift、regime selection、conflict owner 和 SLO goodput 的主要 owner。full PhaseServe 的收益来自在不同 regime 中选择正确 owner，并在 owner 冲突时让 decode 侧动作服务于被选中的 pressure path，而不是把所有局部优化无条件叠加。

### Conflict Arbitration

由于 PBC、BPS 和 KAS 同时处理 performance、memory safety 和 progress，PhaseServe 采用显式冲突仲裁顺序，统一处理 `oldest progress`、`short-request priority` 和 `KV feasibility` 的优先级。

PhaseServe 的仲裁顺序如下：

```text
physical feasibility
  > memory/swap safety
  > bounded progress when feasible
  > bottleneck-regime ownership
  > first/decode conflict owner
  > phase-local utility
```

具体含义是：

1. **Physical feasibility first**：任何 request/batch 都遵守 hard batch size、token budget、GPU block availability 和 swap budget。protected-oldest 或 starved decode request 物理不可行时记录为 `protected_blocked` 或 `infeasible_rounds`。
2. **Memory/swap safety before local utility**：KV 或 swap pressure 高时，BPS 的 batch score 和 KAS 的 active-set selection 偏向低 KV footprint、resident requests 和低 swap-cost 请求。
3. **Bounded progress when feasible**：oldest prefill request 或 starved decode request 资源可行时，调度器为其提供 bounded-progress path。
4. **Bottleneck-regime ownership before local utility**：当 first-token / prompt-skew pressure 主导且无硬 KV/swap 压力时，BPS 的 TTFT 目标优先于 KAS 的 aggressive attained-service 排序；当 decode/KV/swap pressure 主导时，KAS 的 TPOT 与 hard-feasibility 目标优先。
5. **First/decode conflict owner before local utility**：当 `p_first`/`p_bridge` 与 `p_decode` 同时高而 hard KV/swap pressure 尚未触发时，PBC 默认把 owner 设为 first-token-limited。此时 KAS 不进入无约束 LAS，而是通过 bridge completion drain 优先执行 first decode、resident、近完成和高 KV-release 请求，用释放 KV footprint 的方式同时缓解 bridge pressure 与部分 TPOT tail。
6. **Phase-local utility last**：BPS 的 token fill/padding waste 和 KAS 的 attained-service priority 只在上述约束满足后用于排序。

这个仲裁规则也定义了实验解释口径：`protected_feasible_dispatch_ratio`、`protected_blocked`、`max_consecutive_skips` 和 `infeasible_rounds` 分别对应 progress、physical infeasibility、policy skip 和 resource infeasibility。

### Motivating Pressure-Transfer Model

PhaseServe 的必要性来自三个会产生 pressure transfer 的局部优化情形。

**Case 1：prefill-only utilization optimization。**

BPS 或任何 size-aware prefill scheduler 在只最大化 prefill token fill 时，会在 prompt-skew 或 burst 场景快速完成 context computation，并把大量请求推入 bridge/unaccepted queue。对于 decode 接近饱和的系统，这会增加 `p_bridge`、`p_decode` 和 `p_kv`，从而让用户实际 TTFT-to-first-decode 和 TPOT tail 恶化。此时 prefill utilization 提升不是端到端收益。

**Case 2：decode-only LAS optimization。**

Pure LAS/MLFQ 只按 attained service 优先短输出请求，不考虑 KV residency、GPU block availability 和 swap budget时，可能选择逻辑上高优先级但需要昂贵 swap-in 或无法 append KV block 的请求。结果是 decode iteration stall、swap pressure 和 GPU block infeasible rounds 上升，LAS 的短作业优先收益被 KV/swap 开销抵消。

**Case 3：uncoordinated local schedulers。**

prefill 和 decode 各自局部优化但没有共享 budget 时，prefill 端无法知道 decode/KV/swap 是否已经成为瓶颈，decode 端也无法控制新的 KV footprint 注入。系统会出现 pressure transfer：一个阶段的局部收益以另一个阶段的 queue、swap 或 tail latency 为代价。

因此，PBC 把 pressure transfer 转化为可观测、可消融的 budgeted action-space restriction。

BPS 和 KAS 在 `b(t)` 下选择阶段动作：

```text
select feasible action a_t in A_phase(b(t))
to maximize U_phase(a_t)
subject to progress invariant
```

其中：

- BPS 的 `a_t` 是一个 prefill batch，`U_phase` 由 token fill、padding waste、block risk 和 oldest bonus 构成。
- KAS 的 `a_t` 是一个 decode active set，`U_phase` 由 attained-service priority、resident preference、swap feasibility、skip-bounded fairness 和 PBC 给定的 `decode_utility_intensity` 构成。
- PBC 的 `b(t)` 决定二者的 feasible action set，`regime(t)` 决定当前 primary metric owner，是统一优化模板的约束与仲裁入口。

这个统一模板在两个阶段中的实例化如下：

| Phase policy | Action `a_t` | Feasible set `A_phase(b(t))` | Utility terms | Baseline equivalence | Added-by-PBC constraint | Progress invariant | Diagnostic metric |
|---|---|---|---|---|---|---|---|
| BPS | prefill batch | request/token/KV block budget、PBC prefill margin、bounded candidate window | token fill、padding waste、block risk、oldest bonus | bucket / size-aware batching | dynamic prefill token budget、block margin、small-KV preference | oldest request 超过 `tau_prefill` 后进入 protected dispatch path | long-prompt wait、TTFT tail、protected dispatch ratio |
| KAS | decode active set | decode request budget、GPU block budget、swap budget per iteration、scan limit | intensity-scaled attained-service priority、resident preference、swap feasibility、waiting age | LAS / MLFQ decode scheduling | swap budget、resident admission budget、scan limit、decode utility intensity under pressure | starved request 在资源可行时获得同级优先级 | KAS intensity、max skips、long-output slowdown、swap stall、resident admission ratio |

在该目标下，PhaseServe 在线维护两个性质：

1. **Bounded pressure**：当下游 pressure 高于目标区间时，PBC 单调收紧会继续注入下游压力的预算。
2. **Bounded progress**：即使下游 pressure 高，超过等待阈值的 oldest request 和 starved decode request 仍有受控通过路径。

更形式化地，PBC 满足：

```text
if p_i(t) increases, then pressure-increasing budgets do not increase
if p_i(t) remains high for H rounds, then injected KV footprint decreases or stays bounded
if a_prefill(t) reaches 1, then allow_oldest(t) = true
```

在这个统一视角下：

- BPS 是 `b(t)` 约束下的 known-size online batching。
- KAS 是 `b(t)` 与 `decode_utility_intensity(t)` 约束下的 unknown-size active-set selection。
- PBC 是两个阶段的共同预算、utility intensity 生成器和瓶颈 regime 仲裁器。

## 形式化问题建模

PhaseServe 被建模为一个 pressure-budgeted online control problem：PBC 根据下游压力生成 budget，BPS 和 KAS 分别在两个信息结构不同的阶段内执行预算约束下的在线调度。

### Prefill Model

对每个请求 `r`，prefill 阶段在调度前可观测：

```text
arrival_time(r)
prompt_len(r)
kv_blocks(r) = ceil((prompt_len(r) + 1) / block_size)
```

prefill scheduler 在每一轮选择一个 batch `B`。`B` 满足以下约束：

```text
|B| <= C_req
sum(prompt_len(r) for r in B) <= C_tok
sum(kv_blocks(r) for r in B) <= C_blk
```

其中 `C_req` 是最大 batch request 数，`C_tok` 是 prefill token budget，`C_blk` 是当前可用于 prefill handoff 的 KV block budget。

prefill 的优化目标是在线降低 TTFT tail：

```text
minimize p95/p99 over [queue_wait(r) + prefill_exec(r)]
subject to bounded waiting and feasible KV allocation
```

关键建模点是：`prompt_len(r)` 在调度时已知，因此 prefill 可以使用 known-size batching；但 batch execution 又受最长序列、token budget 和 KV block budget 共同约束，所以简单 shortest-job-first 不够。

### Decode Model

对每个请求 `r`，decode 阶段在调度前不可观测最终输出长度 `L_out(r)`。调度器只能在线观测：

```text
generated_tokens(r, t)
kv_residency(r, t)
kv_blocks(r, t)
ready_time(r, t)
```

每个 decode iteration 选择一个 active batch `D_t`。`D_t` 满足以下约束：

```text
|D_t| <= D_req
sum(new_token_budget(r) for r in D_t) <= D_tok
sum(required_gpu_blocks(r, t) for r in D_t) <= D_blk
swap_in_bytes(D_t) <= S_iter
```

decode 的优化目标是降低 token-level tail latency 和短请求 slowdown：

```text
minimize p95/p99 TPOT
and minimize slowdown_short(r) = completion_time(r) / ideal_decode_time(r)
subject to KV feasibility and starvation control
```

关键建模点是：`L_out(r)` 不可知，因此 decode 不使用 shortest-remaining-time；`generated_tokens(r, t)` 是 attained service，可以作为在线调度的稳健信号。

### Paper-Level Hypothesis

PhaseServe 的核心假设为：

> 在 prefill-decode disaggregated serving 中，阶段间资源隔离之后的剩余瓶颈主要来自阶段内信息不匹配和阶段间压力传播。将 first-token/decode-side queue/KV/swap pressure 转化为 admission budget、regime 和 utility intensity，并在该 budget 下分别执行 known-size prefill shaping 与 intensity-controlled unknown-size KV-constrained decode shaping，可以在异构 workload 下改善对应瓶颈指标和 SLO goodput。

这个假设对应明确的适用区间：PhaseServe 面向 prompt/output heterogeneity 和接近饱和的 pressure-bearing workload；在高度同质或远低于饱和的 workload 中，收益主要体现为低开销 no-regression。

### Regime Prediction and Claim Discipline

PhaseServe 的论文 claim 在实验前先由机制归属确定，避免把相互冲突的目标合并成“所有指标同时提升”的单一叙事。

1. **Metric ownership**：TTFT queueing 主要由 BPS 负责，TPOT tail 和 short-output slowdown 主要由 KAS 负责，pressure overshoot、bridge queue 与 SLO goodput 主要由 PBC 负责。
2. **Regime prediction**：每个 workload 在运行前声明 pressure signature、primary metric、secondary tradeoff metric 和预期机制信号。例如 prompt-skew workload 预期 BPS 降低 TTFT tail，decode-heavy workload 预期 KAS 降低 TPOT tail。
3. **Conflict check**：当 BPS 与 KAS 的局部目标冲突时，PBC 必须通过 budget 或 utility intensity 给出仲裁，而不是让两个策略无条件叠加。
4. **Hard-pressure monotonicity**：KV/swap hard pressure 上升时，任何策略都不能放宽 GPU block、append block 或 swap budget 约束。
5. **Claim narrowing**：论文结果只写入已由机制信号和端到端指标共同支持的 claim；未被当前 workload 验证的效果保留为边界或后续扩展。

这个规则把方法论、实现和实验连接起来：实验解释优先沿 `pressure -> budget/intensity -> action -> metric` 链路展开，claim 只绑定到对应 regime 的 primary metric 和机制信号。

## 执行策略一：BPS：Budgeted Prefill Shaping

本文按执行策略到控制器的顺序展开机制细节；正文算法呈现采用 PBC、BPS、KAS 的顺序。BPS 是 prefill 侧的预算执行策略，它显式接受 PBC 给出的 admission budget。

### 问题

DistServe 当前的 context-stage scheduler 是 FCFS。它按照到达顺序把请求加入 batch，直到触发 max batch size、max tokens per batch 或 GPU block budget 限制。

这种策略简单，但在 prompt length 高度偏斜时容易出现两个问题：

1. 长 prompt 阻塞短 prompt，导致 TTFT tail latency 上升。
2. batch 内 prompt 长度混杂，造成 prefill 阶段 padding、同步和资源利用效率下降。

### 设计原则

Prefill 可以被看作 known-size online batching problem。虽然准确 prefill latency 仍然受 kernel、并行策略和硬件状态影响，但 prompt length 在请求进入系统时已经可见，并且与 prefill 计算量和 KV allocation 强相关。

因此，prefill scheduler 使用一个可实现的 bounded-window known-size batching 形式：

> 在一个有界候选窗口内，按照 prompt cost compatibility 构造 batch，同时遵守 PBC 给出的 prefill token budget、KV block margin 和 protected-oldest 规则。

这个设计比“泛化 utility-aware batching”更硬，因为它有明确输入、明确约束、明确 tie-breaker，并且可以直接和 FCFS、shortest-prompt-first、bucket batching 做对照实验。

BPS 与普通 bucket batching 的关键区别是：bucket 定义候选 batch 的 cost compatibility，PBC budget 决定候选 batch 是否可行以及 batch score 如何解释。在 decode/KV pressure 低时，BPS 可以更积极地填满 token budget；在 bridge/decode pressure 高时，`prefill_token_budget` 收缩，BPS 降低大 prefill batch 注入；在 KV/swap pressure 高时，`prefill_block_margin` 上升，BPS 为 decode 保留 KV blocks。也就是说，BPS 的动作空间由 PBC typed budgets 动态改变。

### 算法输入

BPS 使用 DistServe 中容易获得的运行时信号：

1. `prompt_len(r)`：请求输入长度。
2. `wait_time(r)`：请求进入 context waiting queue 后的等待时间。
3. `num_blocks(r)`：prefill 后需要的 KV block 数，可由 prompt length 和 block size 估计。
4. `max_batch_size`：context engine 支持的最大 batch request 数。
5. `max_tokens_per_batch`：context engine 支持的最大 prefill token 数。
6. `free_gpu_blocks`：当前可用 GPU block 数。
7. `AdmissionBudget`：来自 PBC 的预算对象，包含 `prefill_token_budget` 和 `prefill_block_margin`。

### 核心机制

BPS 每轮调度分四步。

**第一步：有界候选窗口。**

从 FCFS waiting queue 的队首取最多 `K` 个请求作为候选窗口 `C`。窗口大小 `K` 是实现参数，用于限定重排范围，并避免为了等更好的 batch composition 而人为增加不确定等待。

窗口中的 oldest request 被标记为 protected request，并获得 bounded-progress path。

**第二步：cost bucket。**

按照 prompt length 将候选请求划入粗粒度桶，例如：

```text
B0:   0 < len <= 256
B1: 256 < len <= 512
B2: 512 < len <= 1024
B3: 1024 < len <= 2048
B4: len > 2048
```

桶边界由模型最大长度和 workload 分布确定。bucket 只依赖 prompt length，不依赖 learned predictor。

**第三步：构造 cost-compatible batch。**

对每个非空 bucket，构造一个候选 batch。batch 满足以下约束：

```text
|B| <= max_batch_size
sum(prompt_len(r) for r in B) <= min(max_tokens_per_batch, prefill_token_budget)
sum(num_blocks(r) for r in B) <= free_gpu_blocks - prefill_block_margin
```

decode pressure 较高时，`prefill_block_margin` 增大，候选 batch 的 token budget 和 KV footprint 更保守；decode pressure 较低时，budget 放宽，prefill 可以更积极地填满 batch。

同一 bucket 内按 `(protected, wait_time, prompt_len)` 排序：

1. 位于该 bucket 的 protected request 优先尝试加入。
2. 其他请求优先选择等待时间更长者。
3. 在等待时间相近时优先选择 prompt length 更接近 bucket median 的请求，降低 padding waste。

**第四步：选择 batch。**

从所有 bucket 产生的候选 batch 中选择一个得分最高者。得分使用可测量项：

```text
score(B) =
  token_fill(B)
  - alpha * pad_waste(B)
  - beta  * pressure_multiplier * block_risk(B)
  + gamma * oldest_bonus(B)
```

其中：

```text
token_fill(B) = sum(prompt_len(r) for r in B) / max_tokens_per_batch
pad_waste(B) = (max_len(B) * |B| - sum(prompt_len(r) for r in B)) / max_tokens_per_batch
block_risk(B) = sum(num_blocks(r) for r in B) / max(free_gpu_blocks, 1)
pressure_multiplier = 1 + rho_down
oldest_bonus(B) = 1 if protected request in B else 0
```

`pressure_multiplier` 是 BPS-PBC 耦合的显式体现。KV/decode pressure 高时，同样的 block footprint 会被更强惩罚；这让 BPS 从“填满 token batch”转向“在保证 progress 的前提下降低 downstream footprint”。

protected request 的等待时间超过 `tau_prefill` 时，BPS 只在包含 protected request 的候选 batch 中选择；没有可行 batch 时，单独 dispatch protected request。

protected request 在忽略 pressure budget 后仍不满足物理资源约束时，例如单请求 token 数超过 engine 上限或 GPU blocks 不足，本轮记录 `protected_blocked`。BPS 的 bounded-progress claim 作用于资源可行的请求。

### 伪代码

```text
BPS(waiting_queue, admission_budget):
  C = first K requests from waiting_queue
  p = oldest request in C
  budget = admission_budget.prefill
  buckets = group C by prompt length
  candidates = []

  for bucket in buckets:
    B = []
    for r in ordered(bucket):
      if feasible(B + r, budget.prefill_token_budget, budget.prefill_block_margin):
        B.add(r)
    if B is not empty:
      candidates.add(B)

  if wait_time(p) >= tau_prefill:
    candidates = {B in candidates | p in B}
    if candidates is empty:
      if physically_feasible({p}):
        return {p}
      return empty_with_protected_blocked

  return argmax_B score(B)
```

### 设计不变量

BPS 维护四个不变量：

1. **Feasibility invariant**：任何被 dispatch 的 batch 都满足 request、token 和 KV block 三类资源约束。
2. **Pressure-coupled feasibility invariant**：`prefill_token_budget` 和 `prefill_block_margin` 进入 batch feasibility。
3. **Oldest protection invariant**：当 oldest request 的等待时间超过 `tau_prefill` 时，下一次 dispatch 包含它；无法与其他请求组成 pressure-budget-feasible batch 时，在物理可行条件下单独 dispatch；物理不可行时记录 blocked。
4. **No artificial waiting invariant**：scheduler 不主动等待未来请求，只在当前 waiting queue 的前 `K` 个请求内重排。

第四个不变量限定了 BPS 的重排范围：BPS 只重排已经到达的 bounded window，不主动等待未来请求来换取更好 batch composition。

### 复杂度与边界

令候选窗口大小为 `K`，bucket 数为 `G`，最大 batch size 为 `B_max`。BPS 每轮最多检查 `K` 个请求并构造至多 `G` 个候选 batch。

```text
time complexity: O(K log K + G * K)
space complexity: O(K + G)
```

bucket 内按 waiting queue 顺序扫描、并省略完整排序时，复杂度为：

```text
time complexity: O(K + G * K)
```

在 DistServe 中，`K` 设置为小常数，例如 `2x` 到 `4x` 的 `max_batch_size`。这样 scheduler overhead 与模型 prefill 执行时间相比保持可忽略。

### Starvation Bound

BPS 的 starvation bound 给出工程上可验证的上界：

```text
wait_time(r) <= tau_prefill + one_dispatch_interval + prefill_exec_time(protected_batch)
```

含义是：一个请求一旦成为 protected oldest request 并超过 `tau_prefill`，下一次调度进入 protected dispatch path。实验报告：

1. long-prompt p95/p99 TTFT。
2. long-prompt maximum observed queue wait。
3. 被 protected dispatch 触发的请求比例。
4. feasible protected dispatch ratio。
5. protected blocked count。

这些指标共同刻画 BPS 对短 prompt 响应和长 prompt bounded progress 的影响。

### 实现映射

BPS 可以直接在 DistServe 的 `ContextStageFCFSScheduler.get_next_batch_and_pop` 上实现：

1. 保留原有 waiting queue 数据结构，避免重写 context engine。
2. 将原来的 FCFS append loop 替换为 candidate-window + bucket batch selection。
3. 使用 DistServe 已有的 `max_batch_size`、`max_tokens_per_batch`、block budget 检查。
4. BPS 使用 `prompt_len` 作为 cost proxy。
5. `AdmissionBudget` 动态调节 token budget 和 safety margin。

### 实验设计

BPS 单独验证以下问题：

1. 相对 DistServe FCFS 是否降低 TTFT p90/p99。
2. 相对 shortest-prompt-first 是否更公平，是否控制 long-prompt starvation。
3. 相对 pure bucket batching 是否在低负载下控制额外等待。
4. 当 prompt length skew 增大时，收益是否更明显。
5. scheduler CPU overhead 是否低于 prefill 执行时间的 1% 或一个可接受阈值。

### 可验证主张

BPS 的核心主张是：

> 在 prompt length 分布偏斜且系统接近饱和时，budgeted cost-compatible prefill shaping 可以降低 TTFT tail latency；当 PBC 收紧预算时，它通过保守 prefill admission 减少阶段间压力传播，同时通过 protected oldest request 保持长 prompt 的 bounded waiting。

### 方法范围

BPS 聚焦在线、低开销、可消融的 prefill batch shaping：

- 优化目标是在线 tail latency 与 bounded waiting。
- 调度信号使用 prompt length、waiting age 和 KV block footprint。
- homogeneous prompt length workload 主要用于验证 no-regression 和 scheduler overhead。
- size-aware scheduling 变体作为 baseline 与 sensitivity 对照。

## 执行策略二：KAS：Intensity-Controlled KV-Constrained Attained-Service Scheduling

KAS 是 decode 侧的预算执行策略。它要求 decode active set 同时满足 attained-service priority、KV residency 和 swap budget 三类约束，并接受 PBC 给定的 `decode_utility_intensity` 来调节 attained-service / resident preference 的强度。

### 问题

DistServe 当前的 decode scheduler 也是 FCFS-like。它接收从 context stage 迁移过来的请求，将其放入 waiting queue，并按顺序填充 decode batch；对于 swapped-out requests，只做简单的 swap-in preference。

Decode 和 prefill 的核心区别是：

1. 输出长度未知。
2. 长请求会跨很多 decode iterations 持续占用 batch slot 和 KV cache。
3. 短请求可能被长请求拖累，即使每个 decode iteration 本身很短。

因此，decode 阶段继续使用 FCFS 会在输出长度高度可变时造成明显 tail latency 问题。

### 设计原则

Decode 被建模为 unknown-size online scheduling problem。因为最终 job size 不可知，调度器不直接做 shortest-job-first 或 shortest-remaining-processing-time。

可行的近似是使用 attained service：

> 已经生成 token 越少的请求，越可能是短请求，并获得更高的前台优先级；已经获得大量服务的请求可以被降级，同时由 aging 机制控制 starvation。

KAS 的主要机制是：

> Decode 是 unknown-size iterative serving。KAS 用 generated tokens 作为 attained service，近似 least-attained-service scheduling；同时把 KV residency、KV footprint、free block budget 和 swap budget 作为 admission 约束，避免调度器选择一个理论上紧急但当前激活代价过高的请求。PBC 通过 `decode_utility_intensity` 决定 KAS 当前更接近 ready-time / FCFS decode，还是更接近完整 KV-aware LAS decode。

这比通用 MLFQ 更贴合当前方法边界，因为它把 scheduling 和 LLM serving 的 KV memory 约束绑定起来，但又不夸大成完整 KV cache architecture。

KAS 与 pure LAS 的关键区别是：attained-service priority 只决定扫描顺序，KV/swap hard constraints 定义 admission 边界，且 attained-service priority 的强度由 PBC 按 regime 调节。一个低 attained-service 请求在本轮 `decode_swap_budget_per_iter` 已耗尽、或无法为即将生成的 next token 预留 GPU block 时，被标记为 infeasible。这样 KAS 的收益来自在资源可行边界内优先服务低 attained-service、resident 或低 swap-cost 请求；当 first-token pressure 主导时，KAS 减弱该局部偏好，避免把 BPS 改善的 prefill queueing 转移为 decode-side first-token delay。

### 算法输入

KAS 使用以下状态：

1. `arrival_time`
2. `last_ready_time`
3. `generated_tokens`
4. `attained_level`
5. `consecutive_skips`
6. `kv_resident`
7. `num_gpu_blocks`
8. `num_cpu_blocks`
9. `expected_new_blocks_per_step`
10. `decode_utility_intensity`：来自 PBC 的 regime intensity，范围为 `[0, 1]`。
11. `slo_deadline`，可选扩展信号；核心算法不依赖 SLO deadline。

### 队列组织

KAS 维护多个 attained-service queues，而不是抽象 MLFQ：

```text
Q0: generated_tokens in [0, 1)
Q1: generated_tokens in [1, 2)
Q2: generated_tokens in [2, 4)
Q3: generated_tokens in [4, 8)
Q4: generated_tokens in [8, 16)
...
Qn: generated_tokens >= 2^(n-1)
```

这种指数桶有三个好处：

1. 新请求和短输出请求获得更细粒度响应。
2. 长输出请求不会每个 token 都触发频繁 queue reshuffle。
3. 队列层级和 generated token count 直接绑定，实验解释更清楚。

请求刚进入 decode 时进入 `Q0`。每执行一个 decode iteration，`generated_tokens` 增加 1；跨过当前队列边界后移动到更低优先级队列。

### Admission 规则

每轮 decode iteration 之前，scheduler 从高优先级队列到低优先级队列扫描请求。一个请求进入 active batch 需同时满足：

```text
batch_size_ok
and token_budget_ok
and gpu_block_budget_ok
and swap_budget_ok
```

其中：

```text
gpu_block_budget_ok =
  kv_resident(r)
  or free_gpu_blocks >= blocks_to_swap_in(r) + expected_new_blocks_per_step(r)

swap_budget_ok =
  kv_resident(r)
  or current_swap_in_bytes + kv_size(r) <= swap_in_budget_per_iter
```

这些条件是 hard feasibility gates，而不是 tie-breaker。KAS 首先排除不可行请求，再在可行集合中使用 intensity-scaled attained-service、starved flag、residency 和 waiting age 排序。被排除的请求记录 infeasible reason：

```text
infeasible_reason in {
  batch_size,
  token_budget,
  gpu_append_blocks,
  gpu_swap_blocks,
  swap_budget
}
```

核心实现聚焦 swap-aware admission；真正异步 prefetch 属于可组合扩展：

- 请求 KV 已在 GPU 时，admission 成本低。
- 请求 KV 在 CPU 时，admission 消耗本轮 swap budget。
- GPU block 紧张时，优先保留高优先级和 resident 请求。

### KV-Constrained Claim Contract

KAS 的 `KV-constrained` claim 由 hard gates、资源账本和诊断指标共同定义。一个 decode request 的 admission 决策包含以下状态转换：

```text
ready
  -> admitted_resident
  -> admitted_with_swap
  -> infeasible_gpu_append
  -> infeasible_gpu_swap
  -> infeasible_swap_budget
  -> policy_skipped
```

这些状态分别对应可计数事件：

| Event | 触发条件 | 计入指标 | 作用 |
|---|---|---|---|
| `admitted_resident` | KV blocks 已在 GPU，append block 可用 | resident admission ratio | 衡量 resident-first active set |
| `admitted_with_swap` | KV 在 CPU，swap budget 与 GPU blocks 均可用 | swap bytes、swap-in count | 衡量受控 swap admission |
| `infeasible_gpu_append` | next-token append blocks 不足 | append-block infeasible rounds | 分离 append KV 压力 |
| `infeasible_gpu_swap` | swap-in 后 GPU blocks 不足 | swap-block infeasible rounds | 分离 swap-in KV 压力 |
| `infeasible_swap_budget` | 本轮 swap budget 已耗尽 | swap-budget infeasible rounds | 分离 bandwidth pressure |
| `policy_skipped` | 资源可行但优先级未选中 | consecutive skips | 分离调度策略跳过 |

KAS 的 active-set selection 因此包含两层语义：

```text
hard feasibility gates decide whether a request can be admitted
intensity-scaled attained-service and tie-breakers decide which feasible requests are admitted first
```

实验报告以下硬指标来支撑该语义：

```text
decode_swap_budget_per_iter
swap_bytes_per_iter
resident_admission_ratio
iteration_stall_time
infeasible_gpu_append_rounds
infeasible_gpu_swap_rounds
infeasible_swap_budget_rounds
policy_skipped_rounds
```

这些指标让 KAS 与 pure LAS / MLFQ 形成清晰区分：pure LAS 只定义服务顺序，KAS 同时定义 per-iteration memory feasibility、swap feasibility 和资源不可行原因。

### 同级 tie-breaker

同一个 attained-service queue 内使用固定 tie-breaker，便于实现和消融：

1. `starved` 请求优先：`consecutive_skips >= skip_threshold`。
2. KV resident 请求优先：避免把 iteration 卡在 swap-in 上；当 `decode_utility_intensity` 很低且没有 hard KV/swap pressure 时，该偏好弱化为同级 tie-breaker。
3. waiting time 更长者优先。
4. request id 更小者优先，保证确定性。

跨 attained-service level 的排序使用一个可实现的 effective level：

```text
effective_level(r, t) =
  decode_utility_intensity(t) * attained_level(r)
  - handoff_debt(r, t)
```

`handoff_debt` 是可选诊断项，用于刻画新完成 prefill 但尚未获得 first decode 的请求。核心算法首先使用 output-tail eligibility 决定是否启用 KAS：短输出 workload 使用 FCFS-compatible decode，长输出 workload 使用 full KAS，中间区域再由 `decode_utility_intensity` 连续调节。这样，BPS 的 TTFT 收益不会被短输出场景下的 decode-side 局部重排抵消。

### Bridge Completion Drain

当 bridge / first-token pressure 高而 hard KV/swap pressure 尚未触发时，KAS 使用 bridge completion drain 作为 first-token-limited regime 的 decode 侧执行策略。它不是开启 aggressive LAS，而是在硬可行性约束内优先选择能够释放 bridge 阻塞和 GPU KV footprint 的请求：

1. starved 请求仍保留 bounded-progress tie-break priority。
2. 尚未执行 first decode 的请求优先，降低 context-finished-but-unaccepted 到 first-token 的等待。
3. KV resident 请求优先，避免把一次 completion-oriented iteration 变成 swap stall。
4. 剩余输出较短的请求优先，尽快完成并释放 KV blocks。
5. 剩余输出相近时，当前占用 KV blocks 更多的请求优先，以提高单位 decode step 的 KV release。

Bridge completion drain 的机制信号包括 `bridge_completion_drain_active`、被选中请求的 remaining output、被选中请求的 allocated blocks、context-side `protected_blocked` 和 decode-side unaccepted queue。该策略让 first-token owner 与 decode 侧动作保持一致：decode 不只优化本地 TPOT 排序，而是通过完成近尾部 resident 请求释放 KV 空间，使 BPS 保护的请求能够被 bridge 接收。

一个请求连续被跳过超过 `skip_threshold` 后获得 `starved` 标记。starved 请求不会被提升到比 `Q0` 更高的队列，但在本队列内优先，并且 scheduler 在可行时优先 admission。

这里“可行时”按冲突仲裁规则解释：starved 标记不突破 `gpu_block_budget_ok` 或 `swap_budget_ok`。实验同时报告 `policy_skipped` 和 `infeasible_rounds`；前者表示策略层面绕过，后者表示资源不可行。

### Eviction 规则

Eviction 作为保守兜底策略，完整 cold-state eviction 属于相邻 KV management 层。策略定义如下：

1. 只有当 free GPU blocks 不足以接纳高优先级请求时才触发 eviction。
2. 优先 eviction 低优先级队列中的 non-resident-imminent 请求。
3. 同一队列内优先 eviction `generated_tokens` 更多、waiting urgency 更低的请求。
4. 已经 starved 的请求不被 eviction，除非系统无法继续执行。

KAS 复用 serving engine 已有 swap-out 机制，并聚焦 swap-aware admission；proactive prefetch 属于可组合扩展。

### 伪代码

```text
KAS(queues, kv_state, decode_budget):
  B = []
  swap_used = 0
  decode_pressure = estimate_decode_pressure(kv_state, queues)
  avg_target_output = average target output tokens of ready requests

  if avg_target_output <= short_output_threshold and not hard_pressure(kv_state):
    return FCFS-compatible decode batch subject to hard feasibility gates

  if avg_target_output > long_output_threshold:
    intensity = 1.0
  else:
    intensity = decode_budget.decode_utility_intensity

  if bridge_completion_drain(decode_budget, kv_state, queues):
    ordered_ready = sort ready requests by (
      starved first,
      first-decode-step first,
      resident first,
      remaining_output <= completion_threshold first,
      smaller remaining_output,
      larger allocated KV blocks,
      waiting age,
      request id
    )
  else:
    ordered_ready = sort ready requests by (
      starved first,
      intensity * attained_level - optional_handoff_debt,
      resident_preference if intensity is high or hard pressure exists,
      waiting age,
      request id
    )

  for r in ordered_ready:
      if starved(r):
        mark high tie-break priority

      reason = hard_feasibility_check(B, r, swap_used, decode_budget)
      if reason == ok:
        B.add(r)
        if not kv_resident(r):
          swap_used += kv_size(r)
      else:
        record_infeasible(r, reason)

      if B reaches decode batch limit:
        break

  execute one decode step for requests in B

  for r in B:
    generated_tokens(r) += 1
    consecutive_skips(r) = 0
    move r to queue_by_generated_tokens(r)

  for r not in B but ready:
    if r was infeasible:
      infeasible_rounds(r) += 1
    else:
      consecutive_skips(r) += 1

  if gpu_blocks are insufficient:
    evict from lowest eligible queues

  return B
```

### 设计不变量

KAS 维护七个不变量：

1. **Iteration feasibility invariant**：每个 decode iteration 的 active batch 同时满足 batch size、token budget、GPU block budget 和 swap budget。
2. **Hard-constraint accounting invariant**：被 KV block、append block 或 swap budget 排除的请求计入 `infeasible_rounds`，不混入 policy skip。
3. **Intensity-controlled ordering invariant**：在没有 starvation 标记和 KV 不可行的情况下，排序按 `decode_utility_intensity * attained_level` 调节；intensity 越高越接近 LAS，intensity 越低越接近 ready-time order。
4. **Resident preference invariant**：同一 effective attained-service level 内，KV resident 请求优先于需要 swap-in 的请求；hard KV/swap pressure 出现时 resident preference 不被弱化。
5. **Regime-compatibility invariant**：first-token-limited regime 可以降低 KAS utility intensity，但不能绕过 hard feasibility gates；decode-heavy 或 KV/swap-limited regime 恢复强 KAS。
6. **Bridge-drain compatibility invariant**：bridge completion drain 只在 bridge/first-token pressure 高且 hard KV/swap pressure 未触发时启用；它优先 first-decode、resident、近完成和高 KV-release 请求，但不突破 batch、GPU block 或 swap budget。
7. **Skip-bounded fairness invariant**：一个 ready request 连续被跳过超过 `skip_threshold` 后获得 starved tie-break priority；资源可行时，它不会继续被同级非 starved 请求绕过。

这些不变量把 KAS 和普通 MLFQ 区分开：它在 unknown output length、KV residency、per-iteration feasibility、bridge pressure release 和 PBC regime intensity 之间做在线折中。

### 复杂度与边界

令 active/ready decode 请求数为 `N`，attained-service queue 数为 `Q`，每轮最大 decode batch size 为 `D_max`。

每个队列保持 FIFO 加固定 tie-breaker 时，调度器每轮扫描直到填满 batch：

```text
time complexity: O(min(N, scan_limit))
space complexity: O(N + Q)
```

其中 `scan_limit` 可以设置为 `c * D_max`，例如 `2x` 到 `4x` 的最大 batch size，以避免在超高并发时每轮扫描全部请求。未扫描到的请求会累积 `consecutive_skips`，之后通过 starved tie-breaker 得到补偿。

每轮完整扫描所有队列时复杂度是 `O(N)`；实验报告 scheduler CPU overhead。

### Fairness Bound

KAS 使用 skip-bounded fairness。它偏向低 attained service 请求以改善短请求 slowdown，同时提供可实验验证的 skip bound：

```text
consecutive_skips(r) <= skip_threshold + infeasible_rounds(r)
```

其中 `infeasible_rounds(r)` 表示因为 KV block 不足、swap budget 不足或 batch token budget 不足而无法 admission 的轮数。

这个 bound 的含义是：长期 ready 且资源可行的请求不会被无限期跳过。实验报告：

1. long-output slowdown。
2. maximum consecutive skips。
3. starved admission ratio。
4. resident-first 带来的 swap 次数变化。

Fairness analysis 是 KAS 主实验的一部分，用于同时呈现短请求收益和长输出 slowdown。

### 实现映射

KAS 可以直接在 DistServe 的 `DecodingStageFCFSScheduler` 上演进：

1. 将 `waiting_queue` 从单个 list 改为多个 attained-service queues。
2. `unaccepted_queue` 中新迁移来的请求进入 `Q0`。
3. `batch_queues` 仍可复用，填充策略从 FCFS 改成 queue-level scan。
4. 使用 DistServe 现有 block manager 检查 GPU/CPU block availability。
5. 实现 resident-first 和 swap-budget admission。
6. 每个 request 增加少量元数据：`generated_tokens`、`consecutive_skips`、`attained_level`。

### 实验设计

KAS 单独验证以下问题：

1. 相对 DistServe FCFS 是否降低 TPOT p90/p99。
2. 相对 round-robin decode 是否更能照顾短输出请求。
3. 相对纯 LAS、不考虑 KV residency 的策略，是否减少 swap 次数和 iteration stall。
4. 当 output length variance 增大时，收益是否更明显。
5. 长输出请求的 slowdown 是否受 `skip_threshold` 控制。
6. 在 prompt-skew / first-token-limited regime 下，降低 `decode_utility_intensity` 是否减少 TTFT tail transfer。
7. scheduler overhead 是否随 active requests 线性增长，并且在真实 batch size 下可忽略。

### 可验证主张

KAS 的核心主张是：

> 在输出长度高度可变、短生成和长生成混合的 workload 下，intensity-controlled KV-constrained least-attained-service scheduling 可以降低 TPOT tail latency 和短请求 slowdown；同时通过 starvation counter、resident-first admission、swap-budget constraint、bridge completion drain 和 PBC regime intensity 控制公平性、swap 开销、KV footprint 释放与 TTFT tradeoff。

### 方法范围

KAS 聚焦 decode active-set shaping 与 KV/swap-aware admission：

- proactive KV prefetch 属于可组合扩展。
- topology-aware KV routing 属于 cluster-level routing 层。
- 平均延迟、tail latency 和长输出 slowdown 作为 tradeoff 一起报告。
- `decode_utility_intensity` 作为机制指标报告，用于解释 full PhaseServe 在 TTFT 与 TPOT 之间的折中。
- KV cache architecture 由底层 serving engine 或 KV-centric system 提供，KAS 使用其可观测状态做 admission。

对于长输出请求，attained-service scheduling 可能牺牲一部分平均完成时间或长请求公平性。方法说明同时报告 fairness 和 starvation bound。

## 核心控制器：PBC：Regime-Aware Pressure-Budget Controller

PBC 是最终方法中作为 Algorithm 1 呈现的核心算法。它负责把 KAS 观测到的 decode-side pressure 转化为 BPS 和 KAS 都能消费的 admission budget、safety margin 和 utility intensity，形成闭环。

PBC 是一个 pressure-to-budget-regime controller：prefill 是否继续积极 dispatch、decode active set 是否允许昂贵 swap-in、KAS 是否使用 aggressive attained-service priority，都受到当前 first-token/queue/KV/swap pressure 的预算约束和 regime 仲裁。

### 问题

prefill 调度只优化自身吞吐时，会很快完成大量 context computation，并把请求推入 decode 阶段；当 decode 阶段已经拥塞，这些请求会堆积在 bridge / unaccepted queue 中。

结果是：

1. prefill 端吞吐提高，但用户感知的 TTFT-to-first-decode 仍然变差。
2. decode queue 变长，TPOT tail latency 上升。
3. 已经生成的 KV state 占用更多内存，增加 swap pressure。

### 算法输入

PBC 使用以下低成本信号，并将其归一化为 pressure vector：

1. `active_decode_blocks`
2. `waiting_decode_blocks`
3. `bridge_queue_length`
4. `first_decode_wait` 或 context-finished-but-not-decoded age
5. `swap_in_queue_length`
6. `decode_queue_wait_p95`，可选；实现可用 queue length 近似。
7. `free_gpu_blocks`
8. `prefill_waiting_age`

### 机制

PBC 分四步运行：pressure normalization、regime classification、monotonic budget/intensity mapping、hysteresis smoothing。

**第一步：pressure normalization。**

PBC 先将原始 queue length、block 数和 swap bytes 归一化为 `[0, 1]` 压力分量：

```text
p_bridge = min(bridge_queue_length / B_target, 1)
p_first  = min(first_decode_wait / F_target, 1)
p_decode = min(waiting_decode_blocks / D_target, 1)
p_kv     = min((active_decode_blocks + waiting_decode_blocks) / G_blocks, 1)
p_swap   = min(swap_in_bytes_per_sec / S_target, 1)
p_age    = min(oldest_prefill_wait / tau_prefill, 1)
```

其中，`B_target`、`F_target`、`D_target`、`S_target` 由 SLO 或硬件容量决定：

1. `B_target`：超过该 bridge queue 后，TTFT-to-first-decode 开始明显恶化。
2. `F_target`：context 完成后到 first decode 的可接受等待阈值。
3. `D_target`：decode waiting blocks 的目标上限。
4. `G_blocks`：GPU KV block capacity。
5. `S_target`：每秒可承受 swap 带宽或每 iteration 可承受 swap bytes。
6. `tau_prefill`：最长可接受 prefill queue wait。

**第二步：regime classification。**

PBC 用 typed pressure signature 判断当前 bottleneck owner：

```text
hard_pressure = max(p_kv, p_swap)
first_token_pressure = max(p_first, p_bridge)
decode_tail_pressure = typed_effective_decode_pressure(p_decode, p_kv, p_swap)

if hard_pressure >= rho_hard:
  regime = KV_SWAP_LIMITED
elif first_token_pressure >= rho_high and decode_tail_pressure >= rho_high:
  regime = resolve_first_decode_conflict(
    default = FIRST_TOKEN_LIMITED,
    hard_pressure = hard_pressure,
    output_tail_state = output_tail_eligibility
  )
elif first_token_pressure >= rho_high and decode_tail_pressure < rho_high:
  regime = FIRST_TOKEN_LIMITED
elif decode_tail_pressure >= rho_high:
  regime = DECODE_HEAVY
else:
  regime = MIXED_SLO
```

当 first-token pressure 和 decode-tail pressure 同时进入高压区间且 hard KV/swap pressure 未触发时，默认 conflict owner 是 `FIRST_TOKEN_LIMITED`。原因是 bridge / first-token pressure 同时代表 admission path 阻塞：若 decode 侧此时无条件进入 aggressive attained-service 排序，可能把 BPS 已保护的请求继续卡在 first decode 之前。默认 owner 选择 first-token-limited 后，KAS 仍可通过 bridge completion drain 执行 resident、近完成和高 KV-release 请求，从而降低 KV 占用并改善一部分 TPOT tail。

`regime` 不替代 budget；它决定 phase-local utility 的强度和 conflict owner。这样 PBC 可以在 prompt-skew workload 中让 BPS 承担 TTFT owner，在 decode-heavy workload 中让 KAS 承担 TPOT owner，在 KV/swap pressure 中让 hard feasibility 成为第一目标，在 first/decode 冲突中让 decode 侧动作服务于被选中的 pressure path。

**第三步：monotonic budget and intensity mapping。**

PBC 将归一化压力映射为预算和 utility intensity。映射保持单调：任何 downstream hard pressure 上升时，可能继续增加对应 pressure 的预算不变宽；first-token pressure 上升且无 hard pressure 时，KAS 的 local utility intensity 不增大。

PhaseServe 采用 component-wise mapping 控制不同预算：

```text
rho_down = max(p_bridge, p_first, p_decode, p_kv, p_swap)
rho_prefill = aggregate(p_bridge, p_first, p_decode)
rho_memory  = aggregate(p_kv, p_swap)
rho_swap    = p_swap
rho_scan    = aggregate(p_kv, p_swap)
rho_hard    = aggregate(p_kv, p_swap)

c_prefill_tok_raw =
  c_prefill_min + (1 - rho_prefill) * (c_prefill_max - c_prefill_min)

m_prefill_blk_raw =
  m_prefill_min + rho_memory * (m_prefill_max - m_prefill_min)

s_decode_swap_raw =
  s_swap_min + (1 - rho_swap) * (s_swap_max - s_swap_min)

l_decode_scan_raw =
  l_scan_min + (1 - rho_scan) * (l_scan_max - l_scan_min)

i_decode_util_raw =
  regime_intensity(regime, rho_hard, first_token_pressure, decode_tail_pressure)
```

这里 `rho_down` 仍用于 mode selection、pressure overshoot 和 backpressure 状态解释，但不再直接控制每个 budget knob。component-wise mapping 避免把不同 pressure 混成一个粗粒度信号。例如，decode queue 高主要收缩 prefill token injection；KV/swap 高主要增加 block margin、收紧 scan/swap admission。

`aggregate(...)` 的默认实现可以使用 bottleneck-dominant `max`：在 phase-disaggregated serving 中，只要 bridge queue、decode queue、KV blocks 或 swap 任一链路成为瓶颈，继续扩大相关动作空间都会把压力推向下游 decode pool。因此默认策略由最紧的相关压力分量决定预算。

Aggregation 是 PBC 的可配置设计维度，用于覆盖不同 pressure 形态：

| Aggregation | 适用条件 | 预期优势 | 适用边界 | 实验用途 |
|---|---|---|---|---|
| `max(p_i)` | 单瓶颈主导；decode/KV/swap 共享下游资源池 | 对单点过载敏感；默认策略 | 多压力源温和叠加时可能过度保守 | 主结果和 bottleneck-dominant workload |
| `sum(w_i * p_i)` | 多压力源同时中等偏高，但无单点爆表 | 更平滑，可能保持更高吞吐 | 权重敏感性验证 | sensitivity / robustness |
| `lexicographic(p_kv, p_swap, ...)` | memory 或 swap 是硬瓶颈 | 优先避免 OOM / stall | 可能牺牲 TTFT 或 prefill utilization | memory-pressure ablation |

主配置采用 bottleneck-dominant aggregation；weighted 和 lexicographic aggregation 用于 sensitivity / robustness 分析。

`regime_intensity(...)` 的默认规则是：

```text
if regime == KV_SWAP_LIMITED:
  i_decode_util_raw = 1.0
elif regime == DECODE_HEAVY:
  i_decode_util_raw = high_intensity
elif regime == FIRST_TOKEN_LIMITED:
  i_decode_util_raw = low_intensity * (1 - bridge_discount * first_token_pressure)
else:
  i_decode_util_raw = medium_intensity
```

直觉是：

1. `rho_prefill` 高时，prefill token budget 下降，减少新的 decode arrivals。
2. `rho_memory` 高时，prefill block margin 上升，减少新的 KV handoff footprint。
3. `rho_swap` 高时，KAS 每轮允许 swap-in 的预算下降，避免 decode iteration 被 swap 拖慢。
4. `rho_scan` 高时，decode scan limit 变保守，优先填充 resident / cheap active set。
5. `i_decode_util` 在 first-token-limited regime 中下降，避免 aggressive KAS 把 TTFT 收益转移到 first decode wait；在 decode-heavy 或 KV/swap-limited regime 中恢复。
6. `p_age` 高时触发 progress override，避免 prefill starvation。

**第四步：hysteresis smoothing。**

PBC 使用平滑和双阈值处理 raw budget，降低预算抖动：

```text
b_smooth(t) = lambda * b_smooth(t-1) + (1 - lambda) * b_raw(t)

if rho_down >= rho_high:
  mode = BACKPRESSURE
elif rho_down <= rho_low:
  mode = OPEN
else:
  mode = previous_mode or BALANCED
```

其中 `rho_high > rho_low`。这给出一个工程上可验证的稳定性论证：只要 pressure 在 `[rho_low, rho_high]` 附近小幅波动，PBC 不会每轮改变 mode；预算变化幅度被 `lambda` 限制：

```text
|b_smooth(t) - b_smooth(t-1)| <= (1 - lambda) * |b_raw(t) - b_smooth(t-1)|
```

由此可以定义三个可实验验证的 stability metrics：

```text
mode_switch_rate = #mode_changes / #scheduler_rounds
regime_switch_rate = #regime_changes / #scheduler_rounds
budget_variance  = Var(c_prefill_tok, m_prefill_blk, s_decode_swap)
intensity_variance = Var(i_decode_util)
pressure_overshoot = max(0, rho_down - rho_high)
```

PBC 提供 bounded oscillation 的在线控制目标。实验报告 `mode_switch_rate`、`regime_switch_rate`、`pressure_overshoot`、budget variance 和 intensity variance，用于呈现预算控制是否稳定。

PBC 输出一个结构化 `AdmissionBudget`：

```text
AdmissionBudget:
  mode
  rho_down
  rho_prefill
  rho_memory
  rho_swap
  rho_scan
  prefill_token_budget
  prefill_block_margin
  prefer_small_kv_footprint
  decode_swap_budget_per_iter
  decode_scan_limit
  decode_utility_intensity
  regime
  conflict_owner
  bridge_completion_drain
  allow_protected_oldest
```

这样核心机制是把可观测压力稳定地转成两个阶段共享的预算接口。

### 参数选择原则

PBC 参数选择遵循可解释、可复现实验规则：

1. 容量类参数来自系统配置，例如 GPU block capacity、max prefill tokens、max decode batch size。
2. SLO 类参数来自服务目标，例如 TTFT SLO、TPOT SLO、可接受 bridge queue wait。
3. 带宽类参数来自微基准，例如 CPU/GPU swap bandwidth、一次 decode iteration 可隐藏的 swap bytes。
4. `rho_low` 和 `rho_high` 使用固定间隔，例如 `0.55/0.75`，并做 sensitivity sweep。
5. `lambda` 使用少量离散值，例如 `0.6/0.8/0.9`，报告 mode switch rate 和 tail latency 的敏感性。

参数敏感性覆盖不同 load、memory pressure 或模型设置，用于展示 pressure-budget mapping 的鲁棒性。

### 伪代码

```text
PBC(context_state, decode_state):
  p = normalize_pressure(context_state, decode_state)
  rho_down = max(p.bridge, p.first, p.decode, p.kv, p.swap)
  rho_prefill = aggregate(p.bridge, p.first, p.decode)
  rho_memory = aggregate(p.kv, p.swap)
  rho_swap = p.swap
  rho_scan = aggregate(p.kv, p.swap)
  hard_pressure = max(p.kv, p.swap)
  first_token_pressure = max(p.first, p.bridge)
  decode_tail_pressure = p.decode

  regime, conflict_owner = classify_regime(
    first_token_pressure,
    decode_tail_pressure,
    hard_pressure,
    output_tail_eligibility
  )

  raw_budget.prefill_token_budget =
    map_decreasing(rho_prefill, min_prefill_budget, max_prefill_budget)
  raw_budget.prefill_block_margin =
    map_increasing(rho_memory, low_safety_margin, high_safety_margin)
  raw_budget.decode_swap_budget_per_iter =
    map_decreasing(rho_swap, min_swap_budget, max_swap_budget)
  raw_budget.decode_scan_limit =
    map_decreasing(rho_scan, conservative_scan_limit, normal_scan_limit)
  raw_budget.decode_utility_intensity =
    map_regime_intensity(regime, first_token_pressure, decode_tail_pressure, hard_pressure)

  if rho_down >= rho_high:
    mode = BACKPRESSURE
  else if rho_down <= rho_low:
    mode = OPEN
  else:
    mode = previous_mode or BALANCED

  budget = smooth(previous_budget, raw_budget, lambda)
  budget.mode = mode
  budget.prefer_small_kv_footprint = (mode == BACKPRESSURE or rho_memory >= rho_high)
  budget.rho_prefill = rho_prefill
  budget.rho_memory = rho_memory
  budget.rho_swap = rho_swap
  budget.rho_scan = rho_scan
  budget.decode_utility_intensity =
    smooth_intensity(previous_budget.decode_utility_intensity,
                     raw_budget.decode_utility_intensity,
                     lambda)
  budget.regime = regime
  budget.conflict_owner = conflict_owner
  budget.bridge_completion_drain =
    (conflict_owner == FIRST_TOKEN_LIMITED
     and max(p.first, p.bridge) >= rho_high
     and hard_pressure < rho_hard)

  if p.age >= 1:
    allow_protected_oldest = true
  budget.allow_protected_oldest = allow_protected_oldest

  return budget
```

BPS 读取 PBC 生成的 `AdmissionBudget`，KAS 也读取同一个预算对象。这样实现上保持模块边界清楚，方法说明中也更容易解释。

### 设计不变量

PBC 维护八个不变量：

1. **Budget monotonicity invariant**：downstream pressure 越高，prefill token budget 不增大，prefill block margin 不减小，decode swap budget 不放宽。
2. **Bounded injection invariant**：当 `rho_down >= rho_high` 时，BPS 不以最大 token budget dispatch 大 KV footprint batch。
3. **Typed dependency invariant**：`bridge/first/decode` pressure 主要控制 prefill token injection，`kv/swap` pressure 主要控制 block margin、decode scan 和 swap admission。实验呈现对应 budget 与对应 pressure 的相关性。
4. **Progress invariant**：即使 decode pressure 高，protected oldest request 仍然可以在 bounded waiting 后被允许通过，避免 prefill starvation；该路径遵守物理可行性。
5. **Hysteresis invariant**：`rho_high` 和 `rho_low` 分离，并对输出预算做平滑，避免 admission budget 在临界压力附近频繁抖动。
6. **Surrogate accounting invariant**：PBC 每轮记录 `Phi(t)`、`I_prefill(t)`、`I_decode_swap(t)` 和 `GoodputCapacity(b)`，用于解释 pressure drift 与 budget movement。
7. **Regime ownership invariant**：first-token-limited regime 中 BPS 是 TTFT owner，decode-heavy regime 中 KAS 是 TPOT owner，KV/swap-limited regime 中 hard feasibility 是 owner；当 first-token 与 decode pressure 同时高而 hard pressure 未触发时，默认 conflict owner 为 first-token path，KAS 通过 bridge completion drain 服务该 owner；实验报告 regime、conflict owner 与对应机制信号。
8. **Observable stability invariant**：实验报告 mode switch rate、budget variance、regime switch rate 和 pressure overshoot。

### 可验证主张

PBC 的核心主张是：

> 仅做局部 prefill 或 decode scheduling 仍然可能造成阶段间压力转移；regime-aware pressure-budget control 可以减少 bridge queue 堆积、decode KV pressure 和 swap pressure，并通过正确选择 bottleneck owner 提升端到端 SLO goodput。

### 方法范围

PBC 聚焦 local pressure-budget coordination：

- cluster-wide load balancing 和 topology-aware routing 属于更高层控制平面。
- DistServe 的全局资源规划负责静态阶段资源配置，PBC 负责运行时预算控制。

它定位为 local pressure-budget coordination，与大规模控制平面互补。

## 方法总览

PhaseServe 的方法论由 **3 个正文算法** 构成：

### Algorithm 1: PBC

面向阶段间压力传播的 regime-aware pressure-budget controller。

目标：

- 将 first-token、decode queue、KV block、bridge queue 和 swap pressure 转成结构化 admission budget、regime 和 decode utility intensity。
- 防止 prefill 把 decode 推入过载。
- 控制 KV block pressure 和 swap pressure。
- 在 TTFT、TPOT 和 KV/swap safety 之间选择当前瓶颈 owner。
- 提升端到端 SLO goodput。

### Algorithm 2: BPS

面向已知 prompt length 的 budgeted cost-compatible prefill shaping。

目标：

- 降低 TTFT tail latency。
- 减少 prompt length skew 对 batch efficiency 的影响。
- 通过 protected oldest request 控制长 prompt starvation。
- 在 PBC budget 宽松时保持较高 prefill utilization。
- 在 PBC budget 收紧时主动降低 KV handoff 压力。

### Algorithm 3: KAS

面向未知 output length 的 intensity-controlled KV-constrained least-attained-service scheduling。

目标：

- 降低 TPOT tail latency。
- 改善短输出请求的排队体验。
- 通过 `consecutive_skips`、resident-first admission、swap budget、bridge completion drain 和 PBC utility intensity 控制 starvation、swap overhead、KV footprint 释放与 TTFT tradeoff。

这三个算法共同构成一个完整的系统方法。方法说明把 PBC 放在最前面呈现，因为它给出了统一的 pressure-to-budget-regime 接口；BPS 和 KAS 是该接口下的两个 phase-specialized execution policies。

最终方法可以概括为：

```text
PhaseServe regime-aware pressure-budgeted phase scheduling
  = PBC: regime-aware pressure-budget controller
  + BPS: budgeted prefill shaping
  + KAS: intensity-controlled KV-constrained attained-service scheduling
```

## 方法贡献

PhaseServe 的方法贡献包括：

1. **问题发现**：我们发现，在 prefill-decode disaggregated LLM serving 中，即使资源已经按阶段隔离，阶段内部的信息不匹配和阶段间 pressure propagation 仍然会导致严重的 tail latency 和 SLO goodput 损失。

2. **方法设计**：我们提出 regime-aware pressure-budgeted phase scheduling，将 first-token/decode-side queue/KV/swap pressure 转化为 admission budget、safety margin 和 utility intensity，并在该 budget 下将 prefill 建模为 known-size budgeted shaping problem，将 decode 建模为 intensity-controlled unknown-size KV-constrained attained-service scheduling problem。

3. **系统实现**：我们在 DistServe 上实现 PhaseServe，替换其 FCFS context scheduler 和 FCFS decode scheduler，并复用现有 block manager 完成 budget generation、memory-aware admission、swap-aware scheduling 和 pressure feedback。

4. **实验验证**：我们在真实模型、真实 GPU 和 trace-driven workload 上评估 PhaseServe，展示其在 workload-specific bottleneck metrics、SLO goodput、fairness 和 overhead 上的收益与 tradeoff，并通过消融实验证明三个算法的贡献。

## 方法边界

PhaseServe 的方法边界由四个方面定义。

### 1. 系统层次

PhaseServe 聚焦 scheduling、budgeted admission 和 pressure feedback。Global control、topology-aware routing、proactive KV prefetch 和完整 KV cache architecture 属于相邻系统层次。

本文主贡献限定为 phase-specialized scheduling、typed pressure-budget control 和 memory-aware admission。

### 2. 方法与实现映射

PhaseServe 的实现映射遵循三个原则：

- 每个方法机制对应 serving stack 中明确的 scheduler、budget controller 或 admission path。
- 相比 DistServe，新增机制集中在 runtime scheduling 和 budgeted admission。
- 每个机制都可通过 policy flag 或动态预算开关进行消融。

所有方法模块都映射到 DistServe 的 scheduler、block manager 或 engine event loop。

### 3. KV 相关方法边界

Mooncake 等系统已经把 KV cache 作为核心对象深入研究。PhaseServe 与这些 KV-centric systems 的关系是互补的：PhaseServe 把 KV block pressure 作为 scheduling 和 admission 的约束信号。

PhaseServe 的 KV 边界是：

- 使用已有 KV cache architecture。
- 提出 memory-aware scheduling。
- 使用现有 block manager 做 admission、swap preference 和 pressure control。

### 4. 可验证假设

PhaseServe 的假设具体到 workload、primary metric 和 mechanism signal。

验证假设包括：

- H1：prompt length skew 越高，BPS 相对 DistServe FCFS、shortest-prompt-first 和 pure bucket batching 对 TTFT p95/p99 的收益越明显。
- H2：在相同 prompt length 分布下，BPS 相比 shortest-prompt-first 降低 long-prompt starvation，并保持 protected blocked 可解释。
- H3：output length variance 越高，KAS 相对 DistServe FCFS、round-robin 和 pure LAS 对 TPOT p95/p99 与 short-request slowdown 的收益越明显。
- H4：在相同 output length 分布下，KV-aware KAS 相比 KV-unaware LAS 减少 swap bytes、iteration stall 和资源不可行轮次。
- H5：first-token、decode 或 KV/swap pressure 越接近 regime 阈值，PBC 相对 no-PBC、static budget 和 local-only BPS/KAS 对 SLO goodput、bridge queue、pressure drift、regime-local primary metric 和 swap pressure 的收益越明显。
- H6：在 homogeneous workload 或低负载下，PhaseServe 的收益下降，scheduler overhead 保持可忽略。

这些假设把 PhaseServe 的收益绑定到具体 pressure-transfer mechanism 和对应指标。

## 和 DistServe 代码的对应关系

基于当前 DistServe 代码，方法可以自然映射到以下位置：

### Context Stage

当前文件：

```text
distserve/context_stage_scheduler.py
```

当前机制：

- `ContextStageFCFSScheduler`
- `waiting_queue`
- `get_next_batch_and_pop`
- 按 FCFS 填 batch

PhaseServe 对应机制：

- `ContextStageCostCompatibleScheduler`
- 在 waiting queue 上实现 bounded candidate window
- 加入 prompt length bucket 和 bucket-local batch construction
- 加入 protected oldest request 和 `tau_prefill`
- 使用 `pad_waste`、`token_fill`、`block_risk` 选择候选 batch
- 通过 decode pressure budget 调节 `safety_margin`

### Decoding Stage

当前文件：

```text
distserve/decoding_stage_scheduler.py
```

当前机制：

- `DecodingStageFCFSScheduler`
- `unaccepted_queue`
- `waiting_queue`
- `swapped_queue`
- `batch_queues`
- FCFS admission 和简单 swap-in preference

PhaseServe 对应机制：

- `DecodingStageKVAwareLASScheduler`
- 将单一 `waiting_queue` 改为 generated-token 指数桶队列
- 基于 `generated_tokens` 更新 attained-service level
- 基于 `consecutive_skips` 标记 starved requests
- 基于 `decode_utility_intensity` 调节 attained-service / residency 排序强度
- 基于 KV residency 做同级 tie-break
- 基于 GPU block budget 和 swap budget 做 admission

KAS 的实现要求：

1. `decode_swap_budget_per_iter` 进入 admission feasibility。
2. `decode_utility_intensity` 进入 ready request 排序，并作为机制指标记录。
3. 每轮记录 `swap_in_bytes`、`swap_out_bytes`、`resident_admission_ratio`、`iteration_stall_time` 和 `eviction_count`。
4. GPU append block、swap-in block 和 swap budget infeasibility 被单独记录。
5. Memory-pressure workload 报告 KAS 相对 KV-unaware LAS 的 swap/stall 或 resident ratio 差异。

### Block Manager

当前文件：

```text
distserve/block_manager.py
```

当前能力：

- GPU/CPU block tables
- `swap_in`
- `swap_out`
- block usage tracking

PhaseServe 使用方式：

- 不重写为新 KV manager
- 将 block availability 和 swap pressure 暴露给 scheduler
- 在 decode admission 中作为约束条件和 tie-break 信号

### Engine / CLI

当前文件：

```text
distserve/engine.py
distserve/single_stage_engine.py
```

PhaseServe 对应机制：

- 增加 scheduler policy 参数
- 支持 `fcfs`、`cost-compatible-prefill`、`kv-aware-las-decode`、`phase` 等模式
- 增加轻量指标记录：queue length、wait time、generated tokens、consecutive skips、swap count、block pressure、`Phi(t)`、`I_prefill`、`I_decode_swap`、`decode_utility_intensity`、`regime`、scheduler overhead

## 评估设计

评估按 workload class 和 primary metric 组织：

| Workload class | Trace / generation rule | Load level | 压力来源 | Primary metric | Secondary metric | Expected mechanism signal | Diagnostic signal |
|---|---|---|---|---|---|---|---|
| Prompt-skew | 真实 trace 的 prompt 分布或 controlled Zipf/lognormal prompt lengths | medium-high | prompt length 高度偏斜，prefill queue head-of-line blocking | TTFT p95/p99、context queue time | prefill utilization、long-prompt wait | BPS 改善 dominant prompt buckets，feasible protected dispatch ratio 接近 1 | long-prompt wait、protected blocked、bucket tail |
| Decode-variance | 真实 trace 的 output 分布或 controlled heavy-tail output lengths | medium-high | output length 长尾，短/长输出混合 | TPOT p95/p99、short-request slowdown | long-output slowdown、skip count | KAS 改善短请求和 TPOT tail，同时报告 long-output slowdown | max skips、starved admission ratio |
| Decode-pressure | 提高 arrival rate 到 decode 接近饱和 | high | decode 阶段接近饱和，bridge queue 增长 | SLO goodput、bridge queue length | TTFT median、prefill token throughput | PBC+BPS 降低下游过载，展示 TTFT/TPOT tradeoff | bridge queue、pressure overshoot、budget ratio |
| Memory-pressure | 降低 GPU KV block budget 或提高并发长度 | medium-high | GPU KV block 紧张或 swap 频繁 | swap bytes、iteration stall、resident admission ratio | TPOT tail、eviction count | KAS 的 KV/swap 约束优于 KV-unaware LAS | swap-budget infeasible rounds、resident ratio |
| Homogeneous / low-load | prompt/output 同质，arrival rate 远低于饱和 | low | 无明显压力瓶颈 | overhead、no-regression latency | throughput | PhaseServe 收益下降，scheduler overhead 可忽略 | median latency、throughput no-regression |
| Swap-dominated overload | 故意让 swap 带宽成为硬瓶颈 | overload | swap 带宽成为主瓶颈 | goodput under SLO、swap stall time | rejection/timeout ratio | PhaseServe 呈现 overload 边界和 admission-control 需求 | timeout/rejection、swap stall |

这张表定义实验章节的组织方式：每类 workload 先声明 primary metric，再报告对应 mechanism signal。

### Claim-Baseline Contract

PhaseServe 的实验 claim 以组件为单位绑定 baseline、主指标和机制信号。每个 claim 同时报告端到端指标和内部机制指标，避免把单个 latency percentile 解释为全部贡献。

| Claim | Baseline family | Primary metric | Required mechanism signal | Diagnostic boundary |
|---|---|---|---|---|
| BPS improves known-size prefill shaping | DistServe FCFS、shortest-prompt-first、pure bucket batching | TTFT p90/p99、context queue time | selected token distribution、pad waste、protected dispatch ratio | long-prompt wait 与 protected blocked 同时报出 |
| KAS improves unknown-size decode scheduling | DistServe FCFS、round-robin、pure LAS、KV-unaware LAS | TPOT p90/p99、short-request slowdown | resident admission ratio、swap bytes、iteration stall、infeasible reason breakdown、KAS intensity | long-output slowdown 与 max skips 同时报出 |
| PBC reduces pressure propagation | no-PBC、static budget、local-only BPS/KAS | SLO goodput、bridge queue、pressure overshoot | `Phi(t)`、budget movement、`I_prefill`、`I_decode_swap`、`regime`、`decode_utility_intensity` | mode/regime switch rate、budget/intensity variance 同时报出 |
| Full PhaseServe improves regime-local end-to-end serving | DistServe FCFS、DistServe+BPS、DistServe+KAS、PBC-only | SLO goodput、regime-local TTFT 或 TPOT tail、per-GPU goodput | PBC regime、BPS/KAS 强度与对应机制信号同时出现 | 非瓶颈 percentile、overhead、fairness、memory pressure 同时报出 |

这个 contract 也定义消融解释方式：

```text
BPS contribution = full or PBC+BPS vs no-BPS variants on prompt-skew workloads
KAS contribution = full or PBC+KAS vs no-KAS variants on decode-variance / memory-pressure workloads
PBC contribution = full vs BPS+KAS with static budgets on decode-pressure workloads
```

在论文叙事中，BPS、KAS 和 PBC 不共享同一个“所有指标同时提升”的 claim。BPS 主要解释 prefill queue 与 TTFT，KAS 主要解释 TPOT、short-output slowdown 与 swap/stall，PBC 主要解释 pressure drift、bridge queue 和 SLO goodput。

实验矩阵覆盖：

1. **End-to-end comparison**：DistServe FCFS vs PhaseServe full。
2. **Component ablation**：只开 PBC、只开 BPS、只开 KAS、PBC+BPS、PBC+KAS、全部开启。
3. **Prompt length skew sensitivity**：控制输入长度分布偏斜程度。
4. **Output length variance sensitivity**：控制输出长度长尾程度。
5. **Load sweep**：从低负载到接近饱和。
6. **Memory pressure sweep**：改变 GPU KV block budget 或并发上限。
7. **Fairness analysis**：检查长请求是否被过度牺牲。
8. **Controller stability analysis**：PBC mode switch rate、regime switch rate、budget variance、pressure overshoot。
9. **Overhead analysis**：scheduler CPU overhead、额外 queue 操作成本、swap 次数变化。

这些实验共同覆盖端到端收益、机制归因、稳定性、公平性和调度开销。

## 方法说明要点

### 统一方法结构

PhaseServe 识别 prefill/decode 解耦之后的信息结构差异和压力传播路径，并将一个 regime-aware 压力预算控制器和两个预算执行策略映射到 LLM serving runtime：

- PBC: regime-aware pressure-budget control for pressure propagation across phases；
- BPS: budgeted cost-compatible shaping for known-size prefill；
- KAS: intensity-controlled KV-constrained attained-service scheduling for unknown-size decode。

实现使用轻量在线策略，但每个策略都有明确不变量：PBC 维护 budget monotonicity、bounded injection、typed dependency、progress、hysteresis、surrogate accounting、regime ownership 和 observable stability 八个不变量；BPS 维护 feasibility、pressure-coupled feasibility、oldest protection 和 no artificial waiting 四个不变量；KAS 维护 iteration feasibility、hard-constraint accounting、intensity-controlled ordering、resident preference、regime compatibility、bridge-drain compatibility 和 skip-bounded fairness 七个不变量。

### 可观测低成本信号

LLM serving 中 latency predictor 对模型、batch size、parallelism、KV residency 和 hardware state 高度敏感。PhaseServe 使用低成本、稳定可观测的信号，使方法更易部署和复现。

### 长请求公平性

KAS 使用 `consecutive_skips` 提供 skip-bounded fairness。实验报告长请求 tail latency、long-output slowdown、maximum consecutive skips 和 starved admission ratio。

### 与 DistServe 的关系

DistServe 的主要贡献是 prefill/decode disaggregation 和资源配置；PhaseServe 的贡献是 disaggregation 之后的 runtime pressure control。PhaseServe 可以被实现为 DistServe 的 scheduler/admission extension，因此二者是互补关系。

### 与 KV-centric systems 的关系

PhaseServe 使用现有 KV cache architecture，并把 KV block pressure 作为 scheduling 和 admission 的约束信号。KV-centric serving architecture 属于互补系统层次。

## 论文结构

论文围绕“运行时压力控制”展开。

1. **Introduction**
   - 说明 disaggregated serving 已经减少 inter-phase interference。
   - 指出 remaining bottleneck 是 intra-phase scheduling mismatch 和 inter-phase pressure propagation。
   - 给出 motivating example：FCFS 在 skewed prompt、variable output 和 decode pressure 下的局限。

2. **Background and Motivation**
   - 介绍 prefill/decode 特性。
   - 介绍 DistServe 的 phase disaggregation。
   - 展示 FCFS scheduler 的局限。

3. **Design Principles**
   - Prefill is known-size。
   - Decode is unknown-size。
   - Bridge pressure couples the phases。
   - Formal model、resource constraints、invariants。

4. **PhaseServe Design**
   - PBC：regime-aware pressure-budget controller。
   - BPS：budgeted cost-compatible prefill shaping。
   - KAS：intensity-controlled KV-constrained least-attained-service scheduling。

5. **Implementation**
   - DistServe 集成。
   - scheduler policy。
   - metrics。
   - overhead。

6. **Evaluation**
   - 端到端效果。
   - 消融。
   - sensitivity。
   - fairness。
   - overhead。

7. **Discussion**
   - 适用边界。
   - 和 KV-centric systems 的关系。
   - 多节点 routing 的扩展方向。

8. **Related Work**
   - Disaggregated LLM serving。
   - LLM serving schedulers。
   - KV cache management。
   - Online scheduling。

## 方法组成与研究范围

PhaseServe 的核心组成包括：

- phase-specialized scheduling 这个主线。
- prefill 利用 prompt length 已知这一点。
- decode 利用 generated tokens / attained service 这一点。
- TTFT、TPOT、SLO goodput 作为核心指标。

相邻方向作为 baseline、discussion 或扩展方向处理：

- global phase controller。
- topology-aware routing。
- proactive KV prefetch。
- cold-state eviction。
- 绝对 speedup 数字作为结果报告项。

PhaseServe 的验证要素包括：

- 更清晰的问题定义。
- 为什么 prefill 和 decode 是不同在线调度问题。
- 为什么 prompt length 和 generated tokens 是足够好的信号。
- 为什么 bridge pressure 是 phase-disaggregated serving 中不可忽略的第三类压力。
- PBC 的 pressure vector、budget vector、regime classifier、pressure-drift surrogate、monotonic mapping、hysteresis smoothing 和 bounded-pressure 规则。
- BPS 的 budgeted cost-compatible batch 选择规则和 bounded waiting 规则。
- KAS 的 intensity-controlled KV-constrained LAS 队列组织、resident-first tie-breaker、bridge completion drain、hard feasibility gate 和 skip-based fairness 规则。
- 每个机制的消融实验计划。
- fairness 和 overhead 的讨论。

## 命名

PhaseServe 的方法模块命名为：

- `PBC`: Regime-Aware Pressure-Budget Controller。
- `BPS`: Budgeted Prefill Shaping。
- `KAS`: Intensity-Controlled KV-Constrained Attained-Service Scheduling。

论文标题候选：

> PhaseServe: Pressure-Budgeted Phase Scheduling for Disaggregated LLM Serving

或者：

> PhaseServe: Pressure-Budget Control for Prefill-Decode Disaggregated LLM Serving

这两个标题都比“coordinated scheduling and KV management”更聚焦，也更容易体现本文的真正贡献。

## 方法定义

PhaseServe 的方法边界保持在 regime-aware pressure-budgeted phase scheduling。实现和实验按本文定义的 workload class、primary metric 和 mechanism signal 验证。

PhaseServe 的方法组成是：

```text
regime-aware pressure-budgeted phase scheduling
  = PBC: regime-aware pressure-budget controller
  + BPS: budgeted prefill shaping
  + KAS: intensity-controlled KV-constrained attained-service scheduling
```

PhaseServe 构成一个完整闭环：PBC 生成 typed budgets、regime 和 decode utility intensity，BPS 在 prefill 侧执行 budgeted known-size shaping，KAS 在 decode 侧执行 intensity-controlled KV-constrained attained-service scheduling。
