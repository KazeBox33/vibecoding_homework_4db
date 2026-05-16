import unittest
from unittest.mock import patch

from core.agent import SqlLearningAgent, UnsafeSqlError
from core.judge_agent import JudgeAgent, JudgeDecision


class SqlLearningAgentTest(unittest.TestCase):
    def setUp(self):
        self.env_patcher = patch.dict("os.environ", {"SQL_COACH_JUDGE_PROVIDER": "local"}, clear=False)
        self.env_patcher.start()
        self.agent = SqlLearningAgent()
        self.session = self.agent.create_session("ecommerce")

    def tearDown(self):
        self.env_patcher.stop()

    def test_schema_is_generated_with_sample_data(self):
        schema = self.agent.get_schema_snapshot(self.session)
        tables = {table["table"] for table in schema["tables"]}
        self.assertIn("customers", tables)
        self.assertIn("orders", tables)
        customers = next(table for table in schema["tables"] if table["table"] == "customers")
        self.assertGreaterEqual(len(customers["preview"]), 3)

    def test_correct_answer_gets_full_score(self):
        result = self.agent.evaluate_answer(
            self.session,
            "eco-basic-where",
            """
            SELECT name, join_date
            FROM customers
            WHERE city = 'Shanghai'
            ORDER BY join_date
            """,
        )
        self.assertTrue(result["correct"])
        self.assertEqual(result["score"], 100)

    def test_markdown_sql_fence_is_normalized(self):
        result = self.agent.evaluate_answer(
            self.session,
            "eco-basic-where",
            """
            ```sql
            SELECT name, join_date
            FROM customers
            WHERE city = 'Shanghai'
            ORDER BY join_date;
            ```
            """,
        )
        self.assertTrue(result["correct"])
        self.assertEqual(result["score"], 100)
        self.assertIn("Markdown", result["feedback"])
        self.assertEqual(
            result["normalized_sql"],
            "SELECT name, join_date\n            FROM customers\n            WHERE city = 'Shanghai'\n            ORDER BY join_date;",
        )

    def test_wrong_answer_gets_feedback(self):
        result = self.agent.evaluate_answer(
            self.session,
            "eco-basic-join",
            "SELECT order_id, order_date FROM orders WHERE status = 'paid'",
        )
        self.assertFalse(result["correct"])
        self.assertIn("不一致", result["feedback"])

    def test_rejects_non_readonly_sql(self):
        result = self.agent.evaluate_answer(
            self.session,
            "eco-basic-where",
            "DROP TABLE customers",
        )
        self.assertFalse(result["correct"])
        self.assertIn("只允许", result["feedback"])

    def test_markdown_fence_does_not_allow_multiple_statements(self):
        result = self.agent.evaluate_answer(
            self.session,
            "eco-basic-where",
            """
            ```sql
            SELECT name FROM customers;
            SELECT city FROM customers;
            ```
            """,
        )
        self.assertFalse(result["correct"])
        self.assertIn("一次只能提交一条查询语句", result["feedback"])

    def test_progress_report_updates(self):
        self.agent.evaluate_answer(self.session, "eco-basic-where", "SELECT name FROM customers")
        report = self.agent.build_progress_report(self.session)
        self.assertEqual(report["attempts"], 1)
        self.assertGreater(report["average_score"], 0)

    def test_returns_judge_source(self):
        result = self.agent.evaluate_answer(
            self.session,
            "eco-basic-where",
            "SELECT name, join_date FROM customers WHERE city = 'Shanghai' ORDER BY join_date",
        )
        self.assertIn("judge_source", result)
        self.assertIn(result["judge_source"], {"local_fallback", "agent_error_fallback", "llm_agent"})

    def test_exercise_includes_runnable_test_cases(self):
        exercise = self.agent.get_exercise("eco-basic-where")
        test_cases = exercise["test_cases"]
        self.assertGreaterEqual(len(test_cases), 4)
        labels = {item["label"] for item in test_cases}
        self.assertIn("正确样例：参考答案", labels)
        self.assertIn("安全样例：非只读 SQL 拦截", labels)

    def test_exercise_includes_learning_metadata(self):
        exercise = self.agent.get_exercise("eco-basic-join")
        self.assertEqual(exercise["required_tables"], ["customers", "orders"])
        self.assertIn("order_id", exercise["output_columns"])
        self.assertTrue(any("JOIN" in step for step in exercise["solution_steps"]))

    def test_correct_test_case_can_be_submitted(self):
        exercise = self.agent.get_exercise("eco-basic-where")
        correct_case = next(item for item in exercise["test_cases"] if item["id"] == "correct_reference")
        result = self.agent.evaluate_answer(self.session, exercise["id"], correct_case["sql"])
        self.assertTrue(result["correct"])
        self.assertEqual(result["score"], 100)

    def test_unsafe_test_case_is_blocked(self):
        exercise = self.agent.get_exercise("eco-basic-where")
        unsafe_case = next(item for item in exercise["test_cases"] if item["id"] == "unsafe_sql")
        result = self.agent.evaluate_answer(self.session, exercise["id"], unsafe_case["sql"])
        self.assertFalse(result["correct"])
        self.assertIn("只允许", result["feedback"])

    def test_can_delegate_to_configured_judge_agent(self):
        class FakeJudgeAgent:
            def status(self):
                return {"enabled": True, "mode": "llm_agent"}

            def judge(self, **kwargs):
                return JudgeDecision(
                    correct=True,
                    score=97,
                    feedback="外部 Judge Agent 已完成裁决。",
                    next_steps=["继续练习聚合查询。"],
                    source="llm_agent",
                    agent_name="Fake Judge Agent",
                )

        self.agent.judge_agent = FakeJudgeAgent()
        result = self.agent.evaluate_answer(
            self.session,
            "eco-basic-where",
            "SELECT name FROM customers",
        )
        self.assertTrue(result["correct"])
        self.assertEqual(result["score"], 97)
        self.assertEqual(result["judge_source"], "llm_agent")
        self.assertEqual(result["judge_agent"], "Fake Judge Agent")

    def test_stream_question_uses_local_fallback_without_api(self):
        events = list(
            self.agent.stream_answer_question(
                self.session,
                "这题需要用到什么知识？",
                "eco-basic-where",
            )
        )
        self.assertEqual(events[0]["type"], "meta")
        self.assertEqual(events[0]["source"], "local_fallback")
        self.assertTrue(any(event.get("type") == "delta" for event in events))
        self.assertEqual(events[-1]["type"], "done")

    def test_chat_history_records_turns_and_can_clear(self):
        list(
            self.agent.stream_answer_question(
                self.session,
                "第一步应该怎么写？",
                "eco-basic-where",
            )
        )
        history = self.agent.get_chat_history(self.session)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[1]["role"], "assistant")
        self.assertIn("第一步", history[0]["content"])

        result = self.agent.clear_chat_history(self.session)
        self.assertTrue(result["ok"])
        self.assertEqual(self.agent.get_chat_history(self.session), [])


class JudgeAgentConfigTest(unittest.TestCase):
    def test_deepseek_env_selects_deepseek_defaults(self):
        with patch.dict(
            "os.environ",
            {
                "DEEPSEEK_API_KEY": "test-key",
            },
            clear=True,
        ):
            judge = JudgeAgent()
            status = judge.status()
            self.assertTrue(status["enabled"])
            self.assertEqual(status["provider"], "deepseek")
            self.assertEqual(status["model"], "deepseek-v4-flash")
            self.assertEqual(judge._completion_url(), "https://api.deepseek.com/chat/completions")

    def test_accepts_full_chat_completions_url(self):
        with patch.dict(
            "os.environ",
            {
                "SQL_COACH_LLM_API_KEY": "test-key",
                "SQL_COACH_LLM_BASE_URL": "https://api.deepseek.com/chat/completions",
                "SQL_COACH_LLM_MODEL": "deepseek-v4-flash",
            },
            clear=True,
        ):
            judge = JudgeAgent()
            self.assertEqual(judge._completion_url(), "https://api.deepseek.com/chat/completions")


if __name__ == "__main__":
    unittest.main()
