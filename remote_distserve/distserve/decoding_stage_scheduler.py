from abc import ABC, abstractmethod
import copy
import math
import os
import time
from typing import List, Callable, Tuple
import warnings
import torch

from distserve.config import ParallelConfig, DecodingStageSchedConfig
from distserve.logger import init_logger
from distserve.request import Request, BatchedRequests, MigratingRequest
from distserve.profiling import ProfilingDatabase
from distserve.block_manager import BlockManager, BlockLocation
from distserve.phase_scheduler import (
    PressureBudgetController,
    append_phase_metric,
    clamp,
    ratio,
    write_pressure_snapshot,
)

logger = init_logger(__name__)


class DecodingStageScheduler(ABC):
    """The abstract class for a decoding stage scheduler.
    It should maintain all the requests in the current systems and their
    runtime statistics which are needed for scheduling. Before each iteration
    begins, the LLMEngine will call get_next_batch() method to get a
    BatchedRequets object for the next iteration. After each iteration ends,
    the LLMEngine will call the pop_finished_requests() method to get the
    finished requests in the current iteration.
    """
    
    @abstractmethod
    def add_request(self, request: MigratingRequest) -> None:
        """
        Add a request to the scheduler.
        NOTE. The scheduler may choose to migrate the request proactively to
        improve the performance.
        """
        raise NotImplementedError()

    @abstractmethod
    def abort_request(self, request_id: int) -> None:
        """
        Abort a request from the scheduler.
        """
        raise NotImplementedError()

    @abstractmethod
    def get_next_batch(self) -> BatchedRequests:
        """
        Get a batch of requests for the execution of next iteration.
        """
        raise NotImplementedError()

    @abstractmethod
    def pop_finished_requests(self) -> List[Request]:
        """
        Pop the finished requests from the scheduler.
        """
        raise NotImplementedError()

    @abstractmethod
    def get_total_num_requests(self) -> int:
        """
        Get the total number of requests in the system.
        """
        raise NotImplementedError()

    @abstractmethod
    def get_processing_num_requests(self) -> int:
        """
        Get the number of requests that are being processed.
        """
        raise NotImplementedError()

    @abstractmethod
    def get_waiting_num_requests(self) -> int:
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
    
    async def post_process(self) -> None:
        """
        Post process after each iteration.
        """
        pass


class DecodingStageFCFSScheduler(DecodingStageScheduler):
    """A first-come-first-serve scheduler.
    Note: It supports pipeline parallelism. It maintains #pp disjoint batches which
    are in the pipeline under execution.
    Note: The requests are in waiting_queue or the batch_queues, and one request
    can only be in one queue at a time.
    """

    def __init__(
        self,
        sched_config: DecodingStageSchedConfig,
        parallel_config: ParallelConfig,
        block_manager: BlockManager,
        engine_migrate_block_callback: Callable,
    ):
        assert sched_config.policy in [
            "fcfs",
            "pure-las",
            "kv-unaware-las",
            "kv-aware-las",
            "kv-aware-las-decode",
            "phase",
        ], f"can not initialize a decoding scheduler with policy {sched_config.policy}"
        self.sched_config = sched_config
        # If the request has not been accepted (i.e. it still resides in the "bridge" queu
        # and its block are still on the context stage engine's side), then it will be put
        # into the unaccepted queue.
        self.unaccepted_queue: List[MigratingRequest] = []
        # If the current batch is full, the requests will be put into the waiting queue.
        self.waiting_queue: List[Request] = []
        # If one request was in batch_queues before, but swapped out, it will be put into the swapped queue.
        self.swapped_queue: List[Request] = []
        # Since pipeline parallelism is used, there are multiple batches in the system.
        self.cur_index = -1
        self.batch_queues = [
            BatchedRequests() for i in range(parallel_config.pipeline_parallel_size)
        ]
        self.parallel_config = copy.deepcopy(parallel_config)
        self.block_manager = block_manager
        self.engine_migrate_block_callback = engine_migrate_block_callback

    def _get_block_needed(self, length: int):
        block_size = self.block_manager.cache_config.block_size
        return (length + block_size - 1) // block_size
        
    def _check_add_to_cur_batch(self, request: Request) -> bool:
        return (
            len(self.batch_queues[self.cur_index]) < self.sched_config.max_batch_size
        ) and (
            self.batch_queues[self.cur_index].get_num_input_tokens()
            + request.get_num_input_tokens()
            <= self.sched_config.max_tokens_per_batch
        ) and (
            sum([
                sum([
                    self._get_block_needed(len(req.prompt_token_ids) + req.get_output_len())
                    for req in self.batch_queues[index].requests
                ])
                for index in range(self.parallel_config.pipeline_parallel_size)
            ]) + sum([
                self._get_block_needed(len(req.prompt_token_ids))
                for req in self.waiting_queue
            ]) + self._get_block_needed(request.get_input_len() + request.get_output_len()) \
                <= self.block_manager.max_num_gpu_blocks
        )

    # Requests-related methods
    async def add_request(self, migrating_req: MigratingRequest) -> None:
        # We take a simple approach here: Accept any request that comes in.
        self.unaccepted_queue.append(migrating_req)

    def abort_request(self, request_id: int) -> None:
        # scan the current batch
        for queue in self.batch_queues:
            for _, request in enumerate(queue.requests):
                if request.request_id == request_id:
                    # This request may be under processed by the model currently,
                    # so it is not safe to delete it from current batch directly.
                    # Mark it as finished will release the resources it holds finally.
                    request.is_finished = True
                    return

        # scan the waiting queue
        for i, request in enumerate(self.waiting_queue):
            if request.request_id == request_id:
                del self.waiting_queue[i]
                return

    def _get_last_stage_batch(self) -> BatchedRequests:
        last_stage_index = (
            self.cur_index + 1
        ) % self.parallel_config.pipeline_parallel_size
        return self.batch_queues[last_stage_index]

    def pop_finished_requests(self) -> List[Request]:
        return self._get_last_stage_batch().pop_finished_requests()

    def get_next_batch(self) -> BatchedRequests:
        self.cur_index = (
            self.cur_index + 1
        ) % self.parallel_config.pipeline_parallel_size

        # Check whether the blocks on GPU is enough for the next batch.
        # If not, swap out the last request
        while sum([
            sum([
                self._get_block_needed(req.get_input_len() + req.get_output_len())
                for req in self.batch_queues[index].requests
            ])
            for index in range(self.parallel_config.pipeline_parallel_size)
        ]) + sum([
            self._get_block_needed(req.get_input_len())
            for req in self.waiting_queue
        ]) > self.block_manager.max_num_gpu_blocks:
            logger.info("No enough GPU blocks. Swap-out triggered")
            request = self.batch_queues[self.cur_index].requests.pop(-1)
            self.swapped_queue.append(request)
            self.block_manager.swap_out_requests([request])

        # Try to add in some new requests. Consider requests in the swapped queue first.
        while len(self.swapped_queue) > 0 or len(self.waiting_queue) > 0:
            if len(self.swapped_queue) > 0:
                request = self.swapped_queue[0]
                if self._check_add_to_cur_batch(request):
                    logger.info("Swap-in triggered")
                    self.block_manager.swap_in_requests([request])
                    self.batch_queues[self.cur_index].add_request(request)
                    self.swapped_queue.pop(0)
                else:
                    break
            else:
                request = self.waiting_queue[0]
                if self._check_add_to_cur_batch(request):
                    self.batch_queues[self.cur_index].add_request(request)
                    self.waiting_queue.pop(0)
                else:
                    break
        return self.batch_queues[self.cur_index]

    # Getter functions
    def get_total_num_requests(self) -> int:
        return self.get_processing_num_requests() + self.get_waiting_num_requests()

    def get_processing_num_requests(self) -> int:
        num = 0
        for batch in self.batch_queues:
            num = num + len(batch.requests)
        return num

    def get_waiting_num_requests(self) -> int:
        return len(self.waiting_queue)

    def __repr__(self) -> str:
        return (
            f"FCFS(max_batch_size={self.sched_config.max_batch_size}, "
            f"max_tokens_per_batch={self.sched_config.max_tokens_per_batch})"
        )
    
    def print_status(self) -> None:
        logger.info(f"(decoding) {len(self.unaccepted_queue)} unaccepted, {len(self.waiting_queue)} waiting, {self.get_processing_num_requests()} processing")

    async def post_process(self) -> None:
        def should_accept(migrating_req: MigratingRequest) -> bool:
            return sum([self._get_block_needed(len(req.prompt_token_ids))
                        for req in self.waiting_queue
                    ]) < self.block_manager.max_num_gpu_blocks * self.sched_config.waiting_block_prop_threshold \
                    and self._get_block_needed(len(migrating_req.req.prompt_token_ids)) <= self.block_manager.get_num_avail_gpu_blocks()
        while len(self.unaccepted_queue) > 0:
            migrating_req = self.unaccepted_queue[0]
            if should_accept(migrating_req):
                self.unaccepted_queue.pop(0)
                await self.engine_migrate_block_callback(migrating_req)
                self.waiting_queue.append(migrating_req.req)
            else:
                break


