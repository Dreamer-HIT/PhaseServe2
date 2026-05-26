# PhaseServe 方法论设计文档

状态：实验前的方法论工作稿。

目标：面向计算机系统领域顶会，例如 OSDI、SOSP、NSDI、EuroSys、ASPLOS、ATC。

## 结论先行

现有初稿的方法论**有潜力，但还不足以支撑系统顶会投稿**。

最值得保留的核心判断是：

> 在 prefill 和 decode 已经被解耦之后，系统瓶颈不再只是两个阶段之间的资源干扰，而是两个阶段内部的调度目标和可观测信息结构不同。prefill 的主导工作量在执行前基本可知，而 decode 的总工作量只能在线暴露。因此，二者不应该继续使用相同的 FCFS 式调度策略。

这个 insight 是强的，值得作为论文主线。但当前初稿的问题是 claim 太宽，系统边界太大，方法论里混合了几个尚未充分实现和验证的方向：

1. 全局 phase controller 和 topology-aware routing。
2. 主动式 KV-state manager，包括 residency、prefetch、cold-state eviction。
3. 大规模实验结果和提升幅度，但这些目前还没有和真实实现、真实硬件、真实 workload 严格绑定。

如果目标是系统顶会，PhaseServe 应该被收窄成一个更精确、更可实现、更容易做消融的系统贡献：

> PhaseServe 是一个面向 prefill-decode 解耦式 LLM serving 的信息不对称调度系统。它在 DistServe 之上引入 phase-specialized local schedulers 和 memory-aware admission，而不是在尚未充分实现前声称构建了完整的新型全局控制平面。

换句话说，当前方法论的种子足够好，但论文需要从“我做了一个包罗万象的 serving 系统”改成“我识别并解决了 disaggregated LLM serving 中一个被低估的核心调度问题”。

## 推荐论文主张

不建议继续使用如下宽泛 claim：

> PhaseServe 是一个包含全局路由、utility-aware prefill scheduling、MLFQ decode scheduling 和 proactive KV management 的协调式 serving 系统。

建议改成如下更稳、更容易说服 reviewer 的 claim：

> PhaseServe 是一个 scheduler-first 的 prefill-decode disaggregated serving 扩展。它证明了，在完成 prefill/decode 资源解耦之后，剩余关键瓶颈来自两个阶段内部的信息不匹配；通过将调度策略与各阶段可观测信息相匹配，可以在不修改模型 kernel 的情况下改善 workload 的瓶颈指标，例如 TTFT queueing、TPOT tail、SLO goodput 或不同长度 bucket 的公平性。

注意：这个 claim 不要求所有指标同时改善。系统论文更可信的写法是定义各类 workload 的瓶颈指标，并显式报告 tradeoff。例如，decode-pressure workload 中 PhaseServe 的主要目标可以是降低 TPOT P99 和提高 SLO goodput；如果 TTFT median 轻微上升，只要幅度可控且 SLO attainment 更高，这仍然是合理结果。

这个 claim 更适合系统顶会，原因有三点：

1. 它和 DistServe 的关系清楚：DistServe 解决阶段解耦和资源配置，PhaseServe 解决解耦之后的阶段内调度。
2. 它能落到真实代码：当前 DistServe 的 context 和 decoding scheduler 都是 FCFS 式实现，替换点明确。
3. 它能做干净消融：prefill scheduler、decode scheduler、bridge admission 可以分别打开和关闭。

## 核心研究命题

Phase-disaggregated LLM serving 将 prefill 和 decode 拆分到不同资源池，以减少两个阶段之间的直接干扰。DistServe 和 Splitwise 已经证明这种方向是合理的。

但是，拆分之后并不意味着调度问题消失。相反，系统暴露出两个结构不同的局部在线调度问题：

- **Prefill 阶段**：prompt length 在执行前已知，prefill 计算量和 KV footprint 可以被粗略估计。
- **Decode 阶段**：最终输出长度未知，请求需要跨多个 decoding iteration 持续占用 KV cache 和 batch slot。

因此，一个好的 disaggregated serving runtime 不应该对两个阶段都使用同一种 FCFS-like 策略，而应该使用 information-matched scheduling：

- 对 prefill 使用 bounded-window cost-compatible batching。
- 对 decode 使用 KV-aware least-attained-service scheduling。
- 对两个阶段之间的迁移使用 memory-aware admission。

这个命题比当前初稿更窄，但更适合发表，因为它产生了明确、可证伪、可实现的系统假设。

## 和已有系统的定位

PhaseServe 的方法论需要清楚地区分于以下相关系统：

