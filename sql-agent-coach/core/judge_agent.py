from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class JudgeDecision:
    correct: bool
    score: int
    feedback: str
    next_steps: list[str]
    source: str
    agent_name: str
    raw: dict[str, Any] | None = None


class JudgeAgent:
    """LLM-backed SQL judge agent with a deterministic local fallback."""

    def __init__(self) -> None:
        requested_provider = os.environ.get("SQL_COACH_JUDGE_PROVIDER", "auto").lower()
        self.provider = self._resolve_provider(requested_provider)
        self.base_url = os.environ.get("SQL_COACH_LLM_BASE_URL") or self._default_base_url()
        self.api_key = (
            os.environ.get("SQL_COACH_LLM_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )
        self.model = os.environ.get("SQL_COACH_LLM_MODEL") or self._default_model()
        self.timeout = float(os.environ.get("SQL_COACH_LLM_TIMEOUT", "25"))
        self.agent_name = os.environ.get("SQL_COACH_JUDGE_AGENT_NAME", "SQL Judge Agent")
        self.reasoning_effort = os.environ.get("SQL_COACH_REASONING_EFFORT")
        if self.reasoning_effort is None and self.provider == "deepseek":
            self.reasoning_effort = "high"
        self.deepseek_thinking = os.environ.get("SQL_COACH_DEEPSEEK_THINKING", "enabled")

    def status(self) -> dict[str, Any]:
        enabled = self.is_enabled()
        return {
            "agent_name": self.agent_name,
            "provider": self.provider,
            "enabled": enabled,
            "model": self.model if enabled else None,
            "base_url": self.base_url if enabled else None,
            "mode": "llm_agent" if enabled else "local_fallback",
            "reason": "LLM API key configured" if enabled else "Set DEEPSEEK_API_KEY, SQL_COACH_LLM_API_KEY, or OPENAI_API_KEY to enable LLM judging.",
        }

    def is_enabled(self) -> bool:
        if self.provider in {"local", "fallback", "off"}:
            return False
        return bool(self.api_key)

    def judge(
        self,
        *,
        schema: dict[str, Any],
        exercise: dict[str, Any],
        submitted_sql: str,
        expected_rows: list[dict[str, Any]],
        actual_rows: list[dict[str, Any]],
        execution_error: str | None,
        deterministic_correct: bool,
        deterministic_score: int,
        deterministic_feedback: str,
        deterministic_next_steps: list[str],
    ) -> JudgeDecision:
        if not self.is_enabled():
            return self._fallback(
                deterministic_correct,
                deterministic_score,
                deterministic_feedback,
                deterministic_next_steps,
                source="local_fallback",
            )

        payload = self._build_payload(
            schema=schema,
            exercise=exercise,
            submitted_sql=submitted_sql,
            expected_rows=expected_rows,
            actual_rows=actual_rows,
            execution_error=execution_error,
            deterministic_correct=deterministic_correct,
            deterministic_score=deterministic_score,
        )
        try:
            raw = self._call_openai_compatible(payload)
            decision = self._parse_decision(raw)
            return JudgeDecision(
                correct=decision["correct"],
                score=decision["score"],
                feedback=decision["feedback"],
                next_steps=decision["next_steps"],
                source="llm_agent",
                agent_name=self.agent_name,
                raw=raw,
            )
        except Exception as exc:
            fallback_feedback = deterministic_feedback + f" Judge Agent 调用失败，已使用本地裁决兜底：{exc}"
            return self._fallback(
                deterministic_correct,
                deterministic_score,
                fallback_feedback,
                deterministic_next_steps,
                source="agent_error_fallback",
            )

    def _fallback(
        self,
        correct: bool,
        score: int,
        feedback: str,
        next_steps: list[str],
        source: str,
    ) -> JudgeDecision:
        return JudgeDecision(
            correct=correct,
            score=score,
            feedback=feedback,
            next_steps=next_steps,
            source=source,
            agent_name=self.agent_name,
        )

    def _build_payload(self, **data: Any) -> dict[str, Any]:
        system_prompt = (
            "You are a strict but helpful SQL tutoring judge agent. "
            "Grade the learner's SQL by comparing expected and actual SQLite results. "
            "Return only valid JSON with keys: correct(boolean), score(integer 0-100), "
            "feedback(string in Chinese), next_steps(array of Chinese strings). "
            "Do not reveal hidden chain-of-thought. Be concise and actionable."
        )
        user_prompt = json.dumps(data, ensure_ascii=False, default=str)
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        if self.provider == "deepseek" and self.deepseek_thinking:
            payload["thinking"] = {"type": self.deepseek_thinking}
        return payload

    def _call_openai_compatible(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self._completion_url(),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM endpoint returned HTTP {exc.code}: {detail}") from exc

    def _resolve_provider(self, requested_provider: str) -> str:
        if requested_provider != "auto":
            return requested_provider
        if os.environ.get("DEEPSEEK_API_KEY"):
            return "deepseek"
        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        return "auto"

    def _default_base_url(self) -> str:
        if self.provider == "deepseek":
            return "https://api.deepseek.com"
        return "https://api.openai.com/v1/chat/completions"

    def _default_model(self) -> str:
        if self.provider == "deepseek":
            return "deepseek-v4-flash"
        return "gpt-4o-mini"

    def _completion_url(self) -> str:
        base_url = self.base_url.rstrip("/")
        if base_url.endswith("/chat/completions"):
            return base_url
        return f"{base_url}/chat/completions"

    def _parse_decision(self, raw: dict[str, Any]) -> dict[str, Any]:
        content = raw["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        correct = bool(parsed.get("correct", False))
        score = int(parsed.get("score", 0))
        score = max(0, min(100, score))
        feedback = str(parsed.get("feedback", "")).strip() or "Judge Agent 未返回详细反馈。"
        next_steps = parsed.get("next_steps", [])
        if not isinstance(next_steps, list):
            next_steps = [str(next_steps)]
        next_steps = [str(item) for item in next_steps if str(item).strip()]
        if not next_steps:
            next_steps = ["对照反馈修改 SQL 后再次提交。"]
        return {
            "correct": correct,
            "score": score,
            "feedback": feedback,
            "next_steps": next_steps,
        }
