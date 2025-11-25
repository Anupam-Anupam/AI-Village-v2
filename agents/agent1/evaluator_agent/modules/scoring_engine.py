from __future__ import annotations
import json
import logging
from typing import Any, Dict, List, Optional
from decimal import Decimal

# Import LLMInterface for correctness evaluation
try:
    from .llm_interface import LLMInterface
except ImportError:
    LLMInterface = None


DEFAULT_WEIGHTS = {
    "correctness": 0.35,
    "efficiency": 0.15,
    "quality": 0.15,
    "stability": 0.10,
    "autonomy": 0.15,
    "resource_efficiency": 0.10,
}


class ScoringEngine:
    def __init__(
        self, 
        logger: Optional[logging.Logger] = None, 
        weights: Optional[Dict[str, float]] = None,
        llm: Optional[Any] = None
    ) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self.weights = weights or DEFAULT_WEIGHTS
        self.llm = llm  # LLMInterface for correctness evaluation

    def _clip(self, v: float) -> float:
        return max(0.0, min(1.0, v))
    
    def _heuristic_correctness(self, data: Dict[str, Any], error_count: float) -> float:
        """Fallback heuristic correctness calculation."""
        progress = data.get("progress", [])
        progress_ratio = 0.0
        if progress:
            # try to infer completion from status/progress columns
            last = progress[-1]
            status = (str(last.get("status") or "").lower())
            prog = last.get("progress")
            # Accept Decimal or string numeric
            if isinstance(prog, Decimal):
                prog = float(prog)
            elif isinstance(prog, str):
                try:
                    prog = float(prog.strip())
                except Exception:
                    prog = None
            if isinstance(prog, (int, float)):
                progress_ratio = max(0.0, min(1.0, float(prog))) if float(prog) <= 1 else min(1.0, float(prog) / 100.0)
            if "done" in status or "complete" in status or status == "success":
                progress_ratio = max(progress_ratio, 1.0)
        return self._clip(0.9 * progress_ratio + 0.1 * (1.0 / (1.0 + error_count)))

    def score_task(self, data: Dict[str, Any], num_agents: int = 1) -> Dict[str, Any]:
        m = data.get("metrics", {})
        logs: List[Dict[str, Any]] = data.get("logs", [])

        # Heuristic scoring
        error_count = float(m.get("error_count", 0))
        retry_count = float(m.get("retry_count", 0))
        deps = float(m.get("human_or_agent_requests", 0))
        completion_time = float(m.get("completion_time_s", 0.0))
        total_api_calls = float(m.get("total_api_calls", 0))
        mem = float(m.get("memory_usage_mb", 0.0))
        cpu = float(m.get("cpu_usage_percent", 0.0))

        # correctness: compare initial request with final output using LLM
        initial_request = data.get("initial_request", "")
        final_output = data.get("final_output", "")
        task_id = data.get("task_id", "unknown")
        
        # Log data availability for debugging
        has_request = bool(initial_request and initial_request.strip())
        has_output = bool(final_output and final_output.strip())
        has_llm = bool(self.llm)
        
        self.logger.info(json.dumps({
            "event": "correctness_evaluation_start",
            "task_id": task_id,
            "has_initial_request": has_request,
            "has_final_output": has_output,
            "has_llm": has_llm,
            "request_length": len(initial_request) if initial_request else 0,
            "output_length": len(final_output) if final_output else 0,
            "request_preview": initial_request[:100] + "..." if initial_request and len(initial_request) > 100 else (initial_request or ""),
            "output_preview": final_output[:100] + "..." if final_output and len(final_output) > 100 else (final_output or "")
        }))
        
        if self.llm and has_request and has_output:
            # Use LLM to evaluate correctness by comparing request vs output
            try:
                correctness = self.llm.evaluate_correctness(initial_request, final_output)
                self.logger.info(json.dumps({
                    "event": "correctness_evaluated",
                    "task_id": task_id,
                    "correctness": correctness,
                    "method": "llm"
                }))
            except Exception as e:
                self.logger.warning(json.dumps({
                    "event": "correctness_evaluation_error",
                    "task_id": task_id,
                    "error": str(e),
                    "fallback": "heuristic"
                }))
                # Fallback to heuristic if LLM fails
                correctness = self._heuristic_correctness(data, error_count)
        else:
            # Fallback to heuristic if no LLM or missing data
            reason = []
            if not has_llm:
                reason.append("no_llm")
            if not has_request:
                reason.append("no_initial_request")
            if not has_output:
                reason.append("no_final_output")
            
            self.logger.info(json.dumps({
                "event": "correctness_fallback_to_heuristic",
                "task_id": task_id,
                "reason": ", ".join(reason)
            }))
            correctness = self._heuristic_correctness(data, error_count)
        
        # Apply minimum score floor for completed tasks
        is_completed = False
        progress = data.get("progress", [])
        if progress:
            last = progress[-1]
            status = str(last.get("status", "") or "").lower()
            if "done" in status or "complete" in status or status == "success":
                is_completed = True
        
        # Also check task_info if available
        if not is_completed:
            task_info = data.get("task_info")
            if task_info:
                task_status = str(task_info.get("status", "") or "").lower()
                if "done" in task_status or "complete" in task_status or task_status == "success":
                    is_completed = True
        
        # If task is completed, ensure minimum correctness of 0.3 (30%)
        if is_completed and correctness < 0.3:
            self.logger.info(json.dumps({
                "event": "correctness_floor_applied",
                "task_id": task_id,
                "original_correctness": correctness,
                "adjusted_correctness": 0.3,
                "reason": "task_completed"
            }))
            correctness = 0.3
        
        self.logger.info(json.dumps({
            "event": "correctness_final",
            "task_id": task_id,
            "correctness": correctness,
            "is_completed": is_completed
        }))

        # efficiency: shorter completion, fewer API calls, fewer retries
        efficiency = self._clip(0.4 * (1.0 / (1.0 + completion_time / 300.0)) + 0.3 * (1.0 / (1.0 + total_api_calls / 50.0)) + 0.3 * (1.0 / (1.0 + retry_count)))

        # quality: fewer errors and retries + some stability reflection
        quality = self._clip(0.6 * (1.0 / (1.0 + error_count)) + 0.4 * (1.0 / (1.0 + retry_count)))

        # stability: inversely related to errors and long runs
        stability = self._clip(0.5 * (1.0 / (1.0 + error_count)) + 0.5 * (1.0 / (1.0 + completion_time / 600.0)))

        # autonomy: penalize dependency requests
        autonomy = self._clip(1.0 / (1.0 + deps))

        # resource_efficiency: low mem and CPU use is better
        resource_efficiency = self._clip(0.5 * (1.0 / (1.0 + mem / 1024.0)) + 0.5 * (1.0 / (1.0 + cpu / 100.0)))

        penalties = {
            "dependency_penalty": min(0.3, 0.05 * deps),
            "timeout_penalty": 0.0,  # could be inferred from logs in future
            "error_penalty": min(0.3, 0.05 * error_count),
        }

        weighted = (
            self.weights["correctness"] * correctness
            + self.weights["efficiency"] * efficiency
            + self.weights["quality"] * quality
            + self.weights["stability"] * stability
            + self.weights["autonomy"] * autonomy
            + self.weights["resource_efficiency"] * resource_efficiency
        )
        final_score = max(0.0, weighted - sum(penalties.values()))

        # Cost penalty: apply a small penalty for high costs (optional)
        # This keeps the score in 0-1 range while accounting for cost efficiency
        cost = float(m.get("cost_usd", 0.0) or 0.0)
        if cost > 0:
            # Apply a small penalty for costs above $0.10 (normalize to reasonable range)
            # Cost penalty is capped at 0.1 (10% reduction)
            cost_penalty = min(0.1, cost / 10.0)  # $1.00 = 0.1 penalty, $0.10 = 0.01 penalty
            final_score = max(0.0, final_score - cost_penalty)

        scores = {
            "correctness": round(correctness, 4),
            "efficiency": round(efficiency, 4),
            "quality": round(quality, 4),
            "stability": round(stability, 4),
            "autonomy": round(autonomy, 4),
            "resource_efficiency": round(resource_efficiency, 4),
            "final_score": round(final_score, 4),
        }

        return {"scores": scores, "penalties": penalties}