- **DistServe**：将 prefill 和 decode 解耦，并联合优化资源分配和并行策略，以满足 TTFT 与 TPOT SLO。它是 PhaseServe 的直接 baseline 和实现基座。
- **Splitwise**：同样强调 prompt computation 与 token generation 的分离，并关注不同阶段的硬件和资源配置。
- **Sarathi / Sarathi-Serve**：在 colocated serving 场景中通过 chunked prefill 和 piggybacked decode 改善 batch 效率，但它没有重点研究 phase disaggregation 之后的阶段内调度。
- **vLLM / PagedAttention**：重点是 KV cache 内存管理和 continuous batching，而不是 disaggregated architecture 下的 phase-specialized scheduling。
- **Mooncake**：将 KV cache 管理作为生产级 disaggregated LLM serving 的核心，包括过载行为和 early rejection。它提高了任何 KV-centric claim 的门槛。

已检查的主要参考：

- DistServe: https://arxiv.org/abs/2401.09670
- Splitwise: https://arxiv.org/abs/2311.18677
- Sarathi: https://arxiv.org/abs/2308.16369
- vLLM / PagedAttention: https://arxiv.org/abs/2309.06180
- Mooncake: https://arxiv.org/abs/2407.00079

## 系统抽象

建议在论文方法论中使用一个简洁抽象，而不是从一开始就描述复杂控制平面。

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

这个抽象足够支撑一篇系统论文，因为它不依赖脆弱的 learned latency predictor，也不要求完整重写 serving engine。

## 形式化问题建模

为了让方法论达到顶会论文的论证强度，PhaseServe 不应只描述为“两个启发式调度器”，而应被建模为两个具有不同信息结构的在线调度问题。

### Prefill Model

对每个请求 `r`，prefill 阶段在调度前可观测：

```text
arrival_time(r)
prompt_len(r)
kv_blocks(r) = ceil((prompt_len(r) + 1) / block_size)
```

prefill scheduler 在每一轮选择一个 batch `B`。`B` 必须满足：

```text
|B| <= C_req
sum(prompt_len(r) for r in B) <= C_tok
sum(kv_blocks(r) for r in B) <= C_blk
```

其中 `C_req` 是最大 batch request 数，`C_tok` 是 prefill token budget，`C_blk` 是当前可用于 prefill handoff 的 KV block budget。

prefill 的优化目标不是全局最优 makespan，而是在线降低 TTFT tail：

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

每个 decode iteration 选择一个 active batch `D_t`。`D_t` 必须满足：

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

关键建模点是：`L_out(r)` 不可知，因此 decode 不能做 shortest-remaining-time；但 `generated_tokens(r, t)` 是 attained service，可以作为在线调度的稳健信号。

### Paper-Level Hypothesis

PhaseServe 的核心假设应写成可证伪形式：

> 在 prefill-decode disaggregated serving 中，阶段间资源隔离之后的剩余瓶颈主要来自阶段内信息不匹配。将 prefill 建模为 known-size constrained batching、将 decode 建模为 unknown-size KV-constrained attained-service scheduling，可以在异构 workload 下改善 TTFT tail、TPOT tail 和 SLO goodput。

这个假设有明确失败条件：如果 workload 的 prompt length 和 output length 都高度同质，或者系统远低于饱和，PhaseServe 的收益应显著下降；如果调度开销或 swap 开销超过收益，则方法不成立。

## 方法一：PS-Prefill：Bounded-Window Cost-Compatible Batching

### 问题

DistServe 当前的 context-stage scheduler 是 FCFS。它按照到达顺序把请求加入 batch，直到触发 max batch size、max tokens per batch 或 GPU block budget 限制。

这种策略简单，但在 prompt length 高度偏斜时容易出现两个问题：

1. 长 prompt 阻塞短 prompt，导致 TTFT tail latency 上升。
2. batch 内 prompt 长度混杂，造成 prefill 阶段 padding、同步和资源利用效率下降。

### 设计原则

Prefill 可以被看作 known-size online batching problem。虽然准确 prefill latency 仍然受 kernel、并行策略和硬件状态影响，但 prompt length 在请求进入系统时已经可见，并且与 prefill 计算量和 KV allocation 强相关。

因此，prefill scheduler 不应该盲目 FCFS，也不应该只写成一个过于抽象的 utility optimizer。更适合系统论文和真实实现的形式是：

> 在一个有界候选窗口内，按照 prompt cost compatibility 构造 batch，同时用 oldest-request protection 提供 starvation bound。

这个设计比“泛化 utility-aware batching”更硬，因为它有明确输入、明确约束、明确 tie-breaker，并且可以直接和 FCFS、shortest-prompt-first、bucket batching 做对照实验。

### 算法输入

PS-Prefill 只使用 DistServe 中容易获得的运行时信号：

1. `prompt_len(r)`：请求输入长度。
2. `wait_time(r)`：请求进入 context waiting queue 后的等待时间。
3. `num_blocks(r)`：prefill 后需要的 KV block 数，可由 prompt length 和 block size 估计。
4. `max_batch_size`：context engine 支持的最大 batch request 数。
5. `max_tokens_per_batch`：context engine 支持的最大 prefill token 数。
6. `free_gpu_blocks`：当前可用 GPU block 数。
7. `decode_pressure`：来自 PS-Bridge 的轻量反馈；第一版实现可以先置为 0。

### 核心机制

PS-Prefill 每轮调度分四步。

