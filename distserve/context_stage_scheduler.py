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
            
    def get_next_batch_and_pop(self) -> BatchedRequests:
        """
        Get the next batch for the context stage in a FCFS-like manner, and pop them
        """
        next_batch = BatchedRequests()

        def _check_add_to_cur_batch(request: Request) -> bool:
            """
            Check whether the request can be added to the current batch.
            """
            return (
                # Limit 1. batch size
                len(next_batch) < self.sched_config.max_batch_size
            ) and (
                # Limit 2. tokens per batch
                next_batch.get_num_input_tokens()
                + request.get_num_input_tokens()
                <= self.sched_config.max_tokens_per_batch
            ) and (
                # Limit 3. GPU blocks
                sum([
                    self._get_block_needed(len(req.prompt_token_ids))
                    for req in next_batch.requests + [request]
                ]) +
                sum([
                    self._get_block_needed(len(req.prompt_token_ids))
                    for req in self.unaccepted_queue
                ]) +
                self.num_on_fly_request_block 
                <= self.block_manager.max_num_gpu_blocks
            )
    
        while len(self.waiting_queue) > 0:
            request = self.waiting_queue[0]
            if _check_add_to_cur_batch(request):
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
        self.scoring_mode = os.environ.get(
            "PHASESERVE_PREFILL_SCORING_MODE",
            "default",
        ).lower()
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
        self.current_budget = None

        self.num_dispatches = 0
        self.total_sched_time_s = 0.0
        self.num_oldest_forced = 0

    def add_request(self, request: Request) -> None:
        request.phaseserve_context_enqueue_time = time.perf_counter()
        self.waiting_queue.append(request)

    def _get_wait_time(self, request: Request) -> float:
        return time.perf_counter() - getattr(
            request,
            "phaseserve_context_enqueue_time",
            request.arrival_time,
        )

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
            "decode": 0.0,
            "kv": ratio(reserved_blocks, self.context_block_target),
            "swap": 0.0,
            "age": ratio(protected_wait, self.dispatch_timeout_s),
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

    def _score_batch(
        self,
        batch: BatchedRequests,
        protected_request: Request,
        protected_wait: float,
    ) -> float:
        if len(batch) == 0:
            return float("-inf")
        lengths = [req.get_input_len() for req in batch.requests]
        token_sum = sum(lengths)
        token_fill = token_sum / max(self.sched_config.max_tokens_per_batch, 1)
        if self.scoring_mode == "bucket_only":
            return token_fill
        pad_waste = (
            (max(lengths) * len(lengths) - token_sum)
            / max(self.sched_config.max_tokens_per_batch, 1)
        )
        block_risk = (
            sum([self._get_block_needed(req.get_input_len()) for req in batch.requests])
            / max(self._get_available_context_blocks(), 1)
        )
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
        return (
            token_fill
            - self.alpha * pad_waste
            - self.beta * pressure_multiplier * block_risk
            + self.gamma * oldest_bonus
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
        candidate_window = self.waiting_queue[:window_size]
        protected_request = candidate_window[0]
        protected_wait = self._get_wait_time(protected_request)
        budget = self._get_context_budget(protected_wait)

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

        if protected_wait >= self.dispatch_timeout_s or budget.allow_protected_oldest:
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
            self.num_oldest_forced += 1

        if candidate_batches:
            next_batch = max(
                candidate_batches,
                key=lambda batch: self._score_batch(batch, protected_request, protected_wait)
            )

        selected_ids = set([req.request_id for req in next_batch.requests])
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
        append_phase_metric("context", "dispatch", {
            "waiting": len(self.waiting_queue),
            "unaccepted": len(self.unaccepted_queue),
            "on_fly_blocks": self.num_on_fly_request_block,
            "selected": len(next_batch.requests),
            "selected_prompt_tokens": next_batch.get_num_input_tokens(),
            "forced_oldest": protected_wait >= self.dispatch_timeout_s,
            "scoring_mode": self.scoring_mode,
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
            f"avg_sched_ms={avg_sched_ms:.3f}, forced_oldest={self.num_oldest_forced}"
        )


def get_context_stage_scheduler(
    sched_config: ContextStageSchedConfig,
    parallel_config: ParallelConfig,
    block_manager: BlockManager
) -> ContextStageScheduler:
    if sched_config.policy == "fcfs":
        return ContextStageFCFSScheduler(sched_config, parallel_config, block_manager)
    elif sched_config.policy in ["cost-compatible", "cost-compatible-prefill", "phase"]:
        return ContextStageCostCompatibleScheduler(sched_config, parallel_config, block_manager)
    else:
        raise NotImplementedError(f"Unknown context scheduler policy {sched_config.policy}")
    