class DecodingStageKVAwareLASScheduler(DecodingStageFCFSScheduler):
    """
    KV-aware least-attained-service decode scheduler.

    This minimal PS-Decode implementation targets the 1p1d experimental setup.
    It rebuilds the active decode batch at iteration boundaries, prioritizing
    requests with fewer generated tokens while preferring GPU-resident KV state
    inside the same attained-service level. A skip counter provides a bounded
    fairness signal for requests repeatedly bypassed by the scheduler.
    """

    def __init__(
        self,
        sched_config: DecodingStageSchedConfig,
        parallel_config: ParallelConfig,
        block_manager: BlockManager,
        engine_migrate_block_callback: Callable,
    ):
        assert sched_config.policy in [
            "pure-las",
            "kv-unaware-las",
            "kv-aware-las",
            "kv-aware-las-decode",
            "phase",
        ], f"can not initialize a KV-aware LAS scheduler with policy {sched_config.policy}"
        super().__init__(
            sched_config,
            parallel_config,
            block_manager,
            engine_migrate_block_callback,
        )
        self.skip_threshold = int(os.environ.get("PHASESERVE_DECODE_SKIP_THRESHOLD", "8"))
        self.max_level = int(os.environ.get("PHASESERVE_DECODE_MAX_LEVEL", "16"))
        self.scan_multiplier = int(os.environ.get("PHASESERVE_DECODE_SCAN_MULT", "4"))
        self.max_swap_ins_per_iter = int(os.environ.get("PHASESERVE_DECODE_MAX_SWAPINS", "1"))
        self.max_swap_bytes_per_iter = int(os.environ.get("PHASESERVE_DECODE_SWAP_BUDGET_BYTES", "0"))
        self.policy_variant = sched_config.policy
        self.use_starved_tiebreak = self.policy_variant != "pure-las"
        self.use_resident_preference = self.policy_variant not in {"pure-las", "kv-unaware-las"}
        self.use_swap_budget = self.policy_variant not in {"pure-las", "kv-unaware-las"}
        default_starved_primary = "1" if self.use_starved_tiebreak else "0"
        self.use_starved_primary = os.environ.get(
            "PHASESERVE_DECODE_STARVED_PRIMARY",
            default_starved_primary,
        ).lower() in {"1", "true", "yes", "on"}
        default_handoff_debt = "0"
        self.use_handoff_debt = os.environ.get(
            "PHASESERVE_KAS_HANDOFF_DEBT",
            default_handoff_debt,
        ).lower() in {"1", "true", "yes", "on"}
        default_adaptive_intensity = "1" if self.policy_variant == "phase" else "0"
        self.use_adaptive_intensity = os.environ.get(
            "PHASESERVE_KAS_ADAPTIVE_INTENSITY",
            default_adaptive_intensity,
        ).lower() in {"1", "true", "yes", "on"}
        default_relaxed_acceptance = "1" if self.policy_variant == "phase" else "0"
        self.use_pbc_relaxed_acceptance = os.environ.get(
            "PHASESERVE_KAS_PBC_RELAXED_ACCEPTANCE",
            default_relaxed_acceptance,
        ).lower() in {"1", "true", "yes", "on"}
        self.kas_intensity_low = float(os.environ.get(
            "PHASESERVE_KAS_INTENSITY_LOW",
            "0.45",
        ))
        self.kas_intensity_high = float(os.environ.get(
            "PHASESERVE_KAS_INTENSITY_HIGH",
            "0.75",
        ))
        self.kas_intensity_bridge_discount = float(os.environ.get(
            "PHASESERVE_KAS_INTENSITY_BRIDGE_DISCOUNT",
            "0.25",
        ))
        self.kas_intensity_resident_threshold = float(os.environ.get(
            "PHASESERVE_KAS_INTENSITY_RESIDENT_THRESHOLD",
            "0.50",
        ))
        self.fcfs_fallback_intensity_threshold = float(os.environ.get(
            "PHASESERVE_KAS_FCFS_FALLBACK_INTENSITY",
            "0.0",
        ))
        self.short_output_fcfs_threshold = int(os.environ.get(
            "PHASESERVE_KAS_SHORT_OUTPUT_FCFS_THRESHOLD",
            "96" if self.policy_variant == "phase" else "0",
        ))
        self.long_output_full_kas_threshold = int(os.environ.get(
            "PHASESERVE_KAS_LONG_OUTPUT_FULL_THRESHOLD",
            "512" if self.policy_variant == "phase" else "0",
        ))
        default_long_output_requires_decode = "0"
        self.long_output_full_requires_decode_pressure = os.environ.get(
            "PHASESERVE_KAS_LONG_OUTPUT_FULL_REQUIRES_DECODE_PRESSURE",
            default_long_output_requires_decode,
        ).lower() in {"1", "true", "yes", "on"}
        self.long_output_full_decode_pressure_threshold = float(os.environ.get(
            "PHASESERVE_KAS_LONG_OUTPUT_FULL_DECODE_PRESSURE",
            "0.75",
        ))
        self.bridge_fcfs_fallback_threshold = float(os.environ.get(
            "PHASESERVE_KAS_BRIDGE_FCFS_FALLBACK_PRESSURE",
            "0.0",
        ))
        default_bridge_eviction = "0"
        self.use_bridge_eviction = os.environ.get(
            "PHASESERVE_KAS_BRIDGE_EVICTION",
            default_bridge_eviction,
        ).lower() in {"1", "true", "yes", "on"}
        self.bridge_eviction_pressure_threshold = float(os.environ.get(
            "PHASESERVE_KAS_BRIDGE_EVICTION_PRESSURE",
            "0.50",
        ))
        default_bridge_eviction_decode = "1" if self.policy_variant == "phase" else "0"
        self.bridge_eviction_allow_decode_heavy = os.environ.get(
            "PHASESERVE_KAS_BRIDGE_EVICTION_ALLOW_DECODE_HEAVY",
            default_bridge_eviction_decode,
        ).lower() in {"1", "true", "yes", "on"}
        self.handoff_debt_weight = float(os.environ.get(
            "PHASESERVE_KAS_HANDOFF_DEBT_WEIGHT",
            "1.0",
        ))
        self.handoff_debt_age_target_s = float(os.environ.get(
            "PHASESERVE_KAS_HANDOFF_DEBT_AGE_TARGET_S",
            "0.50",
        ))
        self.handoff_debt_min_pressure = float(os.environ.get(
            "PHASESERVE_KAS_HANDOFF_DEBT_MIN_PRESSURE",
            "0.25",
        ))
        default_workload_gate = "0"
        self.use_workload_gate = os.environ.get(
            "PHASESERVE_KAS_WORKLOAD_GATING",
            default_workload_gate,
        ).lower() in {"1", "true", "yes", "on"}
        self.first_token_gate_threshold = float(os.environ.get(
            "PHASESERVE_KAS_FIRST_TOKEN_GATE_THRESHOLD",
            "0.65",
        ))
        self.first_token_gate_min_count = int(os.environ.get(
            "PHASESERVE_KAS_FIRST_TOKEN_GATE_MIN_COUNT",
            "2",
        ))
        self.first_token_gate_target = float(os.environ.get(
            "PHASESERVE_KAS_FIRST_TOKEN_GATE_TARGET",
            str(max(self.sched_config.max_batch_size, 1)),
        ))
        self.prefill_gate_hard_threshold = float(os.environ.get(
            "PHASESERVE_KAS_PREFILL_GATE_HARD_THRESHOLD",
            "0.25",
        ))
        self.hard_free_block_frac = float(os.environ.get(
            "PHASESERVE_KAS_HARD_FREE_BLOCK_FRAC",
            "0.02",
        ))
        self.max_decode_scan = max(
            self.sched_config.max_batch_size * self.scan_multiplier,
            self.sched_config.max_batch_size,
            1,
        )
        self.pressure_controller = PressureBudgetController(
            component="decode",
            max_decode_scan=self.max_decode_scan,
            max_decode_swap_budget=self.max_swap_ins_per_iter,
        )
        self.bridge_target = float(os.environ.get("PHASESERVE_PBC_BRIDGE_TARGET", "4"))
        self.decode_queue_target = float(os.environ.get(
            "PHASESERVE_PBC_DECODE_QUEUE_TARGET",
            str(max(self.sched_config.max_batch_size * 4, 1))
        ))
        self.decode_token_target = float(os.environ.get(
            "PHASESERVE_PBC_DECODE_TOKEN_TARGET",
            str(max(self.sched_config.max_batch_size * 256, 1))
        ))
        self.decode_token_pressure_weight = float(os.environ.get(
            "PHASESERVE_PBC_DECODE_TOKEN_WEIGHT",
            "0.0" if self.policy_variant == "phase" else "1.0",
        ))
        self.swap_queue_target = float(os.environ.get(
            "PHASESERVE_PBC_SWAP_TARGET",
            str(max(self.max_swap_ins_per_iter * 4, 1))
        ))
        default_bridge_reserve = "0"
        self.use_bridge_reserve = os.environ.get(
            "PHASESERVE_KAS_BRIDGE_RESERVE",
            default_bridge_reserve,
        ).lower() in {"1", "true", "yes", "on"}
        self.bridge_reserve_pressure_threshold = float(os.environ.get(
            "PHASESERVE_KAS_BRIDGE_RESERVE_PRESSURE",
            "0.50",
        ))
        self.bridge_reserve_max_frac = float(os.environ.get(
            "PHASESERVE_KAS_BRIDGE_RESERVE_MAX_FRAC",
            "0.10",
        ))
        self.bridge_reserve_max_requests = int(os.environ.get(
            "PHASESERVE_KAS_BRIDGE_RESERVE_MAX_REQUESTS",
            "1",
        ))
        default_bridge_waiting_block_prop = (
            "0.20"
            if self.policy_variant == "phase"
            else str(self.sched_config.waiting_block_prop_threshold)
        )
        self.bridge_waiting_block_prop_threshold = float(os.environ.get(
            "PHASESERVE_KAS_BRIDGE_WAITING_BLOCK_PROP",
            default_bridge_waiting_block_prop,
        ))
        self.bridge_waiting_pressure_threshold = float(os.environ.get(
            "PHASESERVE_KAS_BRIDGE_WAITING_PRESSURE",
            "0.50",
        ))
        self.bridge_waiting_max_requests = int(os.environ.get(
            "PHASESERVE_KAS_BRIDGE_WAITING_MAX_REQUESTS",
            str(max(self.sched_config.max_batch_size, 1)) if self.policy_variant == "phase" else "0",
        ))
        default_bridge_hol = "0"
        self.use_bridge_hol_bypass = os.environ.get(
            "PHASESERVE_KAS_BRIDGE_HOL_BYPASS",
            default_bridge_hol,
        ).lower() in {"1", "true", "yes", "on"}
        self.bridge_hol_scan_limit = int(os.environ.get(
            "PHASESERVE_KAS_BRIDGE_HOL_SCAN",
            str(max(self.sched_config.max_batch_size * 2, 1)),
        ))
        self.bridge_hol_short_prompt_blocks = int(os.environ.get(
            "PHASESERVE_KAS_BRIDGE_HOL_SHORT_BLOCKS",
            "48",
        ))
        self.bridge_hol_extra_block_prop = float(os.environ.get(
            "PHASESERVE_KAS_BRIDGE_HOL_EXTRA_BLOCK_PROP",
            "0.05",
        ))
        default_short_output_bridge = "1" if self.policy_variant == "phase" else "0"
        self.use_bridge_short_output_fastlane = os.environ.get(
            "PHASESERVE_KAS_BRIDGE_SHORT_OUTPUT_FASTLANE",
            default_short_output_bridge,
        ).lower() in {"1", "true", "yes", "on"}
        self.bridge_short_output_threshold = int(os.environ.get(
            "PHASESERVE_KAS_BRIDGE_SHORT_OUTPUT_THRESHOLD",
            "128",
        ))
        self.bridge_short_output_extra_block_prop = float(os.environ.get(
            "PHASESERVE_KAS_BRIDGE_SHORT_OUTPUT_EXTRA_BLOCK_PROP",
            "0.05" if self.policy_variant == "phase" else "0.05",
        ))
        default_fastlane_guard = "1" if self.policy_variant == "phase" else "0"
        self.use_bridge_fastlane_guard = os.environ.get(
            "PHASESERVE_KAS_BRIDGE_FASTLANE_GUARD",
            default_fastlane_guard,
        ).lower() in {"1", "true", "yes", "on"}
        self.bridge_fastlane_guard_prompt_tokens = int(os.environ.get(
            "PHASESERVE_KAS_BRIDGE_FASTLANE_GUARD_PROMPT_TOKENS",
            "1024",
        ))
        self.bridge_fastlane_guard_wait_s = float(os.environ.get(
            "PHASESERVE_KAS_BRIDGE_FASTLANE_GUARD_WAIT_S",
            "12.0" if self.policy_variant == "phase" else "20.0",
        ))
        self.bridge_fastlane_guard_pressure = float(os.environ.get(
            "PHASESERVE_KAS_BRIDGE_FASTLANE_GUARD_PRESSURE",
            "0.0",
        ))
        default_bridge_completion_drain = "1" if self.policy_variant == "phase" else "0"
        self.use_bridge_completion_drain = os.environ.get(
            "PHASESERVE_KAS_BRIDGE_COMPLETION_DRAIN",
            default_bridge_completion_drain,
        ).lower() in {"1", "true", "yes", "on"}
        self.bridge_completion_pressure_threshold = float(os.environ.get(
            "PHASESERVE_KAS_BRIDGE_COMPLETION_PRESSURE",
            "0.0",
        ))
        self.bridge_completion_remaining_threshold = int(os.environ.get(
            "PHASESERVE_KAS_BRIDGE_COMPLETION_REMAINING",
            "0",
        ))
        self.bridge_completion_first_decode_frac = float(os.environ.get(
            "PHASESERVE_KAS_BRIDGE_COMPLETION_FIRST_DECODE_FRAC",
            "1.0",
        ))
        self.bridge_completion_first_decode_min = int(os.environ.get(
            "PHASESERVE_KAS_BRIDGE_COMPLETION_FIRST_DECODE_MIN",
            "1",
        ))
        self.append_block_margin = int(os.environ.get("PHASESERVE_DECODE_APPEND_BLOCK_MARGIN", "0"))
        self.current_budget = None

        self.consecutive_skips = {}
        self.consecutive_infeasible = {}
        self.num_iterations = 0
        self.total_sched_time_s = 0.0
        self.total_selected = 0
        self.total_starved_selected = 0
        self.total_starved_ready = 0
        self.total_policy_skipped = 0
        self.total_infeasible_rounds = 0
        self.total_swap_ins = 0
        self.total_swap_in_bytes = 0
        self.total_iteration_stall_s = 0.0
        self.total_resident_selected = 0
        self.total_evictions = 0

        if self.parallel_config.pipeline_parallel_size != 1:
            logger.warning(
                "DecodingStageKVAwareLASScheduler is intended for pp=1. "
                "Falling back to FCFS behavior for pipeline-parallel decode."
            )

    def _is_resident(self, request: Request) -> bool:
        return self.block_manager.get_location(request.request_id) == BlockLocation.GPU

    def _get_attained_level(self, request: Request) -> int:
        output_len = max(request.get_output_len(), 0)
        if output_len <= 0:
            return 0
        return min(output_len.bit_length(), self.max_level)

    def _is_starved(self, request: Request) -> bool:
        return self.consecutive_skips.get(request.request_id, 0) >= self.skip_threshold

    def _is_first_decode_step(self, request: Request) -> bool:
        return getattr(request, "phaseserve_decode_steps", 0) <= 0

    def _handoff_debt_discount(
        self,
        request: Request,
        prefill_gate: dict = None,
        now_s: float = None,
        budget = None,
    ) -> float:
        if (
            not self.use_handoff_debt
            or not self._is_first_decode_step(request)
            or prefill_gate is None
        ):
            return 0.0
        budget_weight = getattr(budget, "ttft_debt_weight", None)
        if budget_weight is None:
            budget_weight = 1.0
        budget_weight = clamp(float(budget_weight))
        if budget_weight <= 0.0:
            return 0.0
        hard_pressure = max(float(prefill_gate.get("decode_hard_pressure", 0.0)), 0.0)
        hard_scale = max(1.0 - hard_pressure, 0.0)
        if hard_scale <= 0.0:
            return 0.0
        first_token_pressure = float(prefill_gate.get("first_token_pressure", 0.0))
        bridge_pressure = float(prefill_gate.get("bridge_pressure", 0.0))
        debt_pressure = max(
            min(max(first_token_pressure, bridge_pressure), 1.0),
            self.handoff_debt_min_pressure,
        )
        if now_s is None:
            now_s = time.perf_counter()
        ready_time = getattr(request, "phaseserve_decode_ready_time", request.arrival_time)
        age_pressure = ratio(max(now_s - ready_time, 0.0), self.handoff_debt_age_target_s)
        age_scale = 0.5 + 0.5 * age_pressure
        return self.handoff_debt_weight * budget_weight * debt_pressure * age_scale * hard_scale

    def _kas_intensity(self, budget, prefill_gate: dict = None) -> float:
        if not self.use_adaptive_intensity or budget is None or prefill_gate is None:
            return 1.0
        budget_intensity = getattr(budget, "decode_utility_intensity", None)
        if budget_intensity is not None:
            return clamp(float(budget_intensity))
        hard_pressure = max(float(prefill_gate.get("decode_hard_pressure", 0.0)), 0.0)
        if hard_pressure >= self.prefill_gate_hard_threshold:
            return 1.0
        decode_pressure = max(float(getattr(budget, "pressure_decode", 0.0)), 0.0)
        swap_pressure = max(float(getattr(budget, "pressure_swap", 0.0)), 0.0)
        local_decode_pressure = max(decode_pressure, swap_pressure)
        denom = max(self.kas_intensity_high - self.kas_intensity_low, 1e-6)
        pressure_intensity = clamp(
            (local_decode_pressure - self.kas_intensity_low) / denom
        )
        bridge_pressure = max(
            float(prefill_gate.get("first_token_pressure", 0.0)),
            float(prefill_gate.get("bridge_pressure", 0.0)),
        )
        bridge_scale = max(
            1.0 - self.kas_intensity_bridge_discount * clamp(bridge_pressure),
            0.0,
        )
        return clamp(max(hard_pressure, pressure_intensity * bridge_scale))

    def _target_output_len(self, request: Request) -> int:
        sampling_params = getattr(request, "sampling_params", None)
        return int(getattr(sampling_params, "max_tokens", request.get_output_len()) or 0)

    def _remaining_output_len(self, request: Request) -> int:
        return max(self._target_output_len(request) - request.get_output_len(), 0)

    def _avg_target_output_len(self, ready_requests: List[Request]) -> float:
        if not ready_requests:
            return 0.0
        return sum(self._target_output_len(request) for request in ready_requests) / len(ready_requests)

    def _output_token_backlog(self, ready_requests: List[Request]) -> int:
        return sum(self._remaining_output_len(request) for request in ready_requests)

    def _use_long_output_full_kas(self, ready_requests: List[Request]) -> bool:
        return (
            self.policy_variant == "phase"
            and self.long_output_full_kas_threshold > 0
            and self._avg_target_output_len(ready_requests) > self.long_output_full_kas_threshold
        )

    def _long_output_full_kas_allowed(
        self,
        budget,
        prefill_gate: dict = None,
    ) -> bool:
        if not self.long_output_full_requires_decode_pressure:
            return True
        hard_pressure = 0.0
        if prefill_gate is not None:
            hard_pressure = float(prefill_gate.get("decode_hard_pressure", 0.0))
        if hard_pressure >= self.prefill_gate_hard_threshold:
            return True
        regime = getattr(budget, "regime", None)
        if regime in {"DECODE_HEAVY", "KV_SWAP_LIMITED"}:
            return True
        decode_pressure = max(
            float(getattr(budget, "pressure_decode", 0.0) or 0.0),
            float(getattr(budget, "pressure_swap", 0.0) or 0.0),
        )
        return decode_pressure >= self.long_output_full_decode_pressure_threshold

    def _request_kas_intensity(
        self,
        request: Request,
        kas_intensity: float,
        prefill_gate: dict = None,
        budget = None,
    ) -> float:
        if self.policy_variant != "phase":
            return kas_intensity
        hard_pressure = 0.0
        if prefill_gate is not None:
            hard_pressure = float(prefill_gate.get("decode_hard_pressure", 0.0))
        if hard_pressure >= self.prefill_gate_hard_threshold:
            return 1.0
        target_output_len = self._target_output_len(request)
        if (
            self.short_output_fcfs_threshold > 0
            and target_output_len <= self.short_output_fcfs_threshold
        ):
            return 0.0
        if (
            self.long_output_full_kas_threshold > 0
            and target_output_len > self.long_output_full_kas_threshold
            and self._long_output_full_kas_allowed(budget, prefill_gate)
        ):
            return 1.0
        return kas_intensity

    def _use_fcfs_fallback(
        self,
        budget,
        prefill_gate: dict,
        kas_intensity: float,
        ready_requests: List[Request],
    ) -> bool:
        if self.policy_variant != "phase" or budget is None or prefill_gate is None:
            return False
        if float(prefill_gate.get("decode_hard_pressure", 0.0)) >= self.prefill_gate_hard_threshold:
            return False
        if (
            self.short_output_fcfs_threshold > 0
            and self._avg_target_output_len(ready_requests) <= self.short_output_fcfs_threshold
        ):
            return True
        if self.fcfs_fallback_intensity_threshold <= 0.0:
            bridge_pressure = max(
                float(prefill_gate.get("bridge_pressure", 0.0)),
                float(prefill_gate.get("first_token_pressure", 0.0)),
            )
            decode_pressure = max(
                float(getattr(budget, "pressure_decode", 0.0) or 0.0),
                float(getattr(budget, "pressure_swap", 0.0) or 0.0),
            )
            return (
                self.bridge_fcfs_fallback_threshold > 0.0
                and bridge_pressure >= self.bridge_fcfs_fallback_threshold
                and decode_pressure < self.long_output_full_decode_pressure_threshold
                and getattr(budget, "regime", None) in {"FIRST_TOKEN_LIMITED", "MIXED_SLO"}
            )
        if getattr(budget, "regime", None) not in {"FIRST_TOKEN_LIMITED", "MIXED_SLO"}:
            return False
        return kas_intensity <= self.fcfs_fallback_intensity_threshold

    def _bridge_dominant_safe(self, budget) -> bool:
        if budget is None:
            return False
        bridge_pressure = max(
            float(getattr(budget, "pressure_bridge", 0.0) or 0.0),
            float(getattr(budget, "pressure_first", 0.0) or 0.0),
        )
        if bridge_pressure < self.bridge_waiting_pressure_threshold:
            return False
        hard_pressure = float(getattr(budget, "pressure_decode_hard", 0.0) or 0.0)
        if hard_pressure >= self.prefill_gate_hard_threshold:
            return False
        decode_pressure = max(
            float(getattr(budget, "pressure_decode", 0.0) or 0.0),
            float(getattr(budget, "pressure_swap", 0.0) or 0.0),
        )
        return bridge_pressure >= decode_pressure

    def _bridge_fastlane_guard_state(self, budget=None, now_s: float = None) -> dict:
        if now_s is None:
            now_s = time.perf_counter()
        long_prompt_wait_s = 0.0
        long_prompt_count = 0
        max_prompt_tokens = 0
        for migrating_req in self.unaccepted_queue:
            request = migrating_req.req
            prompt_tokens = len(request.prompt_token_ids)
            max_prompt_tokens = max(max_prompt_tokens, prompt_tokens)
            if prompt_tokens < self.bridge_fastlane_guard_prompt_tokens:
                continue
            long_prompt_count += 1
            enqueue_time = getattr(
                request,
                "phaseserve_context_enqueue_time",
                request.arrival_time,
            )
            long_prompt_wait_s = max(long_prompt_wait_s, max(now_s - enqueue_time, 0.0))

        bridge_pressure = 0.0
        if budget is not None:
            bridge_pressure = max(
                float(getattr(budget, "pressure_bridge", 0.0) or 0.0),
                float(getattr(budget, "pressure_first", 0.0) or 0.0),
            )
        pressure_ok = (
            self.bridge_fastlane_guard_pressure <= 0.0
            or bridge_pressure >= self.bridge_fastlane_guard_pressure
        )
        active = (
            self.use_bridge_fastlane_guard
            and long_prompt_count > 0
            and long_prompt_wait_s >= self.bridge_fastlane_guard_wait_s
            and pressure_ok
        )
        return {
            "active": active,
            "enabled": self.use_bridge_fastlane_guard,
            "long_prompt_count": long_prompt_count,
            "long_prompt_wait_s": long_prompt_wait_s,
            "max_prompt_tokens": max_prompt_tokens,
            "prompt_tokens": self.bridge_fastlane_guard_prompt_tokens,
            "wait_s": self.bridge_fastlane_guard_wait_s,
            "pressure": bridge_pressure,
            "pressure_threshold": self.bridge_fastlane_guard_pressure,
        }

    def _use_bridge_completion_drain(self, budget, prefill_gate: dict = None) -> bool:
        if (
            self.policy_variant != "phase"
            or not self.use_bridge_completion_drain
            or budget is None
        ):
            return False
        hard_pressure = float(getattr(budget, "pressure_decode_hard", 0.0) or 0.0)
        if prefill_gate is not None:
            hard_pressure = max(
                hard_pressure,
                float(prefill_gate.get("decode_hard_pressure", 0.0) or 0.0),
            )
        if hard_pressure >= self.prefill_gate_hard_threshold:
            return False
        bridge_pressure = max(
            float(getattr(budget, "pressure_bridge", 0.0) or 0.0),
            float(getattr(budget, "pressure_first", 0.0) or 0.0),
        )
        if prefill_gate is not None:
            bridge_pressure = max(
                bridge_pressure,
                float(prefill_gate.get("bridge_pressure", 0.0) or 0.0),
                float(prefill_gate.get("first_token_pressure", 0.0) or 0.0),
            )
        return bridge_pressure >= self.bridge_completion_pressure_threshold

    def _use_pbc_relaxed_acceptance(self, budget) -> bool:
        if (
            self.policy_variant != "phase"
            or not self.use_pbc_relaxed_acceptance
            or budget is None
        ):
            return False
        if getattr(budget, "regime", None) not in {"FIRST_TOKEN_LIMITED", "MIXED_SLO"}:
            return False
        return float(getattr(budget, "pressure_decode_hard", 0.0)) < self.prefill_gate_hard_threshold

    def _ready_sort_key(
        self,
        request: Request,
        prefill_gate_active: bool = False,
        prefill_gate: dict = None,
        now_s: float = None,
        kas_intensity: float = 1.0,
        budget = None,
        fcfs_fallback: bool = False,
    ):
        if fcfs_fallback:
            return (
                getattr(request, "phaseserve_decode_ready_time", request.arrival_time),
                request.request_id,
            )
        if prefill_gate_active:
            return (
                not self._is_first_decode_step(request),
                getattr(request, "phaseserve_decode_ready_time", request.arrival_time),
                request.request_id,
            )
        if self._use_bridge_completion_drain(budget, prefill_gate):
            remaining_output = self._remaining_output_len(request)
            allocated_blocks = self.block_manager.get_allocated_num_blocks(request.request_id)
            is_starved = self._is_starved(request)
            starved_primary_key = (
                not is_starved
                if self.use_starved_tiebreak and self.use_starved_primary
                else False
            )
            short_remaining_key = (
                remaining_output > self.bridge_completion_remaining_threshold
                if self.bridge_completion_remaining_threshold > 0
                else False
            )
            return (
                starved_primary_key,
                not self._is_first_decode_step(request),
                not self._is_resident(request),
                short_remaining_key,
                remaining_output,
                -allocated_blocks,
                getattr(request, "phaseserve_decode_ready_time", request.arrival_time),
                request.request_id,
            )
        is_starved = self._is_starved(request)
        starved_key = not is_starved if self.use_starved_tiebreak else False
        starved_primary_key = (
            not is_starved
            if self.use_starved_tiebreak and self.use_starved_primary
            else False
        )
        attained_level = self._get_attained_level(request)
        request_kas_intensity = self._request_kas_intensity(
            request,
            kas_intensity,
            prefill_gate,
            budget,
        )
        handoff_debt_discount = self._handoff_debt_discount(
            request,
            prefill_gate=prefill_gate,
            now_s=now_s,
            budget=budget,
        )
        resident_preference_enabled = (
            self.use_resident_preference
            and request_kas_intensity >= self.kas_intensity_resident_threshold
        )
        resident_key = not self._is_resident(request) if resident_preference_enabled else False
        return (
            starved_primary_key,
            attained_level * request_kas_intensity - handoff_debt_discount,
            starved_key,
            resident_key,
            getattr(request, "phaseserve_decode_ready_time", request.arrival_time),
            request.request_id,
        )

    def _bridge_completion_first_decode_quota(self) -> int:
        if self.bridge_completion_first_decode_frac >= 1.0:
            return max(self.sched_config.max_batch_size, 1)
        raw_quota = int(math.ceil(
            max(self.sched_config.max_batch_size, 1)
            * max(self.bridge_completion_first_decode_frac, 0.0)
        ))
        return min(
            max(raw_quota, max(self.bridge_completion_first_decode_min, 0)),
            max(self.sched_config.max_batch_size, 1),
        )

    def _ordered_ready_requests(
        self,
        ready_requests: List[Request],
        prefill_gate_active: bool,
        prefill_gate: dict,
        now_s: float,
        kas_intensity: float,
        budget,
        fcfs_fallback_active: bool,
        bridge_completion_drain_active: bool,
    ) -> List[Request]:
        sort_key = lambda request: self._ready_sort_key(
            request,
            prefill_gate_active,
            prefill_gate,
            now_s,
            kas_intensity,
            budget,
            fcfs_fallback_active,
        )
        if (
            not bridge_completion_drain_active
            or self.bridge_completion_first_decode_frac >= 1.0
        ):
            return sorted(ready_requests, key=sort_key)

        first_decode = [
            request for request in ready_requests
            if self._is_first_decode_step(request)
        ]
        non_first_decode = [
            request for request in ready_requests
            if not self._is_first_decode_step(request)
        ]
        first_decode.sort(key=sort_key)
        non_first_decode.sort(key=sort_key)
        first_quota = self._bridge_completion_first_decode_quota()
        return (
            first_decode[:first_quota]
            + non_first_decode
            + first_decode[first_quota:]
        )

    def _decode_hard_pressure(self) -> Tuple[float, float, float]:
        max_gpu_blocks = max(float(self.block_manager.max_num_gpu_blocks), 1.0)
        hard_free_target = max(max_gpu_blocks * self.hard_free_block_frac, 1.0)
        available_gpu_blocks = float(self.block_manager.get_num_avail_gpu_blocks())
        kv_hard = ratio(max(hard_free_target - available_gpu_blocks, 0.0), hard_free_target)
        swap_hard = ratio(len(self.swapped_queue), self.swap_queue_target)
        return max(kv_hard, swap_hard), kv_hard, swap_hard

    def _prefill_gate_state(self, ready_requests: List[Request]) -> Tuple[bool, dict]:
        first_token_ready = sum(
            1 for request in ready_requests
            if self._is_first_decode_step(request)
        )
        hard_pressure, kv_hard, swap_hard = self._decode_hard_pressure()
        first_token_pressure = ratio(first_token_ready, self.first_token_gate_target)
        bridge_pressure = ratio(len(self.unaccepted_queue), self.bridge_target)
        gate_pressure = max(first_token_pressure, bridge_pressure)
        active = (
            self.use_workload_gate
            and first_token_ready >= self.first_token_gate_min_count
            and gate_pressure >= self.first_token_gate_threshold
            and hard_pressure <= self.prefill_gate_hard_threshold
        )
        return active, {
            "active": active,
            "first_token_ready": first_token_ready,
            "first_token_pressure": first_token_pressure,
            "bridge_pressure": bridge_pressure,
            "gate_pressure": gate_pressure,
            "decode_hard_pressure": hard_pressure,
            "decode_kv_hard": kv_hard,
            "decode_swap_hard": swap_hard,
        }

    def _dedup_ready_requests(self, requests: List[Request]) -> List[Request]:
        seen = set()
        deduped = []
        for request in requests:
            if request.request_id in seen or request.is_finished:
                continue
            seen.add(request.request_id)
            deduped.append(request)
        return deduped

    def _estimate_kv_bytes(self, request: Request) -> int:
        blocks = self.block_manager.get_allocated_num_blocks(request.request_id)
        hidden_size = self.block_manager.model_config.get_hidden_size()
        dtype_size = self.block_manager.model_config.get_dtype_size()
        num_layers = getattr(
            self.block_manager.model_config.hf_config,
            "num_hidden_layers",
            getattr(self.block_manager.model_config.hf_config, "n_layer", 1),
        )
        # key + value cache.
        return int(blocks * self.block_manager.cache_config.block_size * hidden_size * num_layers * 2 * dtype_size)

    def _get_decode_budget(self, ready_requests: List[Request] = None):
        waiting_ready = len(self.waiting_queue) + len(self.swapped_queue)
        kv_used = self.block_manager.max_num_gpu_blocks - self.block_manager.get_num_avail_gpu_blocks()
        swapping_blocks = (
            len(getattr(self.block_manager, "swapping_cpu_blocks_list", []))
            + len(getattr(self.block_manager, "swapping_gpu_blocks_list", []))
        )
        max_skip = max(self.consecutive_skips.values(), default=0)
        ready_requests = ready_requests or []
        first_token_ready = sum(
            1 for request in ready_requests
            if self._is_first_decode_step(request)
        )
        hard_pressure, kv_hard, swap_hard = self._decode_hard_pressure()
        decode_queue_pressure = ratio(waiting_ready, self.decode_queue_target)
        decode_token_backlog = self._output_token_backlog(ready_requests)
        decode_token_pressure = clamp(
            ratio(decode_token_backlog, self.decode_token_target)
            * max(self.decode_token_pressure_weight, 0.0)
        )
        decode_pressure = max(decode_queue_pressure, decode_token_pressure)
        pressures = {
            "bridge": ratio(len(self.unaccepted_queue), self.bridge_target),
            "first": ratio(first_token_ready, self.first_token_gate_target),
            "decode": decode_pressure,
            "decode_queue": decode_queue_pressure,
            "decode_tokens": decode_token_pressure,
            "kv": ratio(kv_used, max(self.block_manager.max_num_gpu_blocks, 1)),
            "swap": max(
                ratio(len(self.swapped_queue), self.swap_queue_target),
                ratio(swapping_blocks, max(self.block_manager.max_num_gpu_blocks, 1)),
            ),
            "decode_hard": hard_pressure,
            "kv_hard": kv_hard,
            "age": ratio(max_skip, self.skip_threshold),
        }
        self.current_budget = self.pressure_controller.update(pressures)
        write_pressure_snapshot(
            "decode",
            pressures,
            self.current_budget,
            extra={
                "unaccepted": len(self.unaccepted_queue),
                "waiting": len(self.waiting_queue),
                "swapped": len(self.swapped_queue),
                "first_token_ready": first_token_ready,
                "decode_queue_pressure": decode_queue_pressure,
                "decode_token_backlog": decode_token_backlog,
                "decode_token_pressure": decode_token_pressure,
                "decode_token_target": self.decode_token_target,
                "decode_token_pressure_weight": self.decode_token_pressure_weight,
                "processing": self.get_processing_num_requests(),
                "available_gpu_blocks": self.block_manager.get_num_avail_gpu_blocks(),
                "max_gpu_blocks": self.block_manager.max_num_gpu_blocks,
                "decode_hard_pressure": hard_pressure,
                "decode_kv_hard": kv_hard,
                "decode_swap_hard": swap_hard,
            },
        )
        return self.current_budget

    def _get_swap_byte_budget(self, budget) -> int:
        if self.max_swap_bytes_per_iter <= 0:
            return 0
        if budget is None or self.max_swap_ins_per_iter <= 0:
            return self.max_swap_bytes_per_iter
        budget_ratio = budget.decode_swap_budget_per_iter / max(self.max_swap_ins_per_iter, 1)
        return max(int(round(self.max_swap_bytes_per_iter * budget_ratio)), 0)

    def _estimate_append_blocks_needed(self, request: Request) -> int:
        allocated_blocks = self.block_manager.get_allocated_num_blocks(request.request_id)
        future_len = request.get_input_len() + request.get_output_len() + 1
        block_size = self.block_manager.cache_config.block_size
        next_token_blocks = (future_len + block_size - 1) // block_size
        return max(next_token_blocks - allocated_blocks, self.append_block_margin, 0)

    def _get_append_blocks_needed_safe(self, request: Request) -> int:
        if self.block_manager.get_location(request.request_id) != BlockLocation.GPU:
            return 0
        return max(
            self.block_manager.get_num_append_blocks_needed(request),
            self._estimate_append_blocks_needed(request),
        )

    def _bridge_reserve_blocks(self, budget) -> int:
        if not self.use_bridge_reserve or budget is None or not self.unaccepted_queue:
            return 0
        pressure = max(
            float(getattr(budget, "pressure_bridge", 0.0) or 0.0),
            float(getattr(budget, "pressure_first", 0.0) or 0.0),
        )
        if pressure < self.bridge_reserve_pressure_threshold:
            return 0
        hard_pressure = float(getattr(budget, "pressure_decode_hard", 0.0) or 0.0)
        if hard_pressure >= self.prefill_gate_hard_threshold:
            return 0
        reserve_requests = max(self.bridge_reserve_max_requests, 1)
        prompt_blocks = [
            self._get_block_needed(len(migrating_req.req.prompt_token_ids))
            for migrating_req in self.unaccepted_queue[:reserve_requests]
        ]
        if not prompt_blocks:
            return 0
        pressure_span = max(1.0 - self.bridge_reserve_pressure_threshold, 1e-6)
        pressure_scale = clamp((pressure - self.bridge_reserve_pressure_threshold) / pressure_span)
        raw_reserve = int(math.ceil(max(prompt_blocks) * pressure_scale))
        max_reserve = int(math.ceil(
            self.block_manager.max_num_gpu_blocks * max(self.bridge_reserve_max_frac, 0.0)
        ))
        return max(min(raw_reserve, max_reserve), 0)

    def _available_gpu_blocks_for_decode(self, budget) -> int:
        return max(
            self.block_manager.get_num_avail_gpu_blocks() - self._bridge_reserve_blocks(budget),
            0,
        )

    def _check_add_to_las_batch(
        self,
        batch: BatchedRequests,
        request: Request,
        swap_ins_used: int,
        swap_bytes_used: int,
        budget,
    ) -> Tuple[bool, str]:
        if len(batch) >= self.sched_config.max_batch_size:
            return False, "batch_size"
        if batch.get_num_input_tokens() + request.get_num_input_tokens() > self.sched_config.max_tokens_per_batch:
            return False, "token_budget"

        selected_append_needed = sum([
            self._get_append_blocks_needed_safe(req)
            for req in batch.requests
            if self._is_resident(req)
        ])
        available_decode_blocks = self._available_gpu_blocks_for_decode(budget)
        if self._is_resident(request):
            append_needed = self._get_append_blocks_needed_safe(request)
            if append_needed + selected_append_needed <= available_decode_blocks:
                return True, "ok"
            return False, "gpu_append_blocks"

        swap_budget = (
            budget.decode_swap_budget_per_iter
            if budget is not None
            else self.max_swap_ins_per_iter
        )
        if self.use_swap_budget and swap_ins_used >= swap_budget:
            return False, "swap_budget"
        estimated_swap_bytes = self._estimate_kv_bytes(request)
        swap_byte_budget = self._get_swap_byte_budget(budget)
        if (
            self.use_swap_budget
            and swap_byte_budget > 0
            and swap_bytes_used + estimated_swap_bytes > swap_byte_budget
        ):
            return False, "swap_budget"
        blocks_to_swap_in = self.block_manager.get_allocated_num_blocks(request.request_id)
        append_needed = self._estimate_append_blocks_needed(request)
        if (
            blocks_to_swap_in
            + append_needed
            + selected_append_needed
            <= available_decode_blocks
        ):
            return True, "ok"
        return False, "gpu_swap_blocks"

    def _can_add_to_las_batch(
        self,
        batch: BatchedRequests,
        request: Request,
        swap_ins_used: int,
        swap_bytes_used: int,
        budget,
    ) -> bool:
        can_add, _ = self._check_add_to_las_batch(
            batch,
            request,
            swap_ins_used,
            swap_bytes_used,
            budget,
        )
        return can_add

    def _get_next_batch_fcfs_fallback(
        self,
        ready_requests: List[Request],
        budget,
        prefill_gate: dict,
        kas_intensity: float,
        sched_start: float,
    ) -> BatchedRequests:
        selected_before = list(self.batch_queues[self.cur_index].requests)
        swap_ins_used = 0
        swap_stall_s = 0.0

        while sum([
            sum([
                self._get_block_needed(req.get_input_len() + req.get_output_len())
                for req in self.batch_queues[index].requests
            ])
            for index in range(self.parallel_config.pipeline_parallel_size)
        ]) + sum([
            self._get_block_needed(req.get_input_len())
            for req in self.waiting_queue
        ]) > self.block_manager.max_num_gpu_blocks:
            if len(self.batch_queues[self.cur_index].requests) == 0:
                break
            request = self.batch_queues[self.cur_index].requests.pop(-1)
            self.swapped_queue.append(request)
            self.block_manager.swap_out_requests([request])

        while len(self.swapped_queue) > 0 or len(self.waiting_queue) > 0:
            if len(self.swapped_queue) > 0:
                request = self.swapped_queue[0]
                if self._check_add_to_cur_batch(request):
                    swap_start = time.perf_counter()
                    self.block_manager.swap_in_requests([request])
                    swap_stall_s += time.perf_counter() - swap_start
                    self.batch_queues[self.cur_index].add_request(request)
                    self.swapped_queue.pop(0)
                    swap_ins_used += 1
                else:
                    break
            else:
                request = self.waiting_queue[0]
                if self._check_add_to_cur_batch(request):
                    self.batch_queues[self.cur_index].add_request(request)
                    self.waiting_queue.pop(0)
                else:
                    break

        selected_requests = list(self.batch_queues[self.cur_index].requests)
        selected_ids = {request.request_id for request in selected_requests}
        first_token_selected = sum(
            1 for request in selected_requests
            if self._is_first_decode_step(request)
        )
        for request in selected_requests:
            request.phaseserve_decode_steps = getattr(
                request,
                "phaseserve_decode_steps",
                0,
            ) + 1
            self.consecutive_skips[request.request_id] = 0
            self.consecutive_infeasible[request.request_id] = 0
        policy_skipped = sum(
            1 for request in ready_requests
            if request.request_id not in selected_ids
            and not request.is_finished
        )
        starved_ready = sum(1 for request in ready_requests if self._is_starved(request))
        selected_starved = sum(1 for request in selected_requests if self._is_starved(request))
        resident_selected = sum(1 for request in selected_requests if self._is_resident(request))

        self.num_iterations += 1
        self.total_sched_time_s += time.perf_counter() - sched_start
        self.total_selected += len(selected_requests)
        self.total_starved_selected += selected_starved
        self.total_starved_ready += starved_ready
        self.total_policy_skipped += policy_skipped
        self.total_swap_ins += swap_ins_used
        self.total_resident_selected += resident_selected
        self.total_iteration_stall_s += swap_stall_s
        pressure_injection_decode_swap = swap_ins_used / max(self.max_swap_ins_per_iter, 1)
        if budget is not None:
            budget.pressure_injection_decode_swap = pressure_injection_decode_swap
        append_phase_metric("decode", "dispatch", {
            "unaccepted": len(self.unaccepted_queue),
            "waiting": len(self.waiting_queue),
            "swapped": len(self.swapped_queue),
            "ready": len(ready_requests),
            "considered": len(ready_requests),
            "selected": len(selected_requests),
            "policy_skipped": policy_skipped,
            "infeasible_rounds": 0,
            "resident_selected": resident_selected,
            "resident_admission_ratio": resident_selected / max(len(selected_requests), 1),
            "starved_ready": starved_ready,
            "starved_selected": selected_starved,
            "starved_admission_ratio": selected_starved / max(starved_ready, 1),
            "starved_primary": self.use_starved_primary,
            "first_token_ready": prefill_gate["first_token_ready"],
            "first_token_selected": first_token_selected,
            "first_token_admission_ratio": (
                first_token_selected / max(prefill_gate["first_token_ready"], 1)
            ),
            "handoff_debt_ready": 0,
            "handoff_debt_selected": 0,
            "handoff_debt_admission_ratio": None,
            "handoff_debt_discount_mean": None,
            "handoff_debt_selected_discount_mean": None,
            "handoff_debt_weight": 0.0,
            "budget_ttft_debt_weight": getattr(budget, "ttft_debt_weight", None),
            "effective_handoff_debt_weight": 0.0,
            "handoff_debt_pressure": max(
                prefill_gate["first_token_pressure"],
                prefill_gate["bridge_pressure"],
            ),
            "kas_intensity": kas_intensity,
            "fcfs_fallback_active": True,
            "fcfs_fallback_preserved_active": len(selected_before),
            "fcfs_fallback_intensity_threshold": self.fcfs_fallback_intensity_threshold,
            "short_output_fcfs_threshold": self.short_output_fcfs_threshold,
            "long_output_full_kas_threshold": self.long_output_full_kas_threshold,
            "long_output_full_requires_decode_pressure": self.long_output_full_requires_decode_pressure,
            "long_output_full_decode_pressure_threshold": self.long_output_full_decode_pressure_threshold,
            "bridge_fcfs_fallback_threshold": self.bridge_fcfs_fallback_threshold,
            "avg_target_output_len": self._avg_target_output_len(ready_requests),
            "kas_adaptive_intensity": self.use_adaptive_intensity,
            "budget_regime": getattr(budget, "regime", None),
            "budget_decode_utility_intensity": getattr(budget, "decode_utility_intensity", None),
            "prefill_gate_active": prefill_gate["active"],
            "prefill_gate_pressure": prefill_gate["gate_pressure"],
            "prefill_gate_first_token_pressure": prefill_gate["first_token_pressure"],
            "prefill_gate_bridge_pressure": prefill_gate["bridge_pressure"],
            "prefill_gate_decode_hard_pressure": prefill_gate["decode_hard_pressure"],
            "prefill_gate_decode_kv_hard": prefill_gate["decode_kv_hard"],
            "prefill_gate_decode_swap_hard": prefill_gate["decode_swap_hard"],
            "swap_ins": swap_ins_used,
            "swap_in_bytes": 0,
            "swap_byte_budget": self._get_swap_byte_budget(budget),
            "pressure_injection_decode_swap": pressure_injection_decode_swap,
            "policy_variant": self.policy_variant,
            "iteration_stall_s": swap_stall_s,
            "eviction_count": 0,
            "max_consecutive_skips": max(self.consecutive_skips.values(), default=0),
            "max_consecutive_infeasible": max(self.consecutive_infeasible.values(), default=0),
            "scan_limit": self.sched_config.max_batch_size,
            "sched_time_s": time.perf_counter() - sched_start,
            "budget": budget,
            "controller": self.pressure_controller.metrics(),
        })
        return self.batch_queues[self.cur_index]

    def _evict_resident_requests_for_blocks(
        self,
        ready_requests: List[Request],
        protected_ids: set,
        min_free_blocks: int,
    ) -> int:
        """Swap out low-priority resident requests to make decode progress possible."""
        evicted = 0
        if min_free_blocks <= self.block_manager.get_num_avail_gpu_blocks():
            return evicted

        candidates = [
            request for request in ready_requests
            if request.request_id not in protected_ids
            and not request.is_finished
            and self.block_manager.get_location(request.request_id) == BlockLocation.GPU
        ]
        candidates.sort(key=self._ready_sort_key, reverse=True)

        for request in candidates:
            blocks = self.block_manager.get_allocated_num_blocks(request.request_id)
            if blocks > self.block_manager.get_num_avail_cpu_blocks():
                continue
            logger.info("KV-aware LAS swap-out triggered")
            self.block_manager.swap_out_requests([request])
            evicted += 1
            self.total_evictions += 1
            if self.block_manager.get_num_avail_gpu_blocks() >= min_free_blocks:
                break
        return evicted

    def _requeue_unselected_requests(
        self,
        ready_requests: List[Request],
        selected_ids: set,
        infeasible_ids: set,
    ):
        self.waiting_queue = []
        self.swapped_queue = []
        for request in ready_requests:
            if request.request_id in selected_ids or request.is_finished:
                continue
            if request.request_id in infeasible_ids:
                self.consecutive_infeasible[request.request_id] = (
                    self.consecutive_infeasible.get(request.request_id, 0) + 1
                )
            else:
                self.consecutive_skips[request.request_id] = (
                    self.consecutive_skips.get(request.request_id, 0) + 1
                )
                self.consecutive_infeasible[request.request_id] = 0
            if self.block_manager.get_location(request.request_id) == BlockLocation.CPU:
                self.swapped_queue.append(request)
            else:
                self.waiting_queue.append(request)

    def get_next_batch(self) -> BatchedRequests:
        if self.parallel_config.pipeline_parallel_size != 1:
            return super().get_next_batch()

        sched_start = time.perf_counter()
        self.cur_index = 0

        ready_requests = self._dedup_ready_requests(
            self.batch_queues[self.cur_index].requests
            + self.waiting_queue
            + self.swapped_queue
        )

        if not ready_requests:
            self._get_decode_budget([])
            self.num_iterations += 1
            self.total_sched_time_s += time.perf_counter() - sched_start
            return self.batch_queues[self.cur_index]

        budget = self._get_decode_budget(ready_requests)
        bridge_reserve_blocks = self._bridge_reserve_blocks(budget)
        bridge_reserve_evictions = 0
        if bridge_reserve_blocks > self.block_manager.get_num_avail_gpu_blocks():
            bridge_reserve_evictions = self._evict_resident_requests_for_blocks(
                ready_requests,
                protected_ids=set(),
                min_free_blocks=bridge_reserve_blocks,
            )
        prefill_gate_active, prefill_gate = self._prefill_gate_state(ready_requests)
        kas_intensity = self._kas_intensity(budget, prefill_gate)
        bridge_completion_drain_active = self._use_bridge_completion_drain(budget, prefill_gate)
        fcfs_fallback_active = self._use_fcfs_fallback(
            budget,
            prefill_gate,
            kas_intensity,
            ready_requests,
        )
        if fcfs_fallback_active:
            return self._get_next_batch_fcfs_fallback(
                ready_requests,
                budget,
                prefill_gate,
                kas_intensity,
                sched_start,
            )
        self.batch_queues[self.cur_index] = BatchedRequests()
        sort_now_s = time.perf_counter()
        handoff_debt_discounts = {
            request.request_id: self._handoff_debt_discount(
                request,
                prefill_gate=prefill_gate,
                now_s=sort_now_s,
                budget=budget,
            )
            for request in ready_requests
        }
        handoff_debt_ready = sum(
            1 for discount in handoff_debt_discounts.values()
            if discount > 0.0
        )
        handoff_debt_discount_mean = (
            sum(handoff_debt_discounts.values()) / max(handoff_debt_ready, 1)
        )
        ordered_requests = self._ordered_ready_requests(
            ready_requests,
            prefill_gate_active,
            prefill_gate,
            sort_now_s,
            kas_intensity,
            budget,
            fcfs_fallback_active,
            bridge_completion_drain_active,
        )
        scan_limit = budget.decode_scan_limit if budget.decode_scan_limit > 0 else self.max_decode_scan
        swap_byte_budget = self._get_swap_byte_budget(budget)

        selected_ids = set()
        swap_ins_used = 0
        swap_in_bytes = 0
        swap_stall_s = 0.0
        resident_selected = 0
        selected_starved = 0
        eviction_count = 0
        considered_ids = set()
        infeasible_ids = set()
        infeasible_reasons = {}
        starved_ready = sum(1 for request in ready_requests if self._is_starved(request))
        first_token_selected = 0
        selected_effective_kas_intensities = []
        for request in ordered_requests[:scan_limit]:
            considered_ids.add(request.request_id)
            was_resident = self._is_resident(request)
            can_add, infeasible_reason = self._check_add_to_las_batch(
                self.batch_queues[self.cur_index], request, swap_ins_used, swap_in_bytes, budget
            )
            if not can_add and was_resident:
                append_needed = self._get_append_blocks_needed_safe(request)
                selected_append_needed = sum([
                    self._get_append_blocks_needed_safe(req)
                    for req in self.batch_queues[self.cur_index].requests
                    if self._is_resident(req)
                ])
                min_free_blocks = append_needed + selected_append_needed
                protected_ids = set(selected_ids)
                protected_ids.add(request.request_id)
                eviction_count += self._evict_resident_requests_for_blocks(
                    ready_requests,
                    protected_ids,
                    min_free_blocks,
                )
                can_add, infeasible_reason = self._check_add_to_las_batch(
                    self.batch_queues[self.cur_index], request, swap_ins_used, swap_in_bytes, budget
                )
            if can_add:
                if not self._is_resident(request):
                    logger.info("KV-aware LAS swap-in triggered")
                    estimated_bytes = self._estimate_kv_bytes(request)
                    swap_start = time.perf_counter()
                    self.block_manager.swap_in_requests([request])
                    swap_stall_s += time.perf_counter() - swap_start
                    swap_in_bytes += estimated_bytes
                    swap_ins_used += 1
                    self.total_swap_ins += 1
                    self.total_swap_in_bytes += estimated_bytes
                elif was_resident:
                    resident_selected += 1
                if self._is_starved(request):
                    selected_starved += 1
                if self._is_first_decode_step(request):
                    first_token_selected += 1
                selected_effective_kas_intensities.append(
                    self._request_kas_intensity(
                        request,
                        kas_intensity,
                        prefill_gate,
                        budget,
                    )
                )
                self.batch_queues[self.cur_index].add_request(request)
                request.phaseserve_decode_steps = getattr(
                    request,
                    "phaseserve_decode_steps",
                    0,
                ) + 1
                selected_ids.add(request.request_id)
                self.consecutive_skips[request.request_id] = 0
                self.consecutive_infeasible[request.request_id] = 0
                if len(self.batch_queues[self.cur_index]) >= self.sched_config.max_batch_size:
                    break
            else:
                infeasible_ids.add(request.request_id)
                infeasible_reasons[infeasible_reason] = (
                    infeasible_reasons.get(infeasible_reason, 0) + 1
                )

        self._requeue_unselected_requests(ready_requests, selected_ids, infeasible_ids)
        policy_skipped = sum(
            1 for request in ready_requests
            if request.request_id not in selected_ids
            and request.request_id not in infeasible_ids
            and not request.is_finished
        )
        infeasible_rounds = len(infeasible_ids)
        selected_handoff_debt = sum(
            1 for request_id in selected_ids
            if handoff_debt_discounts.get(request_id, 0.0) > 0.0
        )
        selected_handoff_discount = sum(
            handoff_debt_discounts.get(request_id, 0.0)
            for request_id in selected_ids
        )

        self.num_iterations += 1
        self.total_sched_time_s += time.perf_counter() - sched_start
        self.total_selected += len(selected_ids)
        self.total_starved_selected += selected_starved
        self.total_starved_ready += starved_ready
        self.total_policy_skipped += policy_skipped
        self.total_infeasible_rounds += infeasible_rounds
        self.total_resident_selected += resident_selected
        self.total_iteration_stall_s += swap_stall_s
        pressure_injection_decode_swap = (
            swap_in_bytes / swap_byte_budget
            if swap_byte_budget > 0
            else swap_ins_used / max(self.max_swap_ins_per_iter, 1)
        )
        if budget is not None:
            budget.pressure_injection_decode_swap = pressure_injection_decode_swap
        append_phase_metric("decode", "dispatch", {
            "unaccepted": len(self.unaccepted_queue),
            "waiting": len(self.waiting_queue),
            "swapped": len(self.swapped_queue),
            "ready": len(ready_requests),
            "considered": len(considered_ids),
            "selected": len(selected_ids),
            "policy_skipped": policy_skipped,
            "infeasible_rounds": infeasible_rounds,
            "infeasible_batch_size": infeasible_reasons.get("batch_size", 0),
            "infeasible_token_budget": infeasible_reasons.get("token_budget", 0),
            "infeasible_gpu_append_blocks": infeasible_reasons.get("gpu_append_blocks", 0),
            "infeasible_gpu_swap_blocks": infeasible_reasons.get("gpu_swap_blocks", 0),
            "infeasible_swap_budget": infeasible_reasons.get("swap_budget", 0),
            "resident_selected": resident_selected,
            "resident_admission_ratio": resident_selected / max(len(selected_ids), 1),
            "starved_ready": starved_ready,
            "starved_selected": selected_starved,
            "starved_admission_ratio": selected_starved / max(starved_ready, 1),
            "starved_primary": self.use_starved_primary,
            "first_token_ready": prefill_gate["first_token_ready"],
            "first_token_selected": first_token_selected,
            "first_token_admission_ratio": (
                first_token_selected / max(prefill_gate["first_token_ready"], 1)
            ),
            "handoff_debt_ready": handoff_debt_ready,
            "handoff_debt_selected": selected_handoff_debt,
            "handoff_debt_admission_ratio": (
                selected_handoff_debt / max(handoff_debt_ready, 1)
            ),
            "handoff_debt_discount_mean": handoff_debt_discount_mean,
            "handoff_debt_selected_discount_mean": (
                selected_handoff_discount / max(selected_handoff_debt, 1)
            ),
            "handoff_debt_weight": self.handoff_debt_weight if self.use_handoff_debt else 0.0,
            "budget_ttft_debt_weight": getattr(budget, "ttft_debt_weight", None),
            "effective_handoff_debt_weight": (
                self.handoff_debt_weight * getattr(budget, "ttft_debt_weight", 0.0)
                if self.use_handoff_debt
                else 0.0
            ),
            "handoff_debt_pressure": max(
                prefill_gate["first_token_pressure"],
                prefill_gate["bridge_pressure"],
            ),
            "kas_intensity": kas_intensity,
            "selected_effective_kas_intensity_mean": (
                sum(selected_effective_kas_intensities)
                / max(len(selected_effective_kas_intensities), 1)
            ),
            "fcfs_fallback_active": fcfs_fallback_active,
            "fcfs_fallback_intensity_threshold": self.fcfs_fallback_intensity_threshold,
            "short_output_fcfs_threshold": self.short_output_fcfs_threshold,
            "long_output_full_kas_threshold": self.long_output_full_kas_threshold,
            "long_output_full_requires_decode_pressure": self.long_output_full_requires_decode_pressure,
            "long_output_full_decode_pressure_threshold": self.long_output_full_decode_pressure_threshold,
            "bridge_fcfs_fallback_threshold": self.bridge_fcfs_fallback_threshold,
            "bridge_completion_drain_active": bridge_completion_drain_active,
            "bridge_completion_pressure_threshold": self.bridge_completion_pressure_threshold,
            "bridge_completion_remaining_threshold": self.bridge_completion_remaining_threshold,
            "bridge_completion_first_decode_frac": self.bridge_completion_first_decode_frac,
            "bridge_completion_first_decode_quota": (
                self._bridge_completion_first_decode_quota()
                if bridge_completion_drain_active
                else None
            ),
            "avg_target_output_len": self._avg_target_output_len(ready_requests),
            "output_token_backlog": self._output_token_backlog(ready_requests),
            "decode_token_target": self.decode_token_target,
            "decode_token_pressure_weight": self.decode_token_pressure_weight,
            "kas_adaptive_intensity": self.use_adaptive_intensity,
            "budget_regime": getattr(budget, "regime", None),
            "budget_decode_utility_intensity": getattr(budget, "decode_utility_intensity", None),
            "budget_decode_queue_pressure": (
                getattr(budget, "pressures", {}) or {}
            ).get("decode_queue"),
            "budget_decode_token_pressure": (
                getattr(budget, "pressures", {}) or {}
            ).get("decode_tokens"),
            "prefill_gate_active": prefill_gate_active,
            "prefill_gate_pressure": prefill_gate["gate_pressure"],
            "prefill_gate_first_token_pressure": prefill_gate["first_token_pressure"],
            "prefill_gate_bridge_pressure": prefill_gate["bridge_pressure"],
            "prefill_gate_decode_hard_pressure": prefill_gate["decode_hard_pressure"],
            "prefill_gate_decode_kv_hard": prefill_gate["decode_kv_hard"],
            "prefill_gate_decode_swap_hard": prefill_gate["decode_swap_hard"],
            "swap_ins": swap_ins_used,
            "swap_in_bytes": swap_in_bytes,
            "swap_byte_budget": swap_byte_budget,
            "swap_byte_budget_ratio": (
                swap_in_bytes / swap_byte_budget
                if swap_byte_budget > 0
                else None
            ),
            "pressure_injection_decode_swap": pressure_injection_decode_swap,
            "policy_variant": self.policy_variant,
            "iteration_stall_s": swap_stall_s,
            "eviction_count": eviction_count,
            "bridge_reserve_blocks": bridge_reserve_blocks,
            "bridge_reserve_evictions": bridge_reserve_evictions,
            "bridge_reserve_enabled": self.use_bridge_reserve,
            "bridge_reserve_pressure_threshold": self.bridge_reserve_pressure_threshold,
            "max_consecutive_skips": max(self.consecutive_skips.values(), default=0),
            "max_consecutive_infeasible": max(self.consecutive_infeasible.values(), default=0),
            "scan_limit": scan_limit,
            "sched_time_s": time.perf_counter() - sched_start,
            "budget": budget,
            "controller": self.pressure_controller.metrics(),
        })

        return self.batch_queues[self.cur_index]

    def pop_finished_requests(self) -> List[Request]:
        finished = super().pop_finished_requests()
        for request in finished:
            self.consecutive_skips.pop(request.request_id, None)
            self.consecutive_infeasible.pop(request.request_id, None)
        return finished

    async def post_process(self) -> None:
        budget = getattr(self, "current_budget", None)
        relaxed_acceptance = self._use_pbc_relaxed_acceptance(budget)
        bridge_evictions = 0
        now = time.perf_counter()

        def waiting_block_len(req: Request) -> int:
            if relaxed_acceptance:
                return req.get_input_len()
            return req.get_input_len() + req.get_output_len()

        def waiting_block_limit() -> float:
            base_limit = (
                self.block_manager.max_num_gpu_blocks
                * self.sched_config.waiting_block_prop_threshold
            )
            if budget is None:
                return base_limit
            bridge_pressure = max(
                float(getattr(budget, "pressure_bridge", 0.0) or 0.0),
                float(getattr(budget, "pressure_first", 0.0) or 0.0),
            )
            hard_pressure = float(getattr(budget, "pressure_decode_hard", 0.0) or 0.0)
            if (
                relaxed_acceptance
                and bridge_pressure >= self.bridge_waiting_pressure_threshold
                and hard_pressure < self.prefill_gate_hard_threshold
            ):
                bridge_limit = (
                    self.block_manager.max_num_gpu_blocks
                    * self.bridge_waiting_block_prop_threshold
                )
                return max(base_limit, bridge_limit)
            return base_limit

        def waiting_request_limit_ok() -> bool:
            if self.bridge_waiting_max_requests <= 0:
                return True
            if budget is None:
                return True
            bridge_pressure = max(
                float(getattr(budget, "pressure_bridge", 0.0) or 0.0),
                float(getattr(budget, "pressure_first", 0.0) or 0.0),
            )
            if bridge_pressure < self.bridge_waiting_pressure_threshold:
                return True
            return len(self.waiting_queue) < self.bridge_waiting_max_requests

        def maybe_evict_for_bridge(migrating_req: MigratingRequest) -> int:
            if not self.use_bridge_eviction or budget is None:
                return 0
            regime = getattr(budget, "regime", None)
            pressure = max(
                float(getattr(budget, "pressure_bridge", 0.0)),
                float(getattr(budget, "pressure_first", 0.0)),
            )
            if pressure < self.bridge_eviction_pressure_threshold:
                return 0
            hard_pressure = float(getattr(budget, "pressure_decode_hard", 0.0) or 0.0)
            decode_pressure = max(
                float(getattr(budget, "pressure_decode", 0.0) or 0.0),
                float(getattr(budget, "pressure_swap", 0.0) or 0.0),
            )
            bridge_dominant = pressure >= decode_pressure
            bridge_safe_decode_regime = (
                self.bridge_eviction_allow_decode_heavy
                and bridge_dominant
                and hard_pressure < self.prefill_gate_hard_threshold
            )
            if regime not in {"FIRST_TOKEN_LIMITED", "MIXED_SLO"} and not bridge_safe_decode_regime:
                return 0
            prompt_blocks = self._get_block_needed(len(migrating_req.req.prompt_token_ids))
            if prompt_blocks <= self.block_manager.get_num_avail_gpu_blocks():
                return 0
            ready_requests = self._dedup_ready_requests(
                self.batch_queues[self.cur_index].requests
                + self.waiting_queue
                + self.swapped_queue
            )
            return self._evict_resident_requests_for_blocks(
                ready_requests,
                protected_ids=set(),
                min_free_blocks=prompt_blocks,
            )

        def should_accept(migrating_req: MigratingRequest) -> bool:
            nonlocal bridge_evictions
            bridge_evictions += maybe_evict_for_bridge(migrating_req)
            waiting_blocks = sum([
                self._get_block_needed(waiting_block_len(req))
                for req in self.waiting_queue
            ])
            block_limit = waiting_block_limit()
            return waiting_request_limit_ok() \
                and waiting_blocks < block_limit \
                and self._get_block_needed(len(migrating_req.req.prompt_token_ids)) <= self.block_manager.get_num_avail_gpu_blocks()

        def bridge_hol_active() -> bool:
            if not self.use_bridge_hol_bypass or budget is None:
                return False
            return (
                self.use_bridge_hol_bypass
                and (
                    relaxed_acceptance
                    or self._bridge_dominant_safe(budget)
                )
            )

        fastlane_guard = self._bridge_fastlane_guard_state(budget, now_s=now)

        def bridge_fastlane_active() -> bool:
            if not self.use_bridge_short_output_fastlane or budget is None:
                return False
            if fastlane_guard["active"]:
                return False
            return relaxed_acceptance or self._bridge_dominant_safe(budget)

        def should_accept_hol_bypass(migrating_req: MigratingRequest) -> bool:
            if not bridge_hol_active():
                return False
            prompt_blocks = self._get_block_needed(len(migrating_req.req.prompt_token_ids))
            if prompt_blocks > self.bridge_hol_short_prompt_blocks:
                return False
            if prompt_blocks > self.block_manager.get_num_avail_gpu_blocks():
                return False
            if self.bridge_waiting_max_requests > 0 and len(self.waiting_queue) >= self.bridge_waiting_max_requests:
                return False
            waiting_blocks = sum([
                self._get_block_needed(waiting_block_len(req))
                for req in self.waiting_queue
            ])
            base_limit = (
                self.block_manager.max_num_gpu_blocks
                * self.sched_config.waiting_block_prop_threshold
            )
            extra_limit = (
                self.block_manager.max_num_gpu_blocks
                * max(self.bridge_hol_extra_block_prop, 0.0)
            )
            return waiting_blocks + prompt_blocks <= base_limit + extra_limit

        def should_accept_short_output_fastlane(migrating_req: MigratingRequest) -> bool:
            if not bridge_fastlane_active():
                return False
            target_output = self._target_output_len(migrating_req.req)
            if target_output > self.bridge_short_output_threshold:
                return False
            prompt_blocks = self._get_block_needed(len(migrating_req.req.prompt_token_ids))
            if prompt_blocks > self.block_manager.get_num_avail_gpu_blocks():
                return False
            if self.bridge_waiting_max_requests > 0 and len(self.waiting_queue) >= self.bridge_waiting_max_requests:
                return False
            waiting_blocks = sum([
                self._get_block_needed(waiting_block_len(req))
                for req in self.waiting_queue
            ])
            base_limit = (
                self.block_manager.max_num_gpu_blocks
                * self.sched_config.waiting_block_prop_threshold
            )
            extra_limit = (
                self.block_manager.max_num_gpu_blocks
                * max(self.bridge_short_output_extra_block_prop, 0.0)
            )
            return waiting_blocks + prompt_blocks <= base_limit + extra_limit

        def pop_acceptable_unaccepted():
            if not self.unaccepted_queue:
                return None, 0, False
            head = self.unaccepted_queue[0]
            if should_accept(head):
                return self.unaccepted_queue.pop(0), 0, False, False
            if should_accept_short_output_fastlane(head):
                return self.unaccepted_queue.pop(0), 0, False, True
            scan_limit = min(max(self.bridge_hol_scan_limit, 1), len(self.unaccepted_queue))
            for index in range(1, scan_limit):
                migrating_req = self.unaccepted_queue[index]
                if should_accept_short_output_fastlane(migrating_req):
                    return self.unaccepted_queue.pop(index), index, False, True
                if should_accept_hol_bypass(migrating_req):
                    return self.unaccepted_queue.pop(index), index, True, False
            return None, 0, False, False

        while len(self.unaccepted_queue) > 0:
            (
                migrating_req,
                bridge_hol_bypass_index,
                bridge_hol_bypass_used,
                bridge_short_output_fastlane_used,
            ) = pop_acceptable_unaccepted()
            if migrating_req is not None:
                await self.engine_migrate_block_callback(migrating_req)
                migrating_req.req.phaseserve_decode_ready_time = time.perf_counter()
                migrating_req.req.phaseserve_decode_steps = 0
                self.waiting_queue.append(migrating_req.req)
                self.consecutive_skips.setdefault(migrating_req.req.request_id, 0)
                append_phase_metric("decode", "bridge_accept", {
                    "request_id": migrating_req.req.request_id,
                    "unaccepted": len(self.unaccepted_queue),
                    "waiting": len(self.waiting_queue),
                    "avail_gpu_blocks": self.block_manager.get_num_avail_gpu_blocks(),
                    "relaxed_acceptance": relaxed_acceptance,
                    "bridge_evictions": bridge_evictions,
                    "bridge_eviction_enabled": self.use_bridge_eviction,
                    "bridge_eviction_pressure_threshold": self.bridge_eviction_pressure_threshold,
                    "bridge_eviction_allow_decode_heavy": self.bridge_eviction_allow_decode_heavy,
                    "waiting_block_limit": waiting_block_limit(),
                    "bridge_waiting_block_prop_threshold": self.bridge_waiting_block_prop_threshold,
                    "bridge_waiting_pressure_threshold": self.bridge_waiting_pressure_threshold,
                    "bridge_waiting_max_requests": self.bridge_waiting_max_requests,
                    "bridge_hol_bypass_enabled": self.use_bridge_hol_bypass,
                    "bridge_hol_bypass_used": bridge_hol_bypass_used,
                    "bridge_hol_bypass_index": bridge_hol_bypass_index,
                    "bridge_hol_scan_limit": self.bridge_hol_scan_limit,
                    "bridge_hol_short_prompt_blocks": self.bridge_hol_short_prompt_blocks,
                    "bridge_hol_extra_block_prop": self.bridge_hol_extra_block_prop,
                    "bridge_short_output_fastlane_enabled": self.use_bridge_short_output_fastlane,
                    "bridge_short_output_fastlane_used": bridge_short_output_fastlane_used,
                    "bridge_short_output_threshold": self.bridge_short_output_threshold,
                    "bridge_short_output_extra_block_prop": self.bridge_short_output_extra_block_prop,
                    "bridge_fastlane_guard_enabled": fastlane_guard["enabled"],
                    "bridge_fastlane_guard_active": fastlane_guard["active"],
                    "bridge_fastlane_guard_long_prompt_count": fastlane_guard["long_prompt_count"],
                    "bridge_fastlane_guard_long_wait_s": fastlane_guard["long_prompt_wait_s"],
                    "bridge_fastlane_guard_prompt_tokens": fastlane_guard["prompt_tokens"],
                    "bridge_fastlane_guard_wait_s": fastlane_guard["wait_s"],
                    "bridge_fastlane_guard_pressure": fastlane_guard["pressure"],
                    "bridge_fastlane_guard_pressure_threshold": fastlane_guard["pressure_threshold"],
                    "accepted_target_output": self._target_output_len(migrating_req.req),
                    "accepted_prompt_blocks": self._get_block_needed(len(migrating_req.req.prompt_token_ids)),
                    "budget_regime": getattr(budget, "regime", None),
                    "budget_decode_hard_pressure": getattr(budget, "pressure_decode_hard", None),
                })
            else:
                break

    def __repr__(self) -> str:
        return (
            f"KVAwareLAS(max_batch_size={self.sched_config.max_batch_size}, "
            f"max_tokens_per_batch={self.sched_config.max_tokens_per_batch}, "
            f"skip_threshold={self.skip_threshold})"
        )

    def print_status(self) -> None:
        avg_sched_ms = (
            self.total_sched_time_s / max(self.num_iterations, 1) * 1000.0
        )
        logger.info(
            f"(decoding-kv-aware-las) {len(self.unaccepted_queue)} unaccepted, "
            f"{len(self.waiting_queue)} waiting, {len(self.swapped_queue)} swapped, "
            f"{self.get_processing_num_requests()} processing, "
            f"avg_sched_ms={avg_sched_ms:.3f}, selected={self.total_selected}, "
            f"starved_selected={self.total_starved_selected}, "
            f"starved_ready={self.total_starved_ready}, "
            f"policy_skipped={self.total_policy_skipped}, "
            f"infeasible_rounds={self.total_infeasible_rounds}, "
            f"swap_ins={self.total_swap_ins}, "
            f"swap_in_MB={self.total_swap_in_bytes / (1024 * 1024):.2f}, "
            f"stall_s={self.total_iteration_stall_s:.6f}, "
            f"resident_selected={self.total_resident_selected}, "
            f"variant={self.policy_variant}, "
            f"mode_switch_rate={self.pressure_controller.metrics()['mode_switch_rate']:.4f}"
        )
    
def get_decoding_stage_scheduler(
    sched_config: DecodingStageSchedConfig,
    parallel_config: ParallelConfig,
    block_manager: BlockManager,
    engine_migrate_block_callback: Callable,
) -> DecodingStageScheduler:
    if sched_config.policy == "fcfs":
        return DecodingStageFCFSScheduler(sched_config, parallel_config, block_manager, engine_migrate_block_callback)
    elif sched_config.policy in ["pure-las", "kv-unaware-las", "kv-aware-las", "kv-aware-las-decode", "phase"]:
        return DecodingStageKVAwareLASScheduler(sched_config, parallel_config, block_manager, engine_migrate_block_callback)
    else:
        raise NotImplementedError(
            f"scheduler policy {sched_config.policy} is not supported"
        )
        
