from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from collections.abc import Iterator
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


@dataclass
class TutorAnswer:
    answer: str
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

    def answer_tutor_question(
        self,
        *,
        schema: dict[str, Any],
        exercise: dict[str, Any] | None,
        question: str,
        deterministic_answer: str,
    ) -> TutorAnswer:
        if not self.is_enabled():
            return TutorAnswer(
                answer=deterministic_answer,
                source="local_fallback",
                agent_name=self.agent_name,
            )

        payload = self._build_tutor_payload(
            schema=schema,
            exercise=exercise,
            question=question,
            deterministic_answer=deterministic_answer,
        )
        try:
            raw = self._call_openai_compatible(payload)
            answer = self._parse_tutor_answer(raw)
            return TutorAnswer(
                answer=answer,
                source="llm_agent",
                agent_name="SQL Tutor Agent",
                raw=raw,
            )
        except Exception as exc:
            return TutorAnswer(
                answer=f"{deterministic_answer}\n\nTutor Agent 调用失败，已使用本地提示兜底：{exc}",
                source="agent_error_fallback",
                agent_name="SQL Tutor Agent",
            )

    def stream_tutor_question(
        self,
        *,
        schema: dict[str, Any],
        exercise: dict[str, Any] | None,
        question: str,
        deterministic_answer: str,
    ) -> Iterator[dict[str, str]]:
        if not self.is_enabled():
            yield {"type": "meta", "source": "local_fallback", "agent": self.agent_name}
            yield {"type": "delta", "text": deterministic_answer}
            yield {"type": "done"}
            return

        payload = self._build_tutor_payload(
            schema=schema,
            exercise=exercise,
            question=question,
            deterministic_answer=deterministic_answer,
            stream=True,
        )
        try:
            yield {"type": "meta", "source": "llm_agent", "agent": "SQL Tutor Agent"}
            emitted = False
            for text in self._call_openai_compatible_stream(payload):
                emitted = True
                yield {"type": "delta", "text": text}
            if not emitted:
                yield {"type": "delta", "text": "Tutor Agent 没有返回内容，请换一种问法再试。"}
            yield {"type": "done"}
        except Exception as exc:
            yield {"type": "meta", "source": "agent_error_fallback", "agent": "SQL Tutor Agent"}
            yield {
                "type": "delta",
                "text": f"{deterministic_answer}\n\nTutor Agent 调用失败，已使用本地提示兜底：{exc}",
            }
            yield {"type": "done"}

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

    def _build_tutor_payload(self, stream: bool = False, **data: Any) -> dict[str, Any]:
        if stream:
            response_instruction = "Return a direct Chinese answer. Do not output JSON."
        else:
            response_instruction = "Return only valid JSON with key: answer(string in Chinese)."
        system_prompt = (
            "You are a patient SQL tutor agent for Chinese learners. "
            "Answer the learner's question using the provided schema and exercise. "
            "Do not solve by dumping the full final SQL unless the learner explicitly asks for the answer. "
            "Explain the needed concepts, table relationships, and next step. "
            f"{response_instruction}"
        )
        user_prompt = json.dumps(data, ensure_ascii=False, default=str)
        payload = {
            "model": self.model,
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if stream:
            payload["stream"] = True
        else:
            payload["response_format"] = {"type": "json_object"}
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

    def _call_openai_compatible_stream(self, payload: dict[str, Any]) -> Iterator[str]:
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
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        yield str(content)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM stream endpoint returned HTTP {exc.code}: {detail}") from exc

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

    def _parse_tutor_answer(self, raw: dict[str, Any]) -> str:
        content = raw["choices"][0]["message"]["content"]
        try:
            parsed = json.loads(content)
            answer = str(parsed.get("answer", "")).strip()
        except json.JSONDecodeError:
            answer = content.strip()
        return answer or "Tutor Agent 没有返回有效答复，请换一种问法再试。"
