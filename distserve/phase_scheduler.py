import json
import math
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
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


def _json_safe(value):
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, dict):
        return {key: _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(val) for val in value]
    return value


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
    pressure_bridge: float = 0.0
    pressure_decode: float = 0.0
    pressure_kv: float = 0.0
    pressure_swap: float = 0.0
    pressure_age: float = 0.0
    rho_prefill: float = 0.0
    rho_memory: float = 0.0
    rho_swap: float = 0.0
    rho_scan: float = 0.0
    pressure_overshoot: float = 0.0


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
        self.disable_dynamic = os.environ.get(
            "PHASESERVE_PBC_DISABLE_DYNAMIC",
            "0",
        ).lower() in {"1", "true", "yes", "on"}
        self.weights = {
            "bridge": _env_float("PHASESERVE_PBC_W_BRIDGE", 1.0),
            "decode": _env_float("PHASESERVE_PBC_W_DECODE", 1.0),
            "kv": _env_float("PHASESERVE_PBC_W_KV", 1.0),
            "swap": _env_float("PHASESERVE_PBC_W_SWAP", 1.0),
        }

        self.max_prefill_tokens = max(max_prefill_tokens, 0)
        default_min_prefill = int(self.max_prefill_tokens * _env_float("PHASESERVE_PBC_MIN_PREFILL_FRAC", 0.50))
        self.min_prefill_tokens = _env_int("PHASESERVE_PBC_MIN_PREFILL_TOKENS", default_min_prefill)
        self.max_prefill_block_margin = max_prefill_block_margin
        self.min_prefill_block_margin = _env_int("PHASESERVE_PBC_MIN_BLOCK_MARGIN", 0)

        self.max_decode_scan = max(max_decode_scan, 0)
        default_min_decode_scan = int(round(
            self.max_decode_scan * _env_float("PHASESERVE_PBC_MIN_DECODE_SCAN_FRAC", 0.75)
        ))
        self.min_decode_scan = min(
            self.max_decode_scan,
            max(_env_int("PHASESERVE_PBC_MIN_DECODE_SCAN", default_min_decode_scan), 1),
        )
        self.max_decode_swap_budget = max(max_decode_swap_budget, 0)
        self.min_decode_swap_budget = _env_int("PHASESERVE_PBC_MIN_SWAP_BUDGET", 0)

        self.previous_mode = "OPEN"
        self.previous_budget: Optional[AdmissionBudget] = None
        self.num_updates = 0
        self.num_mode_switches = 0
        self.last_budget_delta = 0.0
        self.last_pressure_overshoot = 0.0

    def _aggregate_keys(self, pressures: Dict[str, float], keys) -> float:
        values = [pressures.get(key, 0.0) for key in keys]
        if not values:
            return 0.0
        if self.aggregation == "weighted":
            denom = sum(self.weights.get(key, 1.0) for key in keys) or 1.0
            return clamp(
                sum(self.weights.get(key, 1.0) * value for key, value in zip(keys, values))
                / denom
            )
        if self.aggregation == "lexicographic":
            for key in ["kv", "swap", "bridge", "decode"]:
                if key in keys:
                    return clamp(max(pressures.get(key, 0.0), max(values)))
            return clamp(max(values))
        return clamp(max(values))

    def _aggregate(self, pressures: Dict[str, float]) -> float:
        return self._aggregate_keys(pressures, ["bridge", "decode", "kv", "swap"])

    def _make_budget(
        self,
        mode: str,
        normalized: Dict[str, float],
        rho_down: float,
        rho_prefill: float,
        rho_memory: float,
        rho_swap: float,
        rho_scan: float,
        prefill_token_budget: int,
        prefill_block_margin: int,
        decode_swap_budget_per_iter: int,
        decode_scan_limit: int,
    ) -> AdmissionBudget:
        pressure_overshoot = max(rho_down - self.rho_high, 0.0)
        return AdmissionBudget(
            mode=mode,
            rho_down=rho_down,
            prefill_token_budget=max(prefill_token_budget, 0),
            prefill_block_margin=max(prefill_block_margin, 0),
            prefer_small_kv_footprint=mode == "BACKPRESSURE" or rho_memory >= self.rho_high,
            decode_swap_budget_per_iter=max(decode_swap_budget_per_iter, 0),
            decode_scan_limit=max(decode_scan_limit, 1) if self.max_decode_scan else 0,
            allow_protected_oldest=normalized.get("age", 0.0) >= 1.0,
            pressures=normalized,
            pressure_bridge=normalized.get("bridge", 0.0),
            pressure_decode=normalized.get("decode", 0.0),
            pressure_kv=normalized.get("kv", 0.0),
            pressure_swap=normalized.get("swap", 0.0),
            pressure_age=normalized.get("age", 0.0),
            rho_prefill=rho_prefill,
            rho_memory=rho_memory,
            rho_swap=rho_swap,
            rho_scan=rho_scan,
            pressure_overshoot=pressure_overshoot,
        )

    def _smooth_int(self, previous: int, raw: int) -> int:
        smoothed = self.smooth_lambda * previous + (1.0 - self.smooth_lambda) * raw
        return int(round(smoothed))

    def _static_budget(self, normalized: Dict[str, float]) -> AdmissionBudget:
        mode = "STATIC"
        if mode != self.previous_mode:
            self.num_mode_switches += 1
        rho_down = self._aggregate(normalized)
        budget = self._make_budget(
            mode=mode,
            normalized=normalized,
            rho_down=rho_down,
            rho_prefill=self._aggregate_keys(normalized, ["bridge", "decode"]),
            rho_memory=self._aggregate_keys(normalized, ["kv", "swap"]),
            rho_swap=normalized.get("swap", 0.0),
            rho_scan=self._aggregate_keys(normalized, ["kv", "swap"]),
            prefill_token_budget=self.max_prefill_tokens,
            prefill_block_margin=max(self.min_prefill_block_margin, 0),
            decode_swap_budget_per_iter=max(self.max_decode_swap_budget, 0),
            decode_scan_limit=max(self.max_decode_scan, 1) if self.max_decode_scan else 0,
        )
        budget.prefer_small_kv_footprint = False
        self.previous_budget = budget
        self.previous_mode = mode
        self.num_updates += 1
        self.last_budget_delta = 0.0
        self.last_pressure_overshoot = budget.pressure_overshoot
        return budget

    def update(self, pressures: Dict[str, float]) -> AdmissionBudget:
        normalized = {key: clamp(float(value)) for key, value in pressures.items()}
        if self.disable_dynamic:
            return self._static_budget(normalized)

        rho_down = self._aggregate(normalized)
        rho_prefill = self._aggregate_keys(normalized, ["bridge", "decode"])
        rho_memory = self._aggregate_keys(normalized, ["kv", "swap"])
        rho_swap = normalized.get("swap", 0.0)
        rho_scan = rho_memory
        if rho_down >= self.rho_high:
            mode = "BACKPRESSURE"
        elif rho_down <= self.rho_low:
            mode = "OPEN"
        else:
            mode = self.previous_mode or "BALANCED"

        prefill_raw = int(round(
            self.min_prefill_tokens
            + (1.0 - rho_prefill) * (self.max_prefill_tokens - self.min_prefill_tokens)
        )) if self.max_prefill_tokens else 0
        block_margin_raw = int(round(
            self.min_prefill_block_margin
            + rho_memory * (self.max_prefill_block_margin - self.min_prefill_block_margin)
        )) if self.max_prefill_block_margin else 0
        decode_swap_raw = int(round(
            self.min_decode_swap_budget
            + (1.0 - rho_swap) * (self.max_decode_swap_budget - self.min_decode_swap_budget)
        )) if self.max_decode_swap_budget else 0
        decode_scan_raw = int(round(
            self.min_decode_scan
            + (1.0 - rho_scan) * (self.max_decode_scan - self.min_decode_scan)
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

        budget = self._make_budget(
            mode=mode,
            normalized=normalized,
            rho_down=rho_down,
            rho_prefill=rho_prefill,
            rho_memory=rho_memory,
            rho_swap=rho_swap,
            rho_scan=rho_scan,
            prefill_token_budget=prefill_budget,
            prefill_block_margin=block_margin,
            decode_swap_budget_per_iter=decode_swap_budget,
            decode_scan_limit=decode_scan_limit,
        )
        self.previous_budget = budget
        self.previous_mode = mode
        self.num_updates += 1
        self.last_pressure_overshoot = budget.pressure_overshoot
        return budget

    def metrics(self) -> Dict[str, float]:
        return {
            "num_updates": self.num_updates,
            "num_mode_switches": self.num_mode_switches,
            "mode_switch_rate": self.num_mode_switches / max(self.num_updates, 1),
            "last_budget_delta": self.last_budget_delta,
            "last_pressure_overshoot": self.last_pressure_overshoot,
        }


def write_pressure_snapshot(component: str, pressures: Dict, budget: Optional[AdmissionBudget], extra: Optional[Dict] = None) -> None:
    snapshot_path = os.environ.get("PHASESERVE_PRESSURE_SNAPSHOT_PATH")
    if not snapshot_path:
        return
    record = {
        "timestamp": time.time(),
        "component": component,
        "pid": os.getpid(),
        "pressures": _json_safe(pressures),
        "budget": _json_safe(budget),
    }
    if extra:
        record.update(_json_safe(extra))
    path = Path(snapshot_path)
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
        os.replace(str(tmp_path), str(path))
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


def read_pressure_snapshot(expected_component: Optional[str] = None) -> Optional[Dict]:
    snapshot_path = os.environ.get("PHASESERVE_PRESSURE_SNAPSHOT_PATH")
    if not snapshot_path:
        return None
    path = Path(snapshot_path)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "available": False,
            "path": str(path),
        }
    now = time.time()
    timestamp = float(record.get("timestamp", 0.0) or 0.0)
    max_age_s = _env_float("PHASESERVE_PRESSURE_SNAPSHOT_MAX_AGE_S", 2.0)
    age_s = max(now - timestamp, 0.0) if timestamp > 0 else None
    component = record.get("component")
    stale = age_s is None or age_s > max_age_s
    wrong_component = expected_component is not None and component != expected_component
    record.update({
        "available": True,
        "path": str(path),
        "age_s": age_s,
        "stale": stale,
        "wrong_component": wrong_component,
    })
    return record


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
    record = _json_safe(record)
    try:
        with open(metrics_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
    except Exception:
        pass
