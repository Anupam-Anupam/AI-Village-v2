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
        
        # Get evaluator output score (0-100) - this is the primary factor
        output_score = 0.0
        if self.llm and has_request and has_output:
            # Use LLM to evaluate correctness by comparing request vs output
            try:
                correctness_ratio = self.llm.evaluate_correctness(initial_request, final_output)
                # Convert to score out of 100
                output_score = correctness_ratio * 100.0
                self.logger.info(json.dumps({
                    "event": "output_score_evaluated",
                    "task_id": task_id,
                    "output_score": output_score,
                    "method": "llm"
                }))
            except Exception as e:
                self.logger.warning(json.dumps({
                    "event": "output_score_evaluation_error",
                    "task_id": task_id,
                    "error": str(e),
                    "fallback": "heuristic"
                }))
                # Fallback: use heuristic correctness converted to 0-100
                correctness_ratio = self._heuristic_correctness(data, error_count)
                output_score = correctness_ratio * 100.0
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
                "event": "output_score_fallback_to_heuristic",
                "task_id": task_id,
                "reason": ", ".join(reason)
            }))
            correctness_ratio = self._heuristic_correctness(data, error_count)
            output_score = correctness_ratio * 100.0
        
        # Clamp output score to 0-100
        output_score = max(0.0, min(100.0, output_score))
        
        self.logger.info(json.dumps({
            "event": "output_score_final",
            "task_id": task_id,
            "output_score": output_score
        }))

        # Simplified scoring formula using only: output_score, time, errors, cost
        # Base score starts from output_score (0-100)
        base_score = output_score
        
        # Time penalty: penalize longer completion times
        # Normalize: 0-300s = no penalty, 300-600s = small penalty, 600s+ = larger penalty
        time_penalty = 0.0
        if completion_time > 300:
            # Penalize 1 point per 10 seconds over 300s, max 20 points
            time_penalty = min(20.0, (completion_time - 300) / 10.0)
        
        # Error penalty: penalize errors
        # Each error costs 2 points, max 20 points
        error_penalty = min(20.0, error_count * 2.0)
        
        # Cost penalty: penalize high costs
        # $0-0.10 = no penalty, $0.10-1.00 = small penalty, $1.00+ = larger penalty
        cost = float(m.get("cost_usd", 0.0) or 0.0)
        cost_penalty = 0.0
        if cost > 0.10:
            # Penalize 1 point per $0.10 over $0.10, max 10 points
            cost_penalty = min(10.0, (cost - 0.10) * 10.0)
        
        # Calculate final score: base score minus penalties
        final_score = max(0.0, base_score - time_penalty - error_penalty - cost_penalty)
        
        # Convert to 0-1 range for consistency with existing code
        final_score_normalized = final_score / 100.0

        scores = {
            "output_score": round(output_score, 2),  # Score out of 100 from evaluator
            "final_score": round(final_score_normalized, 4),  # Final score in 0-1 range
        }

        penalties = {
            "time_penalty": round(time_penalty, 2),
            "error_penalty": round(error_penalty, 2),
            "cost_penalty": round(cost_penalty, 2),
        }

        return {"scores": scores, "penalties": penalties}
