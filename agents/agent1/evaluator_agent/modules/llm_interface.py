import os
import logging
from typing import Any, Dict, List, Optional

import requests


class LLMInterface:
    """Minimal LLM interface for generating evaluation summaries.

    Uses a hypothetical GPT-5 reasoning API with an OpenAI-compatible endpoint if available.
    Set env: GPT5_API_BASE, GPT5_API_KEY, GPT5_MODEL
    Fallback: produce a rule-based short summary if API not configured.
    """

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self.api_base = os.getenv("GPT5_API_BASE", "https://api.openai.com/v1")
        self.api_key = os.getenv("GPT5_API_KEY")
        self.model = os.getenv("GPT5_MODEL", "gpt-5-reasoning")

    def summarize(self, task: Dict[str, Any]) -> str:
        if not self.api_key:
            return self._fallback_summary(task)

        logs: List[Dict[str, Any]] = task.get("logs", [])
        sample = "\n".join([f"[{l.get('timestamp')}] {l.get('level')}: {str(l.get('message'))[:200]}" for l in logs[-50:]])
        m = task.get("metrics", {})
        prompt = (
            "You are an evaluator of an autonomous agent. Summarize the agent's performance, correctness, autonomy behavior, and notable events.\n"
            f"Metrics: {m}\n"
            f"Recent logs:\n{sample}\n"
            "Provide a concise, objective assessment."
        )
        try:
            resp = requests.post(
                f"{self.api_base}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You are a precise evaluation summarizer."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 300,
                },
                timeout=20,
            )
            if resp.ok:
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content")
                return content or self._fallback_summary(task)
        except Exception:
            pass
        return self._fallback_summary(task)

    def evaluate_correctness(self, initial_request: str, final_output: str) -> float:
        """
        Evaluate correctness by comparing initial request with final output.
        
        Args:
            initial_request: The original user request/task description
            final_output: The agent's final output/result
            
        Returns:
            Correctness score between 0.0 and 1.0
        """
        if not initial_request or not final_output:
            return 0.0
        
        if not self.api_key:
            # Fallback: simple heuristic based on length and keyword matching
            return self._fallback_correctness(initial_request, final_output)
        
        prompt = (
            "You are an evaluator assessing how well an agent's output aligns with the original request.\n\n"
            f"Original Request:\n{initial_request}\n\n"
            f"Agent's Final Output:\n{final_output}\n\n"
            "Evaluate how correctly the final output addresses and fulfills the original request.\n\n"
            "Scoring Guidelines (use a DECIMAL between 0.0 and 1.0, NOT a percentage):\n"
            "- 1.0 (perfect): Output fully addresses the request with complete accuracy\n"
            "- 0.8-0.9 (excellent): Output addresses most of the request with minor gaps\n"
            "- 0.6-0.7 (good): Output addresses the core request but may have some issues\n"
            "- 0.4-0.5 (fair): Output partially addresses the request with notable gaps\n"
            "- 0.2-0.3 (poor): Output has some relevance but misses key requirements\n"
            "- 0.0-0.1 (very poor): Output has little or no relevance to the request\n\n"
            "Important: Be lenient - if the output makes a reasonable attempt to address the request, "
            "even if imperfect, give it at least 0.3. Only use very low scores (0.0-0.2) if the output "
            "is completely unrelated or shows no understanding of the request.\n\n"
            "Respond with ONLY a decimal number between 0.0 and 1.0 (e.g., 0.75, not 75 or 75%). "
            "Do not include any explanation, just the number."
        )
        
        try:
            resp = requests.post(
                f"{self.api_base}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You are a precise correctness evaluator. Respond with only a number between 0.0 and 1.0."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 10,
                },
                timeout=30,
            )
            if resp.ok:
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                
                # Extract number from response - handle various formats
                import re
                score = None
                
                # Try direct float conversion first
                try:
                    score = float(content)
                except ValueError:
                    # Try to extract number from text (handles "2%", "score: 2", etc.)
                    # Look for numbers with optional decimal points
                    match = re.search(r'([0-9]+(?:\.[0-9]+)?)', content)
                    if match:
                        try:
                            score = float(match.group(1))
                        except ValueError:
                            pass
                
                if score is not None:
                    # If score > 1.0, assume it's a percentage and convert to 0-1 scale
                    if score > 1.0:
                        score = score / 100.0
                        self.logger.info(f"Converted percentage score {score * 100}% to decimal {score}")
                    
                    # Clamp to valid range
                    score = max(0.0, min(1.0, score))
                    self.logger.info(f"LLM correctness score: {score} (from response: '{content[:50]}...')")
                    return score
                else:
                    self.logger.warning(f"Could not parse score from LLM response: '{content[:100]}'")
        except Exception as e:
            self.logger.warning(f"LLM correctness evaluation failed: {e}")
        
        return self._fallback_correctness(initial_request, final_output)
    
    def _fallback_correctness(self, initial_request: str, final_output: str) -> float:
        """Fallback correctness evaluation using simple heuristics."""
        if not initial_request:
            # If no request, can't evaluate - but if there's output, give some credit
            return 0.3 if final_output else 0.0
        
        if not final_output:
            return 0.0
        
        # Simple keyword matching and length-based heuristic
        request_lower = initial_request.lower()
        output_lower = final_output.lower()
        
        # Remove common stop words for better matching
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'may', 'might', 'must', 'can'}
        
        # Count matching keywords (more lenient - use word stems and ignore stop words)
        request_words = set(word for word in request_lower.split() if word not in stop_words and len(word) > 2)
        output_words = set(word for word in output_lower.split() if word not in stop_words and len(word) > 2)
        
        if len(request_words) == 0:
            # If request has no meaningful words, give baseline score for any output
            return 0.4 if final_output else 0.0
        
        common_words = request_words.intersection(output_words)
        keyword_match_ratio = len(common_words) / len(request_words)
        
        # Length similarity (output shouldn't be too short relative to request)
        # More lenient - accept outputs that are at least 20% of request length
        min_output_length = max(10, len(initial_request) * 0.2)
        if len(final_output) < min_output_length:
            length_penalty = 0.3
        else:
            length_ratio = min(1.0, len(final_output) / max(1, len(initial_request)))
            length_penalty = 1.0 - (1.0 - length_ratio) * 0.3  # Less penalty for length differences
        
        # Combined score with more weight on keyword matching
        score = 0.7 * keyword_match_ratio + 0.3 * length_penalty
        
        # Ensure minimum baseline: if there's any output and any keyword match, give at least 0.3
        if len(common_words) > 0 and len(final_output) > 0:
            score = max(0.3, score)
        
        return max(0.0, min(1.0, score))

    def _fallback_summary(self, task: Dict[str, Any]) -> str:
        m = task.get("metrics", {})
        return (
            "Evaluation summary based on heuristics: "
            f"completion_time={m.get('completion_time_s', 0.0)}s, "
            f"errors={m.get('error_count', 0)}, retries={m.get('retry_count', 0)}, "
            f"dependency_requests={m.get('human_or_agent_requests', 0)}, api_calls={m.get('total_api_calls', 0)}."
        )
