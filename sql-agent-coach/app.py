from __future__ import annotations

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from core.agent import CoachSession, SqlLearningAgent

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"

agent = SqlLearningAgent()
sessions: dict[str, CoachSession] = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/scenarios":
            return self._json({"scenarios": agent.list_scenarios(), **agent.options()})
        if parsed.path == "/api/agent-status":
            return self._json(agent.agent_status())
        if parsed.path == "/api/schema":
            session = self._require_session(parse_qs(parsed.query))
            return self._json(agent.get_schema_snapshot(session))
        if parsed.path == "/api/exercises":
            query = parse_qs(parsed.query)
            scenario = query.get("scenario", ["ecommerce"])[0]
            difficulty = query.get("difficulty", ["全部"])[0]
            kind = query.get("kind", ["全部"])[0]
            return self._json({"exercises": agent.generate_exercises(scenario, difficulty, kind)})
        if parsed.path == "/api/report":
            session = self._require_session(parse_qs(parsed.query))
            return self._json(agent.build_progress_report(session))
        if parsed.path == "/api/chat-history":
            session = self._require_session(parse_qs(parsed.query))
            return self._json({"messages": agent.get_chat_history(session)})
        return self._static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        payload = self._read_json()
        try:
            if parsed.path == "/api/start":
                scenario = payload.get("scenario", "ecommerce")
                session = agent.create_session(scenario)
                sessions[session.session_id] = session
                return self._json(
                    {
                        "session_id": session.session_id,
                        "agent_status": agent.agent_status(),
                        "schema": agent.get_schema_snapshot(session),
                        "exercises": agent.generate_exercises(session.scenario_key),
                    }
                )
            if parsed.path == "/api/answer":
                session = sessions[payload["session_id"]]
                return self._json(
                    agent.evaluate_answer(
                        session=session,
                        exercise_id=payload["exercise_id"],
                        submitted_sql=payload.get("sql", ""),
                    )
                )
            if parsed.path == "/api/ask":
                session = sessions[payload["session_id"]]
                return self._json(
                    agent.answer_question(
                        session=session,
                        question=payload.get("question", ""),
                        exercise_id=payload.get("exercise_id"),
                    )
                )
            if parsed.path == "/api/ask-stream":
                session = sessions[payload["session_id"]]
                return self._stream_json_lines(
                    agent.stream_answer_question(
                        session=session,
                        question=payload.get("question", ""),
                        exercise_id=payload.get("exercise_id"),
                    )
                )
            if parsed.path == "/api/chat-clear":
                session = sessions[payload["session_id"]]
                return self._json(agent.clear_chat_history(session))
        except KeyError as exc:
            return self._json({"error": f"缺少或无效参数：{exc}"}, status=400)
        except Exception as exc:
            return self._json({"error": str(exc)}, status=500)
        return self._json({"error": "unknown endpoint"}, status=404)

    def _static(self, request_path: str) -> None:
        path = STATIC_DIR / "index.html" if request_path == "/" else ROOT / request_path.lstrip("/")
        path = path.resolve()
        if not str(path).startswith(str(ROOT)) or not path.exists() or path.is_dir():
            return self._json({"error": "not found"}, status=404)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream_json_lines(self, events) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        for event in events:
            line = json.dumps(event, ensure_ascii=False) + "\n"
            self.wfile.write(line.encode("utf-8"))
            self.wfile.flush()

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _require_session(self, query: dict[str, list[str]]) -> CoachSession:
        session_id = query.get("session_id", [""])[0]
        if session_id not in sessions:
            raise KeyError("session_id")
        return sessions[session_id]

    def log_message(self, format: str, *args: object) -> None:
        print("[server]", format % args)


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"SQL Agent Coach running at http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