**第一步：有界候选窗口。**

从 FCFS waiting queue 的队首取最多 `K` 个请求作为候选窗口 `C`。窗口大小 `K` 是实现参数，而不是时间窗口。这样可以避免为了等更好的 batch composition 而人为增加不确定等待。

窗口中的 oldest request 被标记为 protected request。protected request 不能被无限跳过。

**第二步：cost bucket。**

按照 prompt length 将候选请求划入粗粒度桶，例如：

```text
B0:   0 < len <= 256
B1: 256 < len <= 512
B2: 512 < len <= 1024
B3: 1024 < len <= 2048
B4: len > 2048
```

桶边界不需要固定为这些数字，后续实验可以基于模型最大长度和 workload 分布调整。但论文中应强调：bucket 只依赖 prompt length，不依赖 learned predictor。

**第三步：构造 cost-compatible batch。**

对每个非空 bucket，构造一个候选 batch。batch 必须满足：

```text
|B| <= max_batch_size
sum(prompt_len(r) for r in B) <= max_tokens_per_batch
sum(num_blocks(r) for r in B) <= free_gpu_blocks - safety_margin
```

如果 decode pressure 较高，`safety_margin` 增大；如果 decode pressure 较低，`safety_margin` 减小。

同一 bucket 内按 `(protected, wait_time, prompt_len)` 排序：

1. protected request 如果属于该 bucket，则必须优先尝试加入。
2. 其他请求优先选择等待时间更长者。
3. 在等待时间相近时优先选择 prompt length 更接近 bucket median 的请求，降低 padding waste。

**第四步：选择 batch。**

从所有 bucket 产生的候选 batch 中选择一个得分最高者。得分建议使用可测量项，而不是抽象权重堆叠：

```text
score(B) =
  token_fill(B)
  - alpha * pad_waste(B)
  - beta  * block_risk(B)
  + gamma * oldest_bonus(B)
```

其中：

```text
token_fill(B) = sum(prompt_len(r) for r in B) / max_tokens_per_batch
pad_waste(B) = (max_len(B) * |B| - sum(prompt_len(r) for r in B)) / max_tokens_per_batch
block_risk(B) = sum(num_blocks(r) for r in B) / max(free_gpu_blocks, 1)
oldest_bonus(B) = 1 if protected request in B else 0
```

如果 protected request 的等待时间超过 `tau_prefill`，则只在包含 protected request 的候选 batch 中选择；如果没有可行 batch，则单独 dispatch protected request。

### 伪代码

```text
PS-Prefill(waiting_queue):
  C = first K requests from waiting_queue
  p = oldest request in C
  buckets = group C by prompt length
  candidates = []

  for bucket in buckets:
    B = []
    for r in ordered(bucket):
      if feasible(B + r):
        B.add(r)
    if B is not empty:
      candidates.add(B)

  if wait_time(p) >= tau_prefill:
    candidates = {B in candidates | p in B}
    if candidates is empty:
      return {p}

  return argmax_B score(B)
```

### 设计不变量

PS-Prefill 在实现和论文中应明确维护三个不变量：

1. **Feasibility invariant**：任何被 dispatch 的 batch 都必须满足 request、token 和 KV block 三类资源约束。
2. **Oldest protection invariant**：当 oldest request 的等待时间超过 `tau_prefill` 时，下一次 dispatch 必须包含它；如果无法与其他请求组成可行 batch，则单独 dispatch。
3. **No artificial waiting invariant**：scheduler 不主动等待未来请求，只在当前 waiting queue 的前 `K` 个请求内重排。

第三个不变量很重要。它能避免 reviewer 质疑 PhaseServe 通过人为延迟请求来换取更好 batch composition。PS-Prefill 只重排已经到达的 bounded window。

### 复杂度与边界

令候选窗口大小为 `K`，bucket 数为 `G`，最大 batch size 为 `B_max`。PS-Prefill 每轮最多检查 `K` 个请求并构造至多 `G` 个候选 batch。

```text
time complexity: O(K log K + G * K)
space complexity: O(K + G)
```

如果实现中 bucket 内只按 waiting queue 顺序扫描，而不做完整排序，则复杂度可以降为：

```text
time complexity: O(K + G * K)
```

在 DistServe 中，`K` 应设置为小常数，例如 `2x` 到 `4x` 的 `max_batch_size`。这样 scheduler overhead 与模型 prefill 执行时间相比应可忽略。

### Starvation Bound

PS-Prefill 的 starvation bound 不需要给出强理论最优性，但要能给出工程上可验证的上界：

```text
wait_time(r) <= tau_prefill + one_dispatch_interval + prefill_exec_time(protected_batch)
```

含义是：一个请求一旦成为 protected oldest request 并超过 `tau_prefill`，下一次调度必须被选中。实际实验中应报告：

1. long-prompt p95/p99 TTFT。
2. long-prompt maximum observed queue wait。
3. 被 protected dispatch 触发的请求比例。

如果这些指标显示长请求 tail latency 爆炸，说明 PS-Prefill 的参数需要调整，不能只报告短请求收益。

