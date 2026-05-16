from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from .catalog import DIFFICULTIES, EXERCISES, KINDS, SCENARIOS
from .judge_agent import JudgeAgent


class UnsafeSqlError(ValueError):
    """Raised when submitted SQL is not a read-only query."""


@dataclass
class Attempt:
    exercise_id: str
    submitted_sql: str
    correct: bool
    score: int
    feedback: str
    created_at: float = field(default_factory=time.time)


@dataclass
class ChatMessage:
    role: str
    content: str
    exercise_id: str | None = None
    created_at: float = field(default_factory=time.time)


@dataclass
class CoachSession:
    session_id: str
    scenario_key: str
    connection: sqlite3.Connection
    attempts: list[Attempt] = field(default_factory=list)
    chat_messages: list[ChatMessage] = field(default_factory=list)


class SqlLearningAgent:
    def __init__(self) -> None:
        self.scenarios = SCENARIOS
        self.exercises = EXERCISES
        self.judge_agent = JudgeAgent()

    def list_scenarios(self) -> list[dict[str, str]]:
        return [
            {
                "key": key,
                "name": value["name"],
                "description": value["description"],
            }
            for key, value in self.scenarios.items()
        ]

    def agent_status(self) -> dict[str, Any]:
        return self.judge_agent.status()

    def create_session(self, scenario_key: str = "ecommerce") -> CoachSession:
        if scenario_key not in self.scenarios:
            scenario_key = "ecommerce"

        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        scenario = self.scenarios[scenario_key]
        conn.executescript(scenario["schema_sql"])
        conn.executescript(scenario["data_sql"])
        conn.commit()
        return CoachSession(str(uuid.uuid4()), scenario_key, conn)

    def get_schema_snapshot(self, session: CoachSession) -> dict[str, Any]:
        tables = self._query(
            session.connection,
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
            trusted=True,
        )
        result = []
        for table in tables:
            table_name = table["name"]
            columns = self._query(session.connection, f"PRAGMA table_info({table_name})", trusted=True)
            preview = self._query(session.connection, f"SELECT * FROM {table_name} LIMIT 5", trusted=True)
            result.append(
                {
                    "table": table_name,
                    "columns": [{"name": c["name"], "type": c["type"], "pk": bool(c["pk"])} for c in columns],
                    "preview": preview,
                }
            )
        return {
            "scenario": self.scenarios[session.scenario_key]["name"],
            "description": self.scenarios[session.scenario_key]["description"],
            "tables": result,
        }

    def generate_exercises(
        self,
        scenario_key: str,
        difficulty: str | None = None,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        exercises = [item for item in self.exercises if item["scenario"] == scenario_key]
        if difficulty and difficulty != "全部":
            exercises = [item for item in exercises if item["difficulty"] == difficulty]
        if kind and kind != "全部":
            exercises = [item for item in exercises if item["kind"] == kind]
        return [self._public_exercise(item) for item in exercises]

    def get_exercise(self, exercise_id: str) -> dict[str, Any]:
        exercise = self._find_exercise(exercise_id)
        return self._public_exercise(exercise)

    def evaluate_answer(self, session: CoachSession, exercise_id: str, submitted_sql: str) -> dict[str, Any]:
        exercise = self._find_exercise(exercise_id)
        submitted_sql = submitted_sql.strip()

        try:
            expected_rows = self._query(session.connection, exercise["expected_sql"])
            actual_rows = self._query(session.connection, submitted_sql)
            deterministic_correct = self._rows_equal(expected_rows, actual_rows)
            deterministic_score = 100 if deterministic_correct else self._partial_score(expected_rows, actual_rows, submitted_sql, exercise)
            deterministic_feedback = self.explain_mistake(
                exercise=exercise,
                submitted_sql=submitted_sql,
                expected_rows=expected_rows,
                actual_rows=actual_rows,
                error=None,
                correct=deterministic_correct,
            )
            error_message = None
        except Exception as exc:  # sqlite errors become teaching feedback.
            expected_rows = self._query(session.connection, exercise["expected_sql"])
            actual_rows = []
            deterministic_correct = False
            deterministic_score = 20 if isinstance(exc, UnsafeSqlError) else 30
            error_message = str(exc)
            deterministic_feedback = self.explain_mistake(
                exercise=exercise,
                submitted_sql=submitted_sql,
                expected_rows=expected_rows,
                actual_rows=actual_rows,
                error=exc,
                correct=False,
            )

        deterministic_next_steps = self._next_steps(exercise, deterministic_correct, deterministic_score)
        decision = self.judge_agent.judge(
            schema=self.get_schema_snapshot(session),
            exercise=self._public_exercise(exercise),
            submitted_sql=submitted_sql,
            expected_rows=expected_rows,
            actual_rows=actual_rows,
            execution_error=error_message,
            deterministic_correct=deterministic_correct,
            deterministic_score=deterministic_score,
            deterministic_feedback=deterministic_feedback,
            deterministic_next_steps=deterministic_next_steps,
        )
        correct = decision.correct
        score = decision.score
        feedback = decision.feedback

        attempt = Attempt(exercise_id, submitted_sql, correct, score, feedback)
        session.attempts.append(attempt)
        return {
            "correct": correct,
            "score": score,
            "feedback": feedback,
            "error": error_message,
            "judge_source": decision.source,
            "judge_agent": decision.agent_name,
            "expected_sql": exercise["expected_sql"].strip(),
            "expected_rows": expected_rows,
            "actual_rows": actual_rows,
            "next_steps": decision.next_steps,
            "summary": self.build_progress_report(session),
        }

    def explain_mistake(
        self,
        exercise: dict[str, Any],
        submitted_sql: str,
        expected_rows: list[dict[str, Any]],
        actual_rows: list[dict[str, Any]],
        error: Exception | None,
        correct: bool,
    ) -> str:
        if correct:
            return "答案正确。你的 SQL 与参考答案返回了相同结果，可以继续挑战更高难度。"

        if error is not None:
            message = str(error)
            if isinstance(error, UnsafeSqlError):
                return f"当前系统只允许 SELECT / WITH 查询。请去掉修改数据或多语句执行部分。错误信息：{message}"
            if "no such table" in message:
                return f"表名不存在。请对照左侧 schema 检查表名拼写。SQLite 返回：{message}"
            if "no such column" in message:
                return f"列名不存在或没有加正确表别名。请查看 schema 中的字段名。SQLite 返回：{message}"
            if "syntax error" in message:
                return f"SQL 语法有误。建议先写 FROM/JOIN，再补 WHERE/GROUP BY/ORDER BY。SQLite 返回：{message}"
            return f"SQL 执行失败。请先确认语法和字段名。SQLite 返回：{message}"

        expected_columns = set(expected_rows[0].keys()) if expected_rows else set()
        actual_columns = set(actual_rows[0].keys()) if actual_rows else set()
        lowered = submitted_sql.lower()
        missing_concepts = [c for c in exercise["concepts"] if c.lower().split()[0] not in lowered]

        messages = ["SQL 可以执行，但结果和参考答案不一致。"]
        if expected_columns != actual_columns:
            messages.append(f"输出列不匹配：期望 {sorted(expected_columns)}，实际 {sorted(actual_columns)}。")
        if len(expected_rows) != len(actual_rows):
            messages.append(f"行数不匹配：期望 {len(expected_rows)} 行，实际 {len(actual_rows)} 行。")
        if "GROUP BY" in exercise["concepts"] and "group by" not in lowered:
            messages.append("这道题需要按业务实体分组，否则聚合会把所有数据混在一起。")
        if "HAVING" in exercise["concepts"] and "having" not in lowered:
            messages.append("过滤聚合后的结果应使用 HAVING，而不是 WHERE。")
        if "JOIN" in exercise["concepts"] and "join" not in lowered:
            messages.append("这道题需要连接多张表，请确认关联键是否写对。")
        if missing_concepts:
            messages.append("可重点检查这些知识点：" + "、".join(missing_concepts) + "。")
        return " ".join(messages)

    def answer_question(self, session: CoachSession, question: str, exercise_id: str | None = None) -> dict[str, str]:
        exercise = self._find_exercise(exercise_id) if exercise_id else None
        schema = self.get_schema_snapshot(session)
        deterministic_answer = self._local_answer_question(schema, question, exercise)
        history = self._recent_chat_history(session)
        session.chat_messages.append(ChatMessage("user", question, exercise_id))
        tutor_answer = self.judge_agent.answer_tutor_question(
            schema=schema,
            exercise=self._public_exercise(exercise) if exercise else None,
            question=question,
            deterministic_answer=deterministic_answer,
            conversation_history=history,
        )
        session.chat_messages.append(ChatMessage("assistant", tutor_answer.answer, exercise_id))
        return {
            "answer": tutor_answer.answer,
            "source": tutor_answer.source,
            "agent": tutor_answer.agent_name,
        }

    def stream_answer_question(
        self,
        session: CoachSession,
        question: str,
        exercise_id: str | None = None,
    ) -> Iterator[dict[str, str]]:
        exercise = self._find_exercise(exercise_id) if exercise_id else None
        schema = self.get_schema_snapshot(session)
        deterministic_answer = self._local_answer_question(schema, question, exercise)
        history = self._recent_chat_history(session)
        session.chat_messages.append(ChatMessage("user", question, exercise_id))
        answer_parts: list[str] = []
        for event in self.judge_agent.stream_tutor_question(
            schema=schema,
            exercise=self._public_exercise(exercise) if exercise else None,
            question=question,
            deterministic_answer=deterministic_answer,
            conversation_history=history,
        ):
            if event.get("type") == "delta":
                answer_parts.append(event.get("text", ""))
            yield event
        answer = "".join(answer_parts).strip()
        if answer:
            session.chat_messages.append(ChatMessage("assistant", answer, exercise_id))

    def get_chat_history(self, session: CoachSession) -> list[dict[str, Any]]:
        return [
            {
                "role": message.role,
                "content": message.content,
                "exercise_id": message.exercise_id,
                "created_at": message.created_at,
            }
            for message in session.chat_messages
        ]

    def clear_chat_history(self, session: CoachSession) -> dict[str, Any]:
        session.chat_messages.clear()
        return {"ok": True, "messages": []}

    def _recent_chat_history(self, session: CoachSession, limit: int = 10) -> list[dict[str, str]]:
        return [
            {
                "role": message.role,
                "content": message.content,
                "exercise_id": message.exercise_id or "",
            }
            for message in session.chat_messages[-limit:]
        ]

    def _local_answer_question(
        self,
        schema: dict[str, Any],
        question: str,
        exercise: dict[str, Any] | None,
    ) -> str:
        text = question.lower()
        table_names = "、".join(table["table"] for table in schema["tables"])

        if any(word in text for word in ["schema", "表", "字段", "列"]):
            return f"当前场景包含这些表：{table_names}。你可以在左侧展开每张表查看字段和样例数据。"
        if any(word in text for word in ["join", "连接", "关联"]):
            return "写 JOIN 时先找主外键关系，例如 orders.customer_id = customers.customer_id。再决定筛选条件放在 WHERE，聚合条件放在 HAVING。"
        if any(word in text for word in ["group", "聚合", "平均", "总", "sum", "avg"]):
            return "聚合题建议按三步写：确定分组粒度，选择 SUM/AVG/COUNT 等函数，再用 GROUP BY 固定粒度。需要过滤聚合结果时使用 HAVING。"
        if exercise:
            return "本题提示：" + " ".join(exercise["hints"])
        return "可以先用 SELECT * FROM 表名 LIMIT 5 观察数据，再逐步增加 WHERE、JOIN、GROUP BY。"

    def build_progress_report(self, session: CoachSession) -> dict[str, Any]:
        attempts = session.attempts
        if not attempts:
            return {
                "attempts": 0,
                "average_score": 0,
                "correct_rate": 0,
                "advice": "先完成一道题，系统会根据表现生成建议。",
            }

        avg_score = round(sum(item.score for item in attempts) / len(attempts), 1)
        correct_rate = round(sum(1 for item in attempts if item.correct) / len(attempts) * 100, 1)
        wrong_items = [self._find_exercise(item.exercise_id) for item in attempts if not item.correct]
        weak_concepts = sorted({concept for item in wrong_items for concept in item["concepts"]})

        if avg_score >= 85:
            advice = "整体掌握较好，可以继续练习子查询、窗口函数和复杂聚合。"
        elif avg_score >= 60:
            advice = "基础已建立，建议重点复盘错题中的 JOIN 条件、分组粒度和排序要求。"
        else:
            advice = "建议先从入门题开始，逐步练习 SELECT、WHERE、JOIN，再进入聚合题。"
        if weak_concepts:
            advice += " 当前薄弱点：" + "、".join(weak_concepts[:5]) + "。"

        return {
            "attempts": len(attempts),
            "average_score": avg_score,
            "correct_rate": correct_rate,
            "advice": advice,
        }

    def options(self) -> dict[str, list[str]]:
        return {"difficulties": ["全部", *DIFFICULTIES], "kinds": ["全部", *KINDS]}

    def _find_exercise(self, exercise_id: str | None) -> dict[str, Any]:
        for exercise in self.exercises:
            if exercise["id"] == exercise_id:
                return exercise
        raise KeyError(f"unknown exercise: {exercise_id}")

    def _public_exercise(self, exercise: dict[str, Any]) -> dict[str, Any]:
        public = {
            key: value
            for key, value in exercise.items()
            if key not in {"expected_sql"}
        }
        public["test_cases"] = self._build_test_cases(exercise)
        public["required_tables"] = self._extract_required_tables(exercise)
        public["output_columns"] = self._extract_output_columns(exercise)
        public["solution_steps"] = self._build_solution_steps(exercise)
        return public

    def _build_test_cases(self, exercise: dict[str, Any]) -> list[dict[str, str]]:
        first_table = self._first_table_name(exercise["scenario"])
        return [
            {
                "id": "correct_reference",
                "label": "正确样例：参考答案",
                "expected": "应判定正确，得分接近 100。",
                "sql": exercise["expected_sql"].strip(),
            },
            {
                "id": "wrong_shape",
                "label": "错误样例：输出结构不匹配",
                "expected": "可执行，但应判定为结果不一致。",
                "sql": f"SELECT *\nFROM {first_table}\nLIMIT 3",
            },
            {
                "id": "syntax_error",
                "label": "错误样例：SQL 语法错误",
                "expected": "应返回语法错误解析。",
                "sql": f"SELECT FROM {first_table}",
            },
            {
                "id": "unsafe_sql",
                "label": "安全样例：非只读 SQL 拦截",
                "expected": "应被只读安全策略拦截。",
                "sql": f"DROP TABLE {first_table}",
            },
        ]

    def _first_table_name(self, scenario_key: str) -> str:
        schema_sql = self.scenarios[scenario_key]["schema_sql"]
        match = re.search(r"CREATE\s+TABLE\s+([a-zA-Z_][a-zA-Z0-9_]*)", schema_sql, re.IGNORECASE)
        return match.group(1) if match else "sqlite_master"

    def _scenario_table_names(self, scenario_key: str) -> list[str]:
        schema_sql = self.scenarios[scenario_key]["schema_sql"]
        return re.findall(r"CREATE\s+TABLE\s+([a-zA-Z_][a-zA-Z0-9_]*)", schema_sql, re.IGNORECASE)

    def _extract_required_tables(self, exercise: dict[str, Any]) -> list[str]:
        sql = exercise["expected_sql"].lower()
        tables = [table for table in self._scenario_table_names(exercise["scenario"]) if re.search(rf"\b{re.escape(table.lower())}\b", sql)]
        return tables or [self._first_table_name(exercise["scenario"])]

    def _extract_output_columns(self, exercise: dict[str, Any]) -> list[str]:
        sql = exercise["expected_sql"].strip()
        match = re.search(r"select\s+(.*?)\s+from\s", sql, re.IGNORECASE | re.DOTALL)
        if not match:
            return []
        select_part = re.sub(r"\s+", " ", match.group(1)).strip()
        columns = []
        for item in select_part.split(","):
            item = item.strip()
            alias_match = re.search(r"\bas\s+([a-zA-Z_][a-zA-Z0-9_]*)$", item, re.IGNORECASE)
            if alias_match:
                columns.append(alias_match.group(1))
                continue
            plain = item.split(".")[-1].strip()
            plain = re.sub(r"\(.*\)", "", plain).strip()
            if plain:
                columns.append(plain)
        return columns

    def _build_solution_steps(self, exercise: dict[str, Any]) -> list[str]:
        steps = ["先确认题目要求的输出列和排序方式。"]
        concepts = set(exercise["concepts"])
        if "JOIN" in concepts:
            steps.append("根据相关表的主键/外键写 JOIN 条件。")
        if any(item in concepts for item in ["WHERE", "筛选查询"]):
            steps.append("把普通筛选条件写在 WHERE 中。")
        if any(item in concepts for item in ["SUM", "AVG", "GROUP BY"]):
            steps.append("确定分组粒度，再写聚合函数和 GROUP BY。")
        if "HAVING" in concepts:
            steps.append("对聚合后的结果使用 HAVING 过滤。")
        if any(item in concepts for item in ["WITH", "子查询"]):
            steps.append("先拆出中间结果，再在外层查询中比较或筛选。")
        if any(item in concepts for item in ["窗口函数", "RANK", "PARTITION BY"]):
            steps.append("用窗口函数按业务维度分区并排序，再筛选排名。")
        if "ORDER BY" in concepts:
            steps.append("最后补上 ORDER BY，确保结果顺序符合题意。")
        return steps

    def _query(self, conn: sqlite3.Connection, sql: str, trusted: bool = False) -> list[dict[str, Any]]:
        cleaned = sql.strip()
        if not trusted:
            cleaned = self._ensure_readonly(cleaned)
        start = time.monotonic()

        def limit_runtime() -> int:
            return 1 if time.monotonic() - start > 1.5 else 0

        conn.set_progress_handler(limit_runtime, 1000)
        try:
            cursor = conn.execute(cleaned)
            rows = cursor.fetchall()
        finally:
            conn.set_progress_handler(None, 0)
        return [dict(row) for row in rows]

    def _ensure_readonly(self, sql: str) -> str:
        sql = sql.strip().rstrip(";").strip()
        if not sql:
            raise UnsafeSqlError("SQL 不能为空。")
        if ";" in sql:
            raise UnsafeSqlError("一次只能提交一条查询语句。")
        if not re.match(r"^(select|with)\b", sql, re.IGNORECASE):
            raise UnsafeSqlError("只允许 SELECT 或 WITH 开头的只读查询。")
        forbidden = re.search(r"\b(insert|update|delete|drop|alter|create|replace|pragma|attach|detach)\b", sql, re.IGNORECASE)
        if forbidden:
            raise UnsafeSqlError(f"检测到非只读关键字：{forbidden.group(1)}。")
        return sql

    def _rows_equal(self, expected: list[dict[str, Any]], actual: list[dict[str, Any]]) -> bool:
        if expected == actual:
            return True
        return self._canonical_rows(expected) == self._canonical_rows(actual)

    def _canonical_rows(self, rows: list[dict[str, Any]]) -> list[str]:
        normalized = []
        for row in rows:
            normalized.append(json.dumps(row, sort_keys=True, ensure_ascii=False, default=str))
        return sorted(normalized)

    def _partial_score(
        self,
        expected_rows: list[dict[str, Any]],
        actual_rows: list[dict[str, Any]],
        submitted_sql: str,
        exercise: dict[str, Any],
    ) -> int:
        score = 35
        if expected_rows and actual_rows:
            if set(expected_rows[0].keys()) == set(actual_rows[0].keys()):
                score += 20
            if len(expected_rows) == len(actual_rows):
                score += 15
        lowered = submitted_sql.lower()
        concept_hits = sum(1 for c in exercise["concepts"] if c.lower().split()[0] in lowered)
        score += min(25, concept_hits * 8)
        return min(score, 85)

    def _next_steps(self, exercise: dict[str, Any], correct: bool, score: int) -> list[str]:
        if correct:
            if exercise["difficulty"] == "入门":
                return ["继续选择进阶题，重点练习 JOIN 和 GROUP BY。"]
            if exercise["difficulty"] == "进阶":
                return ["尝试挑战题，练习 WITH、子查询或窗口函数。"]
            return ["可以尝试改写参考答案，例如用子查询和 CTE 分别实现同一目标。"]
        if score >= 60:
            return ["对照参考答案检查输出列、排序和分组粒度。", "保留已写对的结构，只微调过滤条件。"]
        return ["先点击提示理解表关系。", "写出最小可运行 SELECT，再逐步加入 JOIN、WHERE、GROUP BY。"]
