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
    ratio,
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
        self.swap_queue_target = float(os.environ.get(
            "PHASESERVE_PBC_SWAP_TARGET",
            str(max(self.max_swap_ins_per_iter * 4, 1))
        ))
        self.current_budget = None

        self.consecutive_skips = {}
        self.num_iterations = 0
        self.total_sched_time_s = 0.0
        self.total_selected = 0
        self.total_starved_selected = 0
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

    def _ready_sort_key(self, request: Request):
        return (
            self._get_attained_level(request),
            not self._is_starved(request),
            not self._is_resident(request),
            getattr(request, "phaseserve_decode_ready_time", request.arrival_time),
            request.request_id,
        )

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

    def _get_decode_budget(self):
        waiting_ready = len(self.waiting_queue) + len(self.swapped_queue)
        kv_used = self.block_manager.max_num_gpu_blocks - self.block_manager.get_num_avail_gpu_blocks()
        swapping_blocks = (
            len(getattr(self.block_manager, "swapping_cpu_blocks_list", []))
            + len(getattr(self.block_manager, "swapping_gpu_blocks_list", []))
        )
        max_skip = max(self.consecutive_skips.values(), default=0)
        pressures = {
            "bridge": ratio(len(self.unaccepted_queue), self.bridge_target),
            "decode": ratio(waiting_ready, self.decode_queue_target),
            "kv": ratio(kv_used, max(self.block_manager.max_num_gpu_blocks, 1)),
            "swap": max(
                ratio(len(self.swapped_queue), self.swap_queue_target),
                ratio(swapping_blocks, max(self.block_manager.max_num_gpu_blocks, 1)),
            ),
            "age": ratio(max_skip, self.skip_threshold),
        }
        self.current_budget = self.pressure_controller.update(pressures)
        return self.current_budget

    def _get_append_blocks_needed_safe(self, request: Request) -> int:
        if self.block_manager.get_location(request.request_id) != BlockLocation.GPU:
            return 0
        return max(self.block_manager.get_num_append_blocks_needed(request), 0)

    def _can_add_to_las_batch(self, batch: BatchedRequests, request: Request, swap_ins_used: int, budget) -> bool:
        if len(batch) >= self.sched_config.max_batch_size:
            return False
        if batch.get_num_input_tokens() + request.get_num_input_tokens() > self.sched_config.max_tokens_per_batch:
            return False

        if self._is_resident(request):
            append_needed = self._get_append_blocks_needed_safe(request)
            selected_append_needed = sum([
                self._get_append_blocks_needed_safe(req)
                for req in batch.requests
                if self._is_resident(req)
            ])
            return append_needed + selected_append_needed <= self.block_manager.get_num_avail_gpu_blocks()

        swap_budget = (
            budget.decode_swap_budget_per_iter
            if budget is not None
            else self.max_swap_ins_per_iter
        )
        if swap_ins_used >= swap_budget:
            return False
        blocks_to_swap_in = self.block_manager.get_allocated_num_blocks(request.request_id)
        return blocks_to_swap_in <= self.block_manager.get_num_avail_gpu_blocks()

    def _requeue_unselected_requests(self, ready_requests: List[Request], selected_ids: set):
        self.waiting_queue = []
        self.swapped_queue = []
        for request in ready_requests:
            if request.request_id in selected_ids or request.is_finished:
                continue
            self.consecutive_skips[request.request_id] = (
                self.consecutive_skips.get(request.request_id, 0) + 1
            )
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
        self.batch_queues[self.cur_index] = BatchedRequests()

        if not ready_requests:
            self.num_iterations += 1
            self.total_sched_time_s += time.perf_counter() - sched_start
            return self.batch_queues[self.cur_index]

        ordered_requests = sorted(ready_requests, key=self._ready_sort_key)
        budget = self._get_decode_budget()
        scan_limit = budget.decode_scan_limit if budget.decode_scan_limit > 0 else self.max_decode_scan

        selected_ids = set()
        swap_ins_used = 0
        swap_in_bytes = 0
        swap_stall_s = 0.0
        resident_selected = 0
        selected_starved = 0
        for request in ordered_requests[:scan_limit]:
            was_resident = self._is_resident(request)
            if self._can_add_to_las_batch(self.batch_queues[self.cur_index], request, swap_ins_used, budget):
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
                self.batch_queues[self.cur_index].add_request(request)
                selected_ids.add(request.request_id)
                self.consecutive_skips[request.request_id] = 0
                if len(self.batch_queues[self.cur_index]) >= self.sched_config.max_batch_size:
                    break

        self._requeue_unselected_requests(ready_requests, selected_ids)

        self.num_iterations += 1
        self.total_sched_time_s += time.perf_counter() - sched_start
        self.total_selected += len(selected_ids)
        self.total_starved_selected += selected_starved
        self.total_resident_selected += resident_selected
        self.total_iteration_stall_s += swap_stall_s
        append_phase_metric("decode", "dispatch", {
            "unaccepted": len(self.unaccepted_queue),
            "waiting": len(self.waiting_queue),
            "swapped": len(self.swapped_queue),
            "ready": len(ready_requests),
            "selected": len(selected_ids),
            "resident_selected": resident_selected,
            "resident_admission_ratio": resident_selected / max(len(selected_ids), 1),
            "starved_selected": selected_starved,
            "swap_ins": swap_ins_used,
            "swap_in_bytes": swap_in_bytes,
            "iteration_stall_s": swap_stall_s,
            "eviction_count": 0,
            "max_consecutive_skips": max(self.consecutive_skips.values(), default=0),
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
        return finished

    async def post_process(self) -> None:
        def should_accept(migrating_req: MigratingRequest) -> bool:
            waiting_blocks = sum([
                self._get_block_needed(req.get_input_len() + req.get_output_len())
                for req in self.waiting_queue
            ])
            return waiting_blocks < self.block_manager.max_num_gpu_blocks * self.sched_config.waiting_block_prop_threshold \
                and self._get_block_needed(len(migrating_req.req.prompt_token_ids)) <= self.block_manager.get_num_avail_gpu_blocks()

        while len(self.unaccepted_queue) > 0:
            migrating_req = self.unaccepted_queue[0]
            if should_accept(migrating_req):
                self.unaccepted_queue.pop(0)
                await self.engine_migrate_block_callback(migrating_req)
                migrating_req.req.phaseserve_decode_ready_time = time.perf_counter()
                self.waiting_queue.append(migrating_req.req)
                self.consecutive_skips.setdefault(migrating_req.req.request_id, 0)
                append_phase_metric("decode", "bridge_accept", {
                    "request_id": migrating_req.req.request_id,
                    "unaccepted": len(self.unaccepted_queue),
                    "waiting": len(self.waiting_queue),
                    "avail_gpu_blocks": self.block_manager.get_num_avail_gpu_blocks(),
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
            f"starved_selected={self.total_starved_selected}, swap_ins={self.total_swap_ins}, "
            f"swap_in_MB={self.total_swap_in_bytes / (1024 * 1024):.2f}, "
            f"stall_s={self.total_iteration_stall_s:.6f}, "
            f"resident_selected={self.total_resident_selected}, "
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
    elif sched_config.policy in ["kv-aware-las", "kv-aware-las-decode", "phase"]:
        return DecodingStageKVAwareLASScheduler(sched_config, parallel_config, block_manager, engine_migrate_block_callback)
    else:
        raise NotImplementedError(
            f"scheduler policy {sched_config.policy} is not supported"
        )
        