### 实现映射

PS-Prefill 可以直接在 DistServe 的 `ContextStageFCFSScheduler.get_next_batch_and_pop` 上实现：

1. 保留原有 waiting queue 数据结构，避免重写 context engine。
2. 将原来的 FCFS append loop 替换为 candidate-window + bucket batch selection。
3. 使用 DistServe 已有的 `max_batch_size`、`max_tokens_per_batch`、block budget 检查。
4. 第一版不需要 profiler；`prompt_len` 就是 cost proxy。
5. `decode_pressure` 可以先不接入，等 PS-Bridge 实现后再作为 safety margin 的调节项。

### 后续实验设计

PS-Prefill 至少需要单独验证以下问题：

1. 相对 DistServe FCFS 是否降低 TTFT p90/p99。
2. 相对 shortest-prompt-first 是否更公平，长 prompt 是否不会 starvation。
3. 相对 pure bucket batching 是否在低负载下没有明显额外等待。
4. 当 prompt length skew 增大时，收益是否更明显。
5. scheduler CPU overhead 是否低于 prefill 执行时间的 1% 或一个可接受阈值。

### 可发表 claim

PS-Prefill 的核心 claim 应该是：

> 在 prompt length 分布偏斜且系统接近饱和时，bounded-window cost-compatible batching 可以降低 TTFT tail latency，同时通过 protected oldest request 保持长 prompt 的 bounded waiting。

### 暂时不要 claim

不要声称：

- 全局最优 prefill batching。
- 精确 latency prediction。
- 在 homogeneous prompt length workload 下也一定有显著收益。
- 算法一定优于所有 size-aware scheduling 变体。

## 方法二：PS-Decode：KV-Aware Least-Attained-Service Scheduling

### 问题

DistServe 当前的 decode scheduler 也是 FCFS-like。它接收从 context stage 迁移过来的请求，将其放入 waiting queue，并按顺序填充 decode batch；对于 swapped-out requests，只做简单的 swap-in preference。

Decode 和 prefill 的核心区别是：

1. 输出长度未知。
2. 长请求会跨很多 decode iterations 持续占用 batch slot 和 KV cache。
3. 短请求可能被长请求拖累，即使每个 decode iteration 本身很短。

因此，如果 decode 阶段继续使用 FCFS，会在输出长度高度可变时造成明显 tail latency 问题。

### 设计原则

Decode 应该被看作 unknown-size online scheduling problem。因为最终 job size 不可知，调度器不能直接做 shortest-job-first 或 shortest-remaining-processing-time。

可行的近似是使用 attained service：

> 已经生成 token 越少的请求，越可能是短请求，应该获得更高的前台优先级；已经获得大量服务的请求可以被降级，但需要 aging 机制防止 starvation。

但论文中不建议把主要贡献写成“我们用了 MLFQ”。更好的表述是：

> Decode 是 unknown-size iterative serving。PS-Decode 用 generated tokens 作为 attained service，近似 least-attained-service scheduling；同时把 KV residency 和 block budget 作为 admission 约束，避免调度器选择一个理论上紧急但当前激活代价过高的请求。

这比通用 MLFQ 更适合顶会论文，因为它把 scheduling 和 LLM serving 的 KV memory 约束绑定起来，但又不夸大成完整 KV cache architecture。

### 算法输入

PS-Decode 使用以下状态：

1. `arrival_time`
2. `last_ready_time`
3. `generated_tokens`
4. `attained_level`
5. `consecutive_skips`
6. `kv_resident`
7. `num_gpu_blocks`
8. `num_cpu_blocks`
9. `expected_new_blocks_per_step`
10. `slo_deadline`，可选；第一版可以只做无 SLO 的 attained-service scheduling。

### 队列组织

PS-Decode 维护多个 attained-service queues，而不是抽象 MLFQ：

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

请求刚进入 decode 时进入 `Q0`。每执行一个 decode iteration，`generated_tokens` 增加 1。如果它跨过当前队列边界，就移动到更低优先级队列。

### Admission 规则

每轮 decode iteration 之前，scheduler 从高优先级队列到低优先级队列扫描请求。一个请求能进入 active batch，必须同时满足：

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

第一版实现可以不做真正异步 prefetch，只做 swap-aware admission。这样 claim 更稳：

- 如果请求 KV 已在 GPU，则 admission 成本低。
- 如果请求 KV 在 CPU，只有当本轮 swap budget 足够时才 admission。
- 如果 GPU block 紧张，优先保留高优先级和 resident 请求。

### 同级 tie-breaker

同一个 attained-service queue 内，不建议再用复杂加权公式。使用固定 tie-breaker，便于实现和消融：

1. `starved` 请求优先：`consecutive_skips >= skip_threshold`。
2. KV resident 请求优先：避免把 iteration 卡在 swap-in 上。
3. waiting time 更长者优先。
4. request id 更小者优先，保证确定性。

