from abc import ABC, abstractmethod
import copy
import os
import time
from typing import List, Callable, Tuple

from distserve.config import ContextStageSchedConfig, ParallelConfig
from distserve.logger import init_logger
from distserve.request import Request, BatchedRequests, MigratingRequest
from distserve.block_manager import BlockManager
from distserve.phase_scheduler import (
    PressureBudgetController,
    append_phase_metric,
    read_pressure_snapshot,
    ratio,
)

logger = init_logger(__name__)


class ContextStageScheduler(ABC):
    """
    ContextStageScheduler: The abstract class for a context scheduler.
    
    It should maintain all the requests in the current systems, and support two basic ops:
        - add_request: Add a newly arrived request into the waiting queue
        - get_next_batch_and_pop: Get the next batch for the context stage, and 
          pop the requests in the batch from the waiting queue.
    
    This scheduler is much simpler than DecodingStageScheduler since one request
    will only be processed by one context stage.      
    """

    @abstractmethod
    def add_request(self, request: Request) -> None:
        """
        Add a request to the scheduler.
        """
        raise NotImplementedError()

    @abstractmethod
    def abort_request(self, request_id: int) -> None:
        """
        Cancel a request from the scheduler.
        """
        raise NotImplementedError()

    @abstractmethod
    def get_next_batch_and_pop(self) -> BatchedRequests:
        """
        Get a batch of requests for the execution of next iteration and
        pop the requests in the batch from the waiting queue.
        """
        raise NotImplementedError()

    @abstractmethod
    def get_num_waiting_requests(self) -> int:
        """
        Get the number of requests that are waiting for processing.
        """
        raise NotImplementedError()

    @abstractmethod
    def print_status(self) -> None:
        """
        Print the status of the scheduler.
        """
        raise NotImplementedError()
    
    def on_finish_requests(self, batch: BatchedRequests) -> None:
        """
        Callback function when a batch of requests finish the context stage.
        """
        pass
    
    def on_request_migrated(self, migrated_request: MigratingRequest) -> None:
        """
        Callback function when a request is migrated to the decoding stage
        """
        pass
    
    def post_process(self) -> None:
        """
        Post process after each iteration. ContextEventLoop will call this
        function after each iteration.
        """
        pass


class ContextStageFCFSScheduler(ContextStageScheduler):
    """
    A first-come-first-serve scheduler.
    """

    def __init__(
        self,
        sched_config: ContextStageSchedConfig, 
        parallel_config: ParallelConfig,
        block_manager: BlockManager):
        
        assert (
            sched_config.policy == "fcfs"
        ), f"can not initialize a FCFS scheduler with policy {sched_config.policy}"
        self.sched_config = sched_config
        # If the current batch is full, the requests will be put into the waiting queue.
        self.waiting_queue = []
        self.parallel_config: List[Request] = copy.deepcopy(parallel_config)
        self.block_manager = block_manager
        # Requests that finished the context stage but are not accepted by the decoding stage.
        self.unaccepted_queue: List[Request] = []
        # The number of on-the-fly (i.e. processing) request blocks
        # Adds when calling get_next_batch_and_pop()
        # Subtracts when calling on_finish_requests()
        self.num_on_fly_request_block = 0

    def add_request(self, request: Request) -> None:
        """
        Add a request to the scheduler.
        """
        self.waiting_queue.append(request)

    def abort_request(self, request_id: int) -> None:
        """
        Cancel a request from the scheduler.
        """
        for i, request in enumerate(self.waiting_queue):
            if request.request_id == request_id:
                del self.waiting_queue[i]
                return

    def _get_block_needed(self, length: int):
        block_size = self.block_manager.cache_config.block_size
        return (length + block_size - 1) // block_size

    def _can_add_to_context_batch(self, batch: BatchedRequests, request: Request) -> bool:
        return (
            len(batch) < self.sched_config.max_batch_size
        ) and (
            batch.get_num_input_tokens()
            + request.get_num_input_tokens()
            <= self.sched_config.max_tokens_per_batch
        ) and (
            sum([
                self._get_block_needed(len(req.prompt_token_ids))
                for req in batch.requests + [request]
            ]) +
            sum([
                self._get_block_needed(len(req.prompt_token_ids))
                for req in self.unaccepted_queue
            ]) +
            self.num_on_fly_request_block
            <= self.block_manager.max_num_gpu_blocks
        )
            
    def get_next_batch_and_pop(self) -> BatchedRequests:
        """
        Get the next batch for the context stage in a FCFS-like manner, and pop them
        """
        next_batch = BatchedRequests()

        while len(self.waiting_queue) > 0:
            request = self.waiting_queue[0]
            if self._can_add_to_context_batch(next_batch, request):
                next_batch.add_request(request)
                self.waiting_queue.pop(0)
            else:
                break
        
        self.num_on_fly_request_block += sum([
            self._get_block_needed(req.get_input_len())
            for req in next_batch.requests
        ])

        return next_batch

    def on_finish_requests(self, batch: BatchedRequests):
        for request in batch.requests:
            if not request.is_finished:
                self.unaccepted_queue.append(request)
        
        self.num_on_fly_request_block -= sum([
            self._get_block_needed(req.get_input_len())
            for req in batch.requests
        ])
    
    def on_request_migrated(self, migrated_request: MigratingRequest):
        for i, request in enumerate(self.unaccepted_queue):
            if request.request_id == migrated_request.req.request_id:
                del self.unaccepted_queue[i]
                return
            
    def get_num_waiting_requests(self) -> int:
        return len(self.waiting_queue)

    def __repr__(self) -> str:
        return (
            f"FCFS(max_batch_size={self.sched_config.max_batch_size}, "
            f"max_tokens_per_batch={self.sched_config.max_tokens_per_batch})"
        )
    
    def print_status(self):
        logger.info(f"(context) {len(self.waiting_queue)} waiting, {len(self.unaccepted_queue)} finished but unaccepted, {self.num_on_fly_request_block} blocks occupied by on-the-fly requests")


