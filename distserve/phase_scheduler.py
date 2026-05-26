import json
import math
import os
import time
from dataclasses import asdict, dataclass
from typing import Dict, Optional


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def ratio(value: float, target: float) -> float:
    if target <= 0:
        return 0.0
    return clamp(value / target)


@dataclass
class AdmissionBudget:
    mode: str
    rho_down: float
    prefill_token_budget: int
    prefill_block_margin: int
    prefer_small_kv_footprint: bool
    decode_swap_budget_per_iter: int
    decode_scan_limit: int
    allow_protected_oldest: bool
    pressures: Dict[str, float]


class PressureBudgetController:
    """Lightweight pressure-to-budget controller for PhaseServe experiments."""

    def __init__(
        self,
        component: str,
        max_prefill_tokens: int = 0,
        max_prefill_block_margin: int = 0,
        max_decode_scan: int = 0,
        max_decode_swap_budget: int = 0,
    ):
        self.component = component
        self.rho_low = _env_float("PHASESERVE_PBC_RHO_LOW", 0.55)
        self.rho_high = _env_float("PHASESERVE_PBC_RHO_HIGH", 0.75)
        self.smooth_lambda = _env_float("PHASESERVE_PBC_SMOOTH_LAMBDA", 0.8)
        self.aggregation = os.environ.get("PHASESERVE_PBC_AGG", "max")
        self.weights = [
            _env_float("PHASESERVE_PBC_W_BRIDGE", 1.0),
            _env_float("PHASESERVE_PBC_W_DECODE", 1.0),
            _env_float("PHASESERVE_PBC_W_KV", 1.0),
            _env_float("PHASESERVE_PBC_W_SWAP", 1.0),
        ]

        self.max_prefill_tokens = max(max_prefill_tokens, 0)
        default_min_prefill = int(self.max_prefill_tokens * _env_float("PHASESERVE_PBC_MIN_PREFILL_FRAC", 0.25))
        self.min_prefill_tokens = _env_int("PHASESERVE_PBC_MIN_PREFILL_TOKENS", default_min_prefill)
        self.max_prefill_block_margin = max_prefill_block_margin
        self.min_prefill_block_margin = _env_int("PHASESERVE_PBC_MIN_BLOCK_MARGIN", 0)

        self.max_decode_scan = max(max_decode_scan, 0)
        self.min_decode_scan = _env_int("PHASESERVE_PBC_MIN_DECODE_SCAN", 1)
        self.max_decode_swap_budget = max(max_decode_swap_budget, 0)
        self.min_decode_swap_budget = _env_int("PHASESERVE_PBC_MIN_SWAP_BUDGET", 0)

        self.previous_mode = "OPEN"
        self.previous_budget: Optional[AdmissionBudget] = None
        self.num_updates = 0
        self.num_mode_switches = 0
        self.last_budget_delta = 0.0

    def _aggregate(self, pressures: Dict[str, float]) -> float:
        values = [
            pressures.get("bridge", 0.0),
            pressures.get("decode", 0.0),
            pressures.get("kv", 0.0),
            pressures.get("swap", 0.0),
        ]
        if self.aggregation == "weighted":
            denom = sum(self.weights) or 1.0
            return clamp(sum(w * v for w, v in zip(self.weights, values)) / denom)
        if self.aggregation == "lexicographic":
            return clamp(max(values[2], values[3], values[0], values[1]))
        return clamp(max(values))

    def _smooth_int(self, previous: int, raw: int) -> int:
        smoothed = self.smooth_lambda * previous + (1.0 - self.smooth_lambda) * raw
        return int(round(smoothed))

    def update(self, pressures: Dict[str, float]) -> AdmissionBudget:
        normalized = {key: clamp(float(value)) for key, value in pressures.items()}
        rho_down = self._aggregate(normalized)
        if rho_down >= self.rho_high:
            mode = "BACKPRESSURE"
        elif rho_down <= self.rho_low:
            mode = "OPEN"
        else:
            mode = self.previous_mode or "BALANCED"

        prefill_raw = int(round(
            self.min_prefill_tokens
            + (1.0 - rho_down) * (self.max_prefill_tokens - self.min_prefill_tokens)
        )) if self.max_prefill_tokens else 0
        block_margin_raw = int(round(
            self.min_prefill_block_margin
            + rho_down * (self.max_prefill_block_margin - self.min_prefill_block_margin)
        )) if self.max_prefill_block_margin else 0
        swap_pressure = normalized.get("swap", 0.0)
        decode_swap_raw = int(round(
            self.min_decode_swap_budget
            + (1.0 - swap_pressure) * (self.max_decode_swap_budget - self.min_decode_swap_budget)
        )) if self.max_decode_swap_budget else 0
        decode_scan_pressure = max(normalized.get("kv", 0.0), normalized.get("swap", 0.0))
        decode_scan_raw = int(round(
            self.min_decode_scan
            + (1.0 - decode_scan_pressure) * (self.max_decode_scan - self.min_decode_scan)
        )) if self.max_decode_scan else 0

        if self.previous_budget is not None:
            prefill_budget = self._smooth_int(self.previous_budget.prefill_token_budget, prefill_raw)
            block_margin = self._smooth_int(self.previous_budget.prefill_block_margin, block_margin_raw)
            decode_swap_budget = self._smooth_int(
                self.previous_budget.decode_swap_budget_per_iter,
                decode_swap_raw,
            )
            decode_scan_limit = self._smooth_int(self.previous_budget.decode_scan_limit, decode_scan_raw)
            self.last_budget_delta = math.sqrt(
                (prefill_budget - self.previous_budget.prefill_token_budget) ** 2
                + (block_margin - self.previous_budget.prefill_block_margin) ** 2
                + (decode_swap_budget - self.previous_budget.decode_swap_budget_per_iter) ** 2
                + (decode_scan_limit - self.previous_budget.decode_scan_limit) ** 2
            )
        else:
            prefill_budget = prefill_raw
            block_margin = block_margin_raw
            decode_swap_budget = decode_swap_raw
            decode_scan_limit = decode_scan_raw
            self.last_budget_delta = 0.0

        if mode != self.previous_mode:
            self.num_mode_switches += 1

        budget = AdmissionBudget(
            mode=mode,
            rho_down=rho_down,
            prefill_token_budget=max(prefill_budget, 0),
            prefill_block_margin=max(block_margin, 0),
            prefer_small_kv_footprint=mode == "BACKPRESSURE",
            decode_swap_budget_per_iter=max(decode_swap_budget, 0),
            decode_scan_limit=max(decode_scan_limit, 1) if self.max_decode_scan else 0,
            allow_protected_oldest=normalized.get("age", 0.0) >= 1.0,
            pressures=normalized,
        )
        self.previous_budget = budget
        self.previous_mode = mode
        self.num_updates += 1
        return budget

    def metrics(self) -> Dict[str, float]:
        return {
            "num_updates": self.num_updates,
            "num_mode_switches": self.num_mode_switches,
            "mode_switch_rate": self.num_mode_switches / max(self.num_updates, 1),
            "last_budget_delta": self.last_budget_delta,
        }


def append_phase_metric(component: str, event: str, payload: Dict) -> None:
    metrics_path = os.environ.get("PHASESERVE_METRICS_PATH")
    if not metrics_path:
        return
    record = {
        "timestamp": time.time(),
        "component": component,
        "event": event,
        "pid": os.getpid(),
    }
    record.update(payload)
    if "budget" in record and hasattr(record["budget"], "__dataclass_fields__"):
        record["budget"] = asdict(record["budget"])
    try:
        with open(metrics_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
    except Exception:
        pass