如果一个请求连续被跳过超过 `skip_threshold`，它获得 `starved` 标记。starved 请求不会被提升到比 `Q0` 更高的队列，但在本队列内优先，并且 scheduler 必须在可行时优先 admission。

### Eviction 规则

不建议在论文主方法中 claim 完整 cold-state eviction。第一版可以定义一个保守 eviction 策略：

1. 只有当 free GPU blocks 不足以接纳高优先级请求时才触发 eviction。
2. 优先 eviction 低优先级队列中的 non-resident-imminent 请求。
3. 同一队列内优先 eviction `generated_tokens` 更多、waiting urgency 更低的请求。
4. 已经 starved 的请求不被 eviction，除非系统无法继续执行。

如果实现中 DistServe 已有 swap-out 机制，就复用它；如果没有实现异步 prefetch，则论文中只写 swap-aware admission，不写 proactive prefetch。

### 伪代码

```text
PS-Decode(queues):
  B = []
  swap_used = 0

  for level from Q0 to Qn:
    for r in ordered(level):
      if starved(r):
        mark high tie-break priority

      if feasible_batch(B, r) and feasible_kv(r, swap_used):
        B.add(r)
        if not kv_resident(r):
          swap_used += kv_size(r)

      if B reaches decode batch limit:
        break

  execute one decode step for requests in B

  for r in B:
    generated_tokens(r) += 1
    consecutive_skips(r) = 0
    move r to queue_by_generated_tokens(r)

  for r not in B but ready:
    consecutive_skips(r) += 1

  if gpu_blocks are insufficient:
    evict from lowest eligible queues

  return B
```

### 设计不变量

PS-Decode 应明确维护四个不变量：

1. **Iteration feasibility invariant**：每个 decode iteration 的 active batch 必须同时满足 batch size、token budget、GPU block budget 和 swap budget。
2. **Attained-service ordering invariant**：在没有 starvation 标记和 KV 不可行的情况下，低 `generated_tokens` 队列优先于高 `generated_tokens` 队列。
3. **Resident preference invariant**：同一 attained-service level 内，KV resident 请求优先于需要 swap-in 的请求。
4. **Skip-bounded fairness invariant**：一个 ready request 连续被跳过超过 `skip_threshold` 后必须获得 starved tie-break priority；只要资源可行，它不能继续被同级非 starved 请求绕过。

这些不变量把 PS-Decode 和普通 MLFQ 区分开：它不是单纯按时间片轮转，而是在 unknown output length、KV residency 和 per-iteration feasibility 三者之间做在线折中。

### 复杂度与边界

令 active/ready decode 请求数为 `N`，attained-service queue 数为 `Q`，每轮最大 decode batch size 为 `D_max`。

如果每个队列保持 FIFO 加固定 tie-breaker，调度器每轮扫描直到填满 batch：

```text
time complexity: O(min(N, scan_limit))
space complexity: O(N + Q)
```

其中 `scan_limit` 可以设置为 `c * D_max`，例如 `2x` 到 `4x` 的最大 batch size，以避免在超高并发时每轮扫描全部请求。未扫描到的请求会累积 `consecutive_skips`，之后通过 starved tie-breaker 得到补偿。

如果实现选择每轮完整扫描所有队列，则复杂度是 `O(N)`。这更简单，但需要在实验中报告 scheduler CPU overhead。

### Fairness Bound

PS-Decode 不应承诺严格公平，因为它有意偏向低 attained service 请求以改善短请求 slowdown。但它应提供一个可实验验证的 skip bound：

```text
consecutive_skips(r) <= skip_threshold + infeasible_rounds(r)
```

其中 `infeasible_rounds(r)` 表示因为 KV block 不足、swap budget 不足或 batch token budget 不足而无法 admission 的轮数。

这个 bound 的含义是：如果一个请求长期 ready 且资源可行，它不会被无限期跳过。论文实验应报告：

1. long-output slowdown。
2. maximum consecutive skips。
3. starved admission ratio。
4. resident-first 带来的 swap 次数变化。

如果 PS-Decode 显著改善短请求但让长请求 slowdown 不受控，顶会 reviewer 会认为算法只是在转移痛点。因此 fairness analysis 必须作为主实验之一，而不是 appendix。

### 实现映射

PS-Decode 可以直接在 DistServe 的 `DecodingStageFCFSScheduler` 上演进：

1. 将 `waiting_queue` 从单个 list 改为多个 attained-service queues。
2. `unaccepted_queue` 中新迁移来的请求进入 `Q0`。
3. `batch_queues` 仍可复用，只是填充策略从 FCFS 改成 queue-level scan。
4. 使用 DistServe 现有 block manager 检查 GPU/CPU block availability。
5. 第一版先实现 resident-first 和 swap-budget admission，不实现复杂 prefetch overlap。
6. 每个 request 增加少量元数据：`generated_tokens`、`consecutive_skips`、`attained_level`。

### 后续实验设计

PS-Decode 至少需要单独验证以下问题：