class ContextStageShortestPrefillScheduler(ContextStageFCFSScheduler):
    """Shortest-prompt-first baseline for BPS claim validation."""

    def __init__(
        self,
        sched_config: ContextStageSchedConfig,
        parallel_config: ParallelConfig,
        block_manager: BlockManager):

        assert sched_config.policy in [
            "shortest-prefill",
            "shortest-prompt-first",
        ], f"can not initialize a shortest-prefill scheduler with policy {sched_config.policy}"
        self.sched_config = sched_config
        self.waiting_queue = []
        self.parallel_config: List[Request] = copy.deepcopy(parallel_config)
        self.block_manager = block_manager
        self.unaccepted_queue: List[Request] = []
        self.num_on_fly_request_block = 0

    def get_next_batch_and_pop(self) -> BatchedRequests:
        next_batch = BatchedRequests()

        while len(self.waiting_queue) > 0:
            added = False
            ordered = sorted(
                self.waiting_queue,
                key=lambda req: (req.get_input_len(), req.request_id),
            )
            for request in ordered:
                if self._can_add_to_context_batch(next_batch, request):
                    next_batch.add_request(request)
                    self.waiting_queue.remove(request)
                    added = True
                    break
            if not added:
                break

        self.num_on_fly_request_block += sum([
            self._get_block_needed(req.get_input_len())
            for req in next_batch.requests
        ])

        return next_batch

    def __repr__(self) -> str:
        return (
            f"ShortestPrefill(max_batch_size={self.sched_config.max_batch_size}, "
            f"max_tokens_per_batch={self.sched_config.max_tokens_per_batch})"
        )