1. 相对 DistServe FCFS 是否降低 TPOT p90/p99。
2. 相对 round-robin decode 是否更能照顾短输出请求。
3. 相对纯 LAS、不考虑 KV residency 的策略，是否减少 swap 次数和 iteration stall。
4. 当 output length variance 增大时，收益是否更明显。
5. 长输出请求的 slowdown 是否受 `skip_threshold` 控制。
6. scheduler overhead 是否随 active requests 线性增长，并且在真实 batch size 下可忽略。

### 可发表 claim

PS-Decode 的核心 claim 应该是：

> 在输出长度高度可变、短生成和长生成混合的 workload 下，KV-aware least-attained-service scheduling 可以降低 TPOT tail latency 和短请求 slowdown；同时通过 starvation counter 和 resident-first admission 控制公平性与 swap 开销。

### 暂时不要 claim

不要声称：

- 完整 proactive KV prefetch。
- topology-aware KV routing。
- 总能降低所有请求的平均延迟。
- 完全解决 KV cache management。

对于长输出请求，attained-service scheduling 可能牺牲一部分平均完成时间或长请求公平性。因此论文必须主动讨论 fairness 和 starvation bound。

## 方法三：Coupled Admission Between Phases

这是当前阶段最小且可信的“协调层”。

不建议一开始就 claim broad global controller。更稳的做法是定义一个 bridge admission policy：prefill 是否继续积极 dispatch，要受到 decode pressure 的反馈影响。

### 问题

如果 prefill 调度只优化自身吞吐，它可能会很快完成大量 context computation，并把请求推入 decode 阶段。但 decode 阶段如果已经拥塞，这些请求会堆积在 bridge / unaccepted queue 中。

结果是：

1. prefill 端看起来吞吐很好，但用户感知的 TTFT-to-first-decode 仍然变差。
2. decode queue 变长，TPOT tail latency 上升。
3. 已经生成的 KV state 占用更多内存，增加 swap pressure。

### 机制

定义 decode pressure：

```text
decode_pressure =
  active_decode_blocks / gpu_block_budget
  + waiting_decode_blocks / gpu_block_budget
  + bridge_queue_length / bridge_threshold
```

当 decode pressure 高时，prefill scheduler 应该：

1. 降低目标 batch size 或 token budget。
2. 避免 dispatch 会产生大量 KV footprint 的超长 prompt batch。
3. 在等待时间可接受时，优先处理 KV footprint 较小的请求。

当 decode pressure 低时，prefill scheduler 可以：

1. 更激进地填满 batch。
2. 允许更长 prompt 进入。
3. 提高 prefill 资源利用率。

### 可发表 claim

Bridge admission 的核心 claim 应该是：

> 仅做局部 prefill 或 decode scheduling 仍然可能造成阶段间压力转移；轻量级 decode-pressure feedback 可以减少 bridge queue 堆积，并提升端到端 SLO goodput。

### 暂时不要 claim

不要声称：

- 完整 cluster-wide load balancing。
- topology-aware routing。
- 可以替代 DistServe 的全局资源规划。

它应该被定位为 local coordination，而不是新的大规模控制平面。

## 最终推荐方法

建议将 PhaseServe 的方法论收敛为三部分：

### PS-Prefill

面向已知 prompt length 的 bounded-window cost-compatible batching。

目标：

- 降低 TTFT tail latency。
- 减少 prompt length skew 对 batch efficiency 的影响。
- 通过 protected oldest request 控制长 prompt starvation。
- 在接近饱和时保持较高 prefill utilization。

### PS-Decode

面向未知 output length 的 KV-aware least-attained-service scheduling。

目标：

- 降低 TPOT tail latency。
- 改善短输出请求的排队体验。
- 通过 `consecutive_skips` 和 resident-first admission 控制 starvation 与 swap overhead。

### PS-Bridge

面向阶段间压力传播的 memory-aware bridge admission。

目标：

- 防止 prefill 把 decode 推入过载。
- 控制 KV block pressure 和 swap pressure。
- 提升端到端 SLO goodput。

这三个组件共同构成一个可发表的系统方法，而不是松散的 heuristic 集合。

## 修改后的论文贡献

建议将 contribution 改成如下形式：

1. **问题发现**：我们发现，在 prefill-decode disaggregated LLM serving 中，即使资源已经按阶段隔离，阶段内部的信息不匹配仍然会导致严重的 tail latency 和 SLO goodput 损失。

2. **方法设计**：我们提出 information-matched scheduling，将 prefill 建模为 known-size cost-compatible batching problem，将 decode 建模为 unknown-size KV-constrained least-attained-service scheduling problem，并通过 memory-aware bridge admission 连接两个阶段。

3. **系统实现**：我们在 DistServe 上实现 PhaseServe，替换其 FCFS context scheduler 和 FCFS decode scheduler，并复用现有 block manager 完成 memory-aware admission 和 swap-aware scheduling。

4. **实验验证**：我们在真实模型、真实 GPU 和 trace-driven workload 上评估 PhaseServe，展示其在 TTFT、TPOT、SLO attainment、goodput 和 fairness 上的收益，并通过消融实验证明各组件贡献。

## 现有方法论是否足够

按系统顶会标准，当前初稿还不够，主要不足有四个。

### 1. 系统边界过宽

当前初稿同时声称做 scheduling、global control、routing、KV management、prefetch、eviction。这容易让 reviewer 期待一个完整 production serving stack。

如果实现和实验没有覆盖这些 claim，会被认为 contribution 发散。

建议：把主贡献收窄到 phase-specialized scheduling + memory-aware admission。

### 2. 方法和实现之间的映射不够紧

顶会 reviewer 会问：

- 这个方法到底改了 serving stack 的哪一层？
- 和 DistServe 相比新增了哪些机制？
- 每个机制是否能被单独关闭并复现实验差异？

当前 draft 的一些概念比较抽象，例如 topology-aware handoff 和 proactive KV manager，但实现路径不够具体。

建议：所有方法都要能映射到 DistServe 的 scheduler、block manager、engine event loop。

### 3. KV 相关 claim 风险高

Mooncake 等系统已经把 KV cache 作为核心对象深入研究。如果 PhaseServe 也把 KV manager 放在主贡献中，就必须和这类系统正面比较。

目前更稳的做法是：

- 不 claim 新 KV cache architecture。
- 只 claim memory-aware scheduling。
- 使用现有 block manager 做 admission、swap preference 和 pressure control。

### 4. 缺少可证伪假设

好的系统论文方法论需要能被实验直接验证。当前 draft 的一些 statement 过于笼统，例如“coordinated scheduling improves performance”。

建议改成更具体的 hypotheses：

- H1：prompt length skew 越高，PS-Prefill 对 TTFT p95/p99 的收益越明显。
- H2：在相同 prompt length 分布下，PS-Prefill 相比 shortest-prompt-first 应显著降低 long-prompt starvation。
- H3：output length variance 越高，PS-Decode 对 TPOT p95/p99 和 short-request slowdown 的收益越明显。
- H4：在相同 output length 分布下，KV-aware LAS 相比 pure LAS 应减少 swap 次数和 iteration stall。
- H5：decode pressure 越高，PS-Bridge 对 SLO goodput 的收益越明显。
- H6：在 homogeneous workload 或低负载下，PhaseServe 的收益应下降，但 scheduler overhead 不应显著伤害性能。

这些假设如果被验证，会比笼统 speedup 更有说服力。

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

建议修改：

- 新增 `ContextStageCostCompatibleScheduler`
- 在 waiting queue 上实现 bounded candidate window
- 加入 prompt length bucket 和 bucket-local batch construction
- 加入 protected oldest request 和 `tau_prefill`
- 使用 `pad_waste`、`token_fill`、`block_risk` 选择候选 batch
- 预留 decode pressure feedback 入口，用于调节 `safety_margin`

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

建议修改：

- 新增 `DecodingStageKVAwareLASScheduler`
- 将单一 `waiting_queue` 改为 generated-token 指数桶队列
- 基于 `generated_tokens` 更新 attained-service level
- 基于 `consecutive_skips` 标记 starved requests
- 基于 KV residency 做同级 tie-break
- 基于 GPU block budget 和 swap budget 做 admission

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

建议使用方式：

- 不重写为新 KV manager
- 将 block availability 和 swap pressure 暴露给 scheduler
- 在 decode admission 中作为约束条件和 tie-break 信号

### Engine / CLI

当前文件：

```text
distserve/engine.py
distserve/single_stage_engine.py
```

建议修改：

- 增加 scheduler policy 参数
- 支持 `fcfs`、`cost-compatible-prefill`、`kv-aware-las-decode`、`phase` 等模式
- 增加轻量指标记录：queue length、wait time、generated tokens、consecutive skips、swap count、block pressure、scheduler overhead

## 评估设计提示

虽然本阶段不写实验，但方法论必须能导向后续评估。

建议后续实验至少覆盖：

1. **End-to-end comparison**：DistServe FCFS vs PhaseServe full。
2. **Component ablation**：只开 PS-Prefill、只开 PS-Decode、只开 PS-Bridge、全部开启。
3. **Prompt length skew sensitivity**：控制输入长度分布偏斜程度。
4. **Output length variance sensitivity**：控制输出长度长尾程度。
5. **Load sweep**：从低负载到接近饱和。
6. **Memory pressure sweep**：改变 GPU KV block budget 或并发上限。
7. **Fairness analysis**：检查长请求是否被过度牺牲。
8. **Overhead analysis**：scheduler CPU overhead、额外 queue 操作成本、swap 次数变化。

如果这些实验能做完整，这篇论文的方法论会明显更扎实。

## Reviewer 可能质疑的问题

### 质疑一：这是不是只是 heuristic？

回答方向：

PhaseServe 的贡献不是单个复杂 heuristic，而是识别了 prefill/decode 解耦之后的信息结构差异，并将两个经典调度思想映射到 LLM serving runtime：