class ContextStageCostCompatibleScheduler(ContextStageFCFSScheduler):
    """
    Bounded-window cost-compatible prefill scheduler.

    This is the minimal PS-Prefill implementation used for controlled
    experiments. It only reorders requests already present in a bounded prefix
    of the waiting queue, groups them by prompt length, and dispatches the best
    resource-feasible batch. The oldest request is protected after a bounded
    wait to avoid starving long prompts.
    """

    def __init__(
        self,
        sched_config: ContextStageSchedConfig,
        parallel_config: ParallelConfig,
        block_manager: BlockManager):

        assert sched_config.policy in [
            "cost-compatible",
            "cost-compatible-prefill",
            "phase",
        ], f"can not initialize a cost-compatible scheduler with policy {sched_config.policy}"
        self.sched_config = sched_config
        self.waiting_queue = []
        self.parallel_config: List[Request] = copy.deepcopy(parallel_config)
        self.block_manager = block_manager
        self.unaccepted_queue: List[Request] = []
        self.num_on_fly_request_block = 0

        self.window_multiplier = int(os.environ.get("PHASESERVE_PREFILL_WINDOW_MULT", "4"))
        self.dispatch_timeout_s = float(os.environ.get("PHASESERVE_PREFILL_TIMEOUT_S", "0.25"))
        self.bucket_bounds = [
            int(x) for x in os.environ.get(
                "PHASESERVE_PREFILL_BUCKETS",
                "256,512,1024,2048,4096"
            ).split(",") if x
        ]
        self.alpha = float(os.environ.get("PHASESERVE_PREFILL_ALPHA", "0.5"))
        self.beta = float(os.environ.get("PHASESERVE_PREFILL_BETA", "0.1"))
        self.gamma = float(os.environ.get("PHASESERVE_PREFILL_GAMMA", "1.0"))
        self.short_priority_weight = float(os.environ.get(
            "PHASESERVE_PREFILL_SHORT_PRIORITY",
            "0.75" if self.sched_config.policy == "phase" else "0.0",
        ))
        self.short_priority_threshold = float(os.environ.get(
            "PHASESERVE_PREFILL_SHORT_PRIORITY_PRESSURE",
            "0.35",
        ))
        self.token_fill_pressure_discount = float(os.environ.get(
            "PHASESERVE_PREFILL_TOKEN_FILL_PRESSURE_DISCOUNT",
            "0.35" if self.sched_config.policy == "phase" else "0.0",
        ))
        self.scoring_mode = os.environ.get(
            "PHASESERVE_PREFILL_SCORING_MODE",
            "default",
        ).lower()
        self.prefill_kv_eta = float(os.environ.get("PHASESERVE_PBC_PREFILL_KV_ETA", "1.0"))
        self.long_prompt_threshold = int(os.environ.get(
            "PHASESERVE_PREFILL_LONG_PROMPT_TOKENS",
            "1024",
        ))
        max_block_margin = int(os.environ.get(
            "PHASESERVE_PBC_MAX_BLOCK_MARGIN",
            str(max(1, int(self.block_manager.max_num_gpu_blocks * 0.10)))
        ))
        self.pressure_controller = PressureBudgetController(
            component="context",
            max_prefill_tokens=self.sched_config.max_tokens_per_batch,
            max_prefill_block_margin=max_block_margin,
        )
        self.bridge_target = float(os.environ.get("PHASESERVE_PBC_BRIDGE_TARGET", "4"))
        self.context_block_target = float(os.environ.get(
            "PHASESERVE_PBC_CONTEXT_BLOCK_TARGET",
            str(max(self.block_manager.max_num_gpu_blocks * 0.85, 1))
        ))
        self.hard_free_block_frac = float(os.environ.get(
            "PHASESERVE_PBC_HARD_FREE_BLOCK_FRAC",
            "0.02",
        ))
        self.current_budget = None
        self.last_decode_snapshot = {"available": False}
        self.bypass_blocked_oldest = os.environ.get(
            "PHASESERVE_PREFILL_BYPASS_BLOCKED_OLDEST",
            "0",
        ).lower() in {"1", "true", "yes", "on"}
        self.bypass_blocked_oldest_pressure = float(os.environ.get(
            "PHASESERVE_PREFILL_BYPASS_BLOCKED_OLDEST_PRESSURE",
            "0.65",
        ))

        self.num_dispatches = 0
        self.total_sched_time_s = 0.0
        self.num_oldest_forced = 0
        self.num_protected_triggers = 0
        self.num_protected_selected = 0
        self.num_protected_forced_single = 0
        self.num_protected_blocked = 0
        self.num_protected_bypassed = 0

    def add_request(self, request: Request) -> None:
        request.phaseserve_context_enqueue_time = time.perf_counter()
        self.waiting_queue.append(request)

    def _get_wait_time(self, request: Request, now: float = None) -> float:
        now = time.perf_counter() if now is None else now
        return now - getattr(
            request,
            "phaseserve_context_enqueue_time",
            request.arrival_time,
        )

    def _summarize_waits(self, requests: List[Request], now: float) -> dict:
        if not requests:
            return {
                "count": 0,
                "max_wait_s": None,
                "max_wait_prompt_len": None,
                "max_wait_bucket": None,
                "long_prompt_count": 0,
                "long_prompt_max_wait_s": None,
                "long_prompt_max_wait_prompt_len": None,
                "long_prompt_max_wait_bucket": None,
            }
        rows = [(request, self._get_wait_time(request, now)) for request in requests]
        max_request, max_wait = max(rows, key=lambda item: item[1])
        long_rows = [
            (request, wait)
            for request, wait in rows
            if request.get_input_len() >= self.long_prompt_threshold
        ]
        if long_rows:
            long_request, long_wait = max(long_rows, key=lambda item: item[1])
            long_prompt_len = long_request.get_input_len()
            long_bucket = self._get_bucket_id(long_request)
        else:
            long_wait = None
            long_prompt_len = None
            long_bucket = None
        return {
            "count": len(requests),
            "max_wait_s": max_wait,
            "max_wait_prompt_len": max_request.get_input_len(),
            "max_wait_bucket": self._get_bucket_id(max_request),
            "long_prompt_count": len(long_rows),
            "long_prompt_max_wait_s": long_wait,
            "long_prompt_max_wait_prompt_len": long_prompt_len,
            "long_prompt_max_wait_bucket": long_bucket,
        }

    def _get_bucket_id(self, request: Request) -> int:
        length = request.get_input_len()
        for idx, bound in enumerate(self.bucket_bounds):
            if length <= bound:
                return idx
        return len(self.bucket_bounds)

    def _get_available_context_blocks(self) -> int:
        reserved_blocks = sum([
            self._get_block_needed(len(req.prompt_token_ids))
            for req in self.unaccepted_queue
        ]) + self.num_on_fly_request_block
        return max(self.block_manager.max_num_gpu_blocks - reserved_blocks, 0)

    def _get_context_budget(self, protected_wait: float = 0.0):
        reserved_blocks = self.block_manager.max_num_gpu_blocks - self._get_available_context_blocks()
        pressures = {
            "bridge": ratio(len(self.unaccepted_queue), self.bridge_target),
            "first": 0.0,
            "decode": 0.0,
            "kv": ratio(reserved_blocks, self.context_block_target),
            "swap": 0.0,
            "decode_hard": 0.0,
            "kv_hard": 0.0,
            "age": ratio(protected_wait, self.dispatch_timeout_s),
        }
        snapshot = read_pressure_snapshot(expected_component="decode")
        snapshot_used = False
        decode_hard_details = {}
        if snapshot and snapshot.get("available") and not snapshot.get("stale") and not snapshot.get("wrong_component"):
            decode_pressures = snapshot.get("pressures") or {}
            pressures["bridge"] = max(pressures["bridge"], float(decode_pressures.get("bridge", 0.0) or 0.0))
            pressures["first"] = float(decode_pressures.get("first", 0.0) or 0.0)
            pressures["decode"] = float(decode_pressures.get("decode", 0.0) or 0.0)
            pressures["kv"] = max(pressures["kv"], float(decode_pressures.get("kv", 0.0) or 0.0))
            pressures["swap"] = float(decode_pressures.get("swap", 0.0) or 0.0)
            max_gpu_blocks = float(snapshot.get("max_gpu_blocks") or 0.0)
            available_gpu_blocks = float(snapshot.get("available_gpu_blocks") or max_gpu_blocks)
            hard_free_target = max(max_gpu_blocks * self.hard_free_block_frac, 1.0)
            kv_hard = ratio(max(hard_free_target - available_gpu_blocks, 0.0), hard_free_target)
            hard_pressure = max(pressures["swap"], kv_hard)
            pressures["decode_hard"] = hard_pressure
            pressures["kv_hard"] = hard_pressure
            decode_hard_details = {
                "available_gpu_blocks": available_gpu_blocks,
                "max_gpu_blocks": max_gpu_blocks,
                "hard_free_target": hard_free_target,
                "kv_hard": kv_hard,
                "hard_pressure": hard_pressure,
            }
            snapshot_used = True
        self.last_decode_snapshot = {
            "available": bool(snapshot and snapshot.get("available")),
            "used": snapshot_used,
            "age_s": (snapshot or {}).get("age_s"),
            "stale": bool(snapshot and snapshot.get("stale")),
            "wrong_component": bool(snapshot and snapshot.get("wrong_component")),
            "pressures": (snapshot or {}).get("pressures", {}),
            "hard": decode_hard_details,
        }
        self.current_budget = self.pressure_controller.update(pressures)
        return self.current_budget

    def _is_feasible(self, batch: BatchedRequests, request: Request, ignore_pressure_budget: bool = False) -> bool:
        budget = self.current_budget
        token_budget = (
            min(self.sched_config.max_tokens_per_batch, budget.prefill_token_budget)
            if not ignore_pressure_budget and budget is not None and budget.prefill_token_budget > 0
            else self.sched_config.max_tokens_per_batch
        )
        block_margin = (
            budget.prefill_block_margin
            if not ignore_pressure_budget and budget is not None
            else 0
        )
        return (
            len(batch) < self.sched_config.max_batch_size
        ) and (
            batch.get_num_input_tokens()
            + request.get_num_input_tokens()
            <= token_budget
        ) and (
            sum([
                self._get_block_needed(req.get_input_len())
                for req in batch.requests + [request]
            ]) <= max(self._get_available_context_blocks() - block_margin, 0)
        )

    def _batch_prompt_lengths(self, batch: BatchedRequests) -> List[int]:
        return [req.get_input_len() for req in batch.requests]

    def _batch_prefill_blocks(self, batch: BatchedRequests) -> int:
        return sum([self._get_block_needed(req.get_input_len()) for req in batch.requests])

    def _batch_token_fill(self, batch: BatchedRequests) -> float:
        return batch.get_num_input_tokens() / max(self.sched_config.max_tokens_per_batch, 1)

    def _batch_shortness(self, batch: BatchedRequests) -> float:
        lengths = self._batch_prompt_lengths(batch)
        if not lengths:
            return 0.0
        longest = max(lengths)
        return 1.0 - min(longest / max(self.sched_config.max_tokens_per_batch, 1), 1.0)

    def _batch_pad_waste(self, batch: BatchedRequests) -> float:
        lengths = self._batch_prompt_lengths(batch)
        if not lengths:
            return 0.0
        return (
            (max(lengths) * len(lengths) - sum(lengths))
            / max(self.sched_config.max_tokens_per_batch, 1)
        )

    def _batch_block_risk(self, batch: BatchedRequests) -> float:
        return self._batch_prefill_blocks(batch) / max(self._get_available_context_blocks(), 1)

    def _score_batch(
        self,
        batch: BatchedRequests,
        protected_request: Request,
        protected_wait: float,
    ) -> float:
        if len(batch) == 0:
            return float("-inf")
        token_fill = self._batch_token_fill(batch)
        if self.scoring_mode == "bucket_only":
            return token_fill
        pad_waste = self._batch_pad_waste(batch)
        block_risk = self._batch_block_risk(batch)
        oldest_bonus = 1.0 if protected_request in batch.requests else 0.0
        if self.scoring_mode == "no_oldest_bonus":
            oldest_bonus = 0.0
        elif self.scoring_mode == "age_bonus":
            oldest_bonus = (
                min(protected_wait / max(self.dispatch_timeout_s, 1e-6), 1.0)
                if protected_request in batch.requests
                else 0.0
            )
        budget = self.current_budget
        pressure_multiplier = 1.0 + (budget.rho_down if budget is not None else 0.0)
        first_token_pressure = 0.0
        if budget is not None:
            first_token_pressure = max(
                float(getattr(budget, "pressure_bridge", 0.0) or 0.0),
                float(getattr(budget, "pressure_first", 0.0) or 0.0),
            )
        short_pressure = max(first_token_pressure - self.short_priority_threshold, 0.0)
        short_pressure = short_pressure / max(1.0 - self.short_priority_threshold, 1e-6)
        short_pressure = min(max(short_pressure, 0.0), 1.0)
        token_fill_scale = max(
            1.0 - self.token_fill_pressure_discount * short_pressure,
            0.0,
        )
        short_bonus = self.short_priority_weight * short_pressure * self._batch_shortness(batch)
        return (
            token_fill * token_fill_scale
            - self.alpha * pad_waste
            - self.beta * pressure_multiplier * block_risk
            + self.gamma * oldest_bonus
            + short_bonus
        )

    def _ordered_bucket_requests(self, requests: List[Request], protected_request: Request) -> List[Request]:
        if not requests:
            return []
        median_len = sorted([req.get_input_len() for req in requests])[len(requests) // 2]
        return sorted(
            requests,
            key=lambda req: (
                req is not protected_request,
                -self._get_wait_time(req),
                abs(req.get_input_len() - median_len),
                req.request_id,
            ),
        )

    def _should_bypass_blocked_oldest(self, budget) -> bool:
        if not self.bypass_blocked_oldest or budget is None:
            return False
        pressure = max(
            float(getattr(budget, "rho_down", 0.0) or 0.0),
            float(getattr(budget, "pressure_bridge", 0.0) or 0.0),
            float(getattr(budget, "pressure_first", 0.0) or 0.0),
            float(getattr(budget, "pressure_decode_hard", 0.0) or 0.0),
            float(getattr(budget, "pressure_kv_hard", 0.0) or 0.0),
        )
        return pressure >= self.bypass_blocked_oldest_pressure

    def get_next_batch_and_pop(self) -> BatchedRequests:
        sched_start = time.perf_counter()
        next_batch = BatchedRequests()
        if len(self.waiting_queue) == 0:
            return next_batch

        window_size = max(
            self.sched_config.max_batch_size * self.window_multiplier,
            self.sched_config.max_batch_size,
            1,
        )
        now = time.perf_counter()
        candidate_window = self.waiting_queue[:window_size]
        protected_request = candidate_window[0]
        protected_wait = self._get_wait_time(protected_request, now)
        budget = self._get_context_budget(protected_wait)
        waiting_waits = self._summarize_waits(self.waiting_queue, now)
        candidate_waits = self._summarize_waits(candidate_window, now)

        buckets = {}
        for request in candidate_window:
            buckets.setdefault(self._get_bucket_id(request), []).append(request)

        candidate_batches = []
        for _, bucket_requests in sorted(buckets.items()):
            batch = BatchedRequests()
            for request in self._ordered_bucket_requests(bucket_requests, protected_request):
                if self._is_feasible(batch, request):
                    batch.add_request(request)
            if len(batch) > 0:
                candidate_batches.append(batch)

        protected_due_age = protected_wait >= self.dispatch_timeout_s
        protected_due_budget = bool(budget.allow_protected_oldest)
        protected_triggered = protected_due_age or protected_due_budget
        protected_forced_single = False
        protected_blocked = False
        protected_bypassed = False
        if protected_triggered:
            protected_batches = [
                batch for batch in candidate_batches
                if protected_request in batch.requests
            ]
            if protected_batches:
                candidate_batches = protected_batches
            else:
                forced_batch = BatchedRequests()
                if self._is_feasible(forced_batch, protected_request, ignore_pressure_budget=True):
                    forced_batch.add_request(protected_request)
                    candidate_batches = [forced_batch]
                    protected_forced_single = True
                else:
                    if candidate_batches and self._should_bypass_blocked_oldest(budget):
                        protected_bypassed = True
                    else:
                        candidate_batches = []
                    protected_blocked = True
            self.num_oldest_forced += 1
            self.num_protected_triggers += 1

        if candidate_batches:
            next_batch = max(
                candidate_batches,
                key=lambda batch: self._score_batch(batch, protected_request, protected_wait)
            )

        selected_ids = set([req.request_id for req in next_batch.requests])
        protected_selected = protected_request.request_id in selected_ids
        if protected_triggered and protected_selected:
            self.num_protected_selected += 1
        if protected_forced_single:
            self.num_protected_forced_single += 1
        if protected_blocked:
            self.num_protected_blocked += 1
        if protected_bypassed:
            self.num_protected_bypassed += 1
        selected_waits = self._summarize_waits(next_batch.requests, now)
        if selected_ids:
            self.waiting_queue = [
                req for req in self.waiting_queue
                if req.request_id not in selected_ids
            ]

        self.num_on_fly_request_block += sum([
            self._get_block_needed(req.get_input_len())
            for req in next_batch.requests
        ])
        self.num_dispatches += 1
        sched_time_s = time.perf_counter() - sched_start
        self.total_sched_time_s += sched_time_s
        selected_prefill_blocks = self._batch_prefill_blocks(next_batch)
        token_fill = self._batch_token_fill(next_batch)
        pad_waste = self._batch_pad_waste(next_batch)
        block_risk = self._batch_block_risk(next_batch)
        pressure_injection_prefill = min(
            token_fill
            + self.prefill_kv_eta * selected_prefill_blocks / max(self.block_manager.max_num_gpu_blocks, 1),
            1.0,
        )
        if budget is not None:
            budget.pressure_injection_prefill = pressure_injection_prefill
        append_phase_metric("context", "dispatch", {
            "waiting": len(self.waiting_queue),
            "unaccepted": len(self.unaccepted_queue),
            "on_fly_blocks": self.num_on_fly_request_block,
            "candidate_window": len(candidate_window),
            "candidate_batches": len(candidate_batches),
            "selected": len(next_batch.requests),
            "selected_prompt_tokens": next_batch.get_num_input_tokens(),
            "selected_prefill_blocks": selected_prefill_blocks,
            "token_fill": token_fill,
            "pad_waste": pad_waste,
            "block_risk": block_risk,
            "pressure_injection_prefill": pressure_injection_prefill,
            "max_prefill_tokens": self.sched_config.max_tokens_per_batch,
            "forced_oldest": protected_triggered,
            "protected_triggered": protected_triggered,
            "protected_due_age": protected_due_age,
            "protected_due_budget": protected_due_budget,
            "protected_selected": protected_selected,
            "protected_forced_single": protected_forced_single,
            "protected_blocked": protected_blocked,
            "protected_bypassed": protected_bypassed,
            "protected_bypassed_total": self.num_protected_bypassed,
            "protected_bypass_enabled": self.bypass_blocked_oldest,
            "protected_bypass_pressure": self.bypass_blocked_oldest_pressure,
            "protected_wait_s": protected_wait,
            "protected_prompt_len": protected_request.get_input_len(),
            "protected_bucket": self._get_bucket_id(protected_request),
            "long_prompt_threshold": self.long_prompt_threshold,
            "waiting_waits": waiting_waits,
            "candidate_waits": candidate_waits,
            "selected_waits": selected_waits,
            "scoring_mode": self.scoring_mode,
            "short_priority_weight": self.short_priority_weight,
            "token_fill_pressure_discount": self.token_fill_pressure_discount,
            "decode_snapshot": self.last_decode_snapshot,
            "sched_time_s": sched_time_s,
            "budget": budget,
            "controller": self.pressure_controller.metrics(),
        })

        return next_batch

    def __repr__(self) -> str:
        return (
            f"CostCompatible(max_batch_size={self.sched_config.max_batch_size}, "
            f"max_tokens_per_batch={self.sched_config.max_tokens_per_batch}, "
            f"window_mult={self.window_multiplier}, scoring={self.scoring_mode})"
        )

    def print_status(self):
        avg_sched_ms = (
            self.total_sched_time_s / max(self.num_dispatches, 1) * 1000.0
        )
        logger.info(
            f"(context-cost-compatible) {len(self.waiting_queue)} waiting, "
            f"{len(self.unaccepted_queue)} finished but unaccepted, "
            f"{self.num_on_fly_request_block} blocks occupied by on-the-fly requests, "
            f"avg_sched_ms={avg_sched_ms:.3f}, forced_oldest={self.num_oldest_forced}, "
            f"protected={self.num_protected_selected}/{self.num_protected_triggers}, "
            f"protected_blocked={self.num_protected_blocked}"
        )


def get_context_stage_scheduler(
    sched_config: ContextStageSchedConfig,
    parallel_config: ParallelConfig,
    block_manager: BlockManager
) -> ContextStageScheduler:
    if sched_config.policy == "fcfs":
        return ContextStageFCFSScheduler(sched_config, parallel_config, block_manager)
    elif sched_config.policy in ["shortest-prefill", "shortest-prompt-first"]:
        return ContextStageShortestPrefillScheduler(sched_config, parallel_config, block_manager)
    elif sched_config.policy in ["cost-compatible", "cost-compatible-prefill", "phase"]:
        return ContextStageCostCompatibleScheduler(sched_config, parallel_config, block_manager)
    else:
        raise NotImplementedError(f"Unknown context scheduler policy {sched_config.policy}")
    