- bounded-window cost-compatible batching for known-size prefill；
- KV-aware least-attained-service scheduling for unknown-size decode。

实现是轻量启发式，但设计不是 ad hoc：PS-Prefill 维护 feasibility、oldest protection 和 no artificial waiting 三个不变量；PS-Decode 维护 iteration feasibility、attained-service ordering、resident preference 和 skip-bounded fairness 四个不变量。

### 质疑二：为什么不用 learned latency predictor？

回答方向：

LLM serving 中 latency predictor 对模型、batch size、parallelism、KV residency、hardware state 高度敏感，泛化难度高。PhaseServe 故意使用低成本、稳定可观测的信号，使方法更易部署和复现。

### 质疑三：是否牺牲长请求？

回答方向：

PS-Decode 不承诺严格 max-min fairness，而是使用 `consecutive_skips` 提供 skip-bounded fairness。论文需要报告长请求 tail latency、long-output slowdown、maximum consecutive skips 和 starved admission ratio，而不是只报告平均 TPOT。

### 质疑四：和 DistServe 的区别是否足够？

回答方向：

DistServe 的主要贡献是 prefill/decode disaggregation 和资源配置；PhaseServe 的贡献是 disaggregation 之后的 local scheduling。PhaseServe 可以被实现为 DistServe 的 scheduler extension，因此二者是互补关系。

### 质疑五：和 Mooncake 的 KV 管理相比有什么关系？

回答方向：

PhaseServe 不 claim 新 KV cache architecture。它只把 KV block pressure 作为 scheduling 和 admission 的约束信号。KV-centric serving architecture 不是本文主贡献。

## 推荐论文结构

建议整篇论文围绕“信息不对称调度”展开。

1. **Introduction**
   - 说明 disaggregated serving 已经减少 inter-phase interference。
   - 指出 remaining bottleneck 是 intra-phase scheduling mismatch。
   - 给出 motivating example：FCFS 在 skewed prompt 和 variable output 下失败。

2. **Background and Motivation**
   - 介绍 prefill/decode 特性。
   - 介绍 DistServe 的 phase disaggregation。
   - 展示 FCFS scheduler 的局限。

3. **Design Principles**
   - Prefill is known-size。
   - Decode is unknown-size。
   - Memory pressure couples the phases。
   - Formal model、resource constraints、invariants。

4. **PhaseServe Design**
   - PS-Prefill：bounded-window cost-compatible batching。
   - PS-Decode：KV-aware least-attained-service scheduling。
   - PS-Bridge：decode-pressure-aware admission。

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
   - 局限。
   - 和 KV-centric systems 的关系。
   - 多节点 routing 的未来工作。

8. **Related Work**
   - Disaggregated LLM serving。
   - LLM serving schedulers。
   - KV cache management。
   - Online scheduling。

## 对当前 draft 的修改建议

当前 draft 可以保留：

- phase-specialized scheduling 这个主线。
- prefill 利用 prompt length 已知这一点。
- decode 利用 generated tokens / attained service 这一点。
- TTFT、TPOT、SLO goodput 作为核心指标。

当前 draft 应该弱化：

- global phase controller。
- topology-aware routing。
- proactive KV prefetch。
- cold-state eviction。
- 尚未真实验证的绝对 speedup 数字。

当前 draft 应该新增：

- 更清晰的问题定义。
- 为什么 prefill 和 decode 是不同在线调度问题。
- 为什么 prompt length 和 generated tokens 是足够好的信号。
- PS-Prefill 的 cost-compatible batch 选择规则和 bounded waiting 规则。
- PS-Decode 的 KV-aware LAS 队列组织、resident-first tie-breaker 和 skip-based fairness 规则。
- 每个机制的消融实验计划。
- fairness 和 overhead 的讨论。

## 推荐命名

如果继续使用 PhaseServe 作为系统名，方法模块建议命名为：

- `PS-Prefill`: bounded-window cost-compatible prefill batching。
- `PS-Decode`: KV-aware least-attained-service decode scheduling。
- `PS-Bridge`: decode-pressure-aware bridge admission。

论文副标题或方法概括可以考虑：

> PhaseServe: Information-Matched Scheduling for Disaggregated LLM Serving

或者：

> PhaseServe: Information-Asymmetric Scheduling for Prefill-Decode Disaggregated LLM Serving

这两个标题都比“coordinated scheduling and KV management”更聚焦，也更容易让 reviewer 明白本文的真正贡献。

## 最终判断

现有方法论不建议直接进入实验阶段。

更稳的下一步是先把方法论收敛成：

```text
information-asymmetric scheduling
  = bounded-window cost-compatible prefill batching
  + KV-aware least-attained-service decode scheduling
  + memory-aware bridge admission
```

如果后续实现和实验能够证明这三点，PhaseServe 就有机会成为一篇扎实的系统论文。

如果继续沿着当前初稿中更宽泛的方向推进，风险是论文看起来 claim 很大，但 reviewer 会认为每个点都不够深，最终变成“一个工程系统加若干 heuristic”，顶会说服力会弱很多。
