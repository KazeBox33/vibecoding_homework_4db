let sessionId = null;
let currentScenario = "ecommerce";
let currentExercise = null;
let exercises = [];
let lastResult = null;

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "请求失败");
  return data;
}

function optionList(select, values, labelKey = null, valueKey = null) {
  select.innerHTML = "";
  values.forEach((item) => {
    const option = document.createElement("option");
    option.value = valueKey ? item[valueKey] : item;
    option.textContent = labelKey ? item[labelKey] : item;
    select.appendChild(option);
  });
}

async function init() {
  const data = await api("/api/scenarios");
  optionList($("scenarioSelect"), data.scenarios, "name", "key");
  optionList($("difficultySelect"), data.difficulties);
  optionList($("kindSelect"), data.kinds);
  await startSession();
}

async function startSession() {
  currentScenario = $("scenarioSelect").value || "ecommerce";
  const data = await api("/api/start", {
    method: "POST",
    body: JSON.stringify({ scenario: currentScenario }),
  });
  sessionId = data.session_id;
  renderAgentStatus(data.agent_status);
  renderSchema(data.schema);
  exercises = data.exercises;
  renderExercises();
  chooseExercise(exercises[0]?.id);
  renderProgress({ attempts: 0, average_score: 0, correct_rate: 0, advice: "" });
  $("feedback").className = "feedback muted";
  $("feedback").textContent = "新数据库已生成。请选择题目并提交 SQL。";
  $("actualRows").innerHTML = "";
  $("expectedRows").innerHTML = "";
}

async function refreshExercises() {
  const difficulty = encodeURIComponent($("difficultySelect").value);
  const kind = encodeURIComponent($("kindSelect").value);
  const data = await api(`/api/exercises?scenario=${currentScenario}&difficulty=${difficulty}&kind=${kind}`);
  exercises = data.exercises;
  renderExercises();
  chooseExercise(exercises[0]?.id);
}

function renderExercises() {
  const list = $("exerciseList");
  list.innerHTML = "";
  if (!exercises.length) {
    list.innerHTML = '<div class="muted">当前筛选条件下没有题目。</div>';
    return;
  }
  exercises.forEach((exercise) => {
    const item = document.createElement("div");
    item.className = "exercise-card" + (currentExercise?.id === exercise.id ? " active" : "");
    item.onclick = () => chooseExercise(exercise.id);
    item.innerHTML = `
      <span class="pill">${exercise.difficulty} · ${exercise.kind}</span>
      <strong>${exercise.title}</strong>
      <small class="muted">${exercise.concepts.join(" / ")}</small>
    `;
    list.appendChild(item);
  });
}

function chooseExercise(id) {
  currentExercise = exercises.find((item) => item.id === id) || null;
  renderExercises();
  if (!currentExercise) {
    $("exerciseMeta").textContent = "无题目";
    $("exerciseTitle").textContent = "没有匹配题目";
    $("exercisePrompt").textContent = "请调整难度或题型筛选。";
    renderTestCases([]);
    return;
  }
  $("exerciseMeta").textContent = `${currentExercise.difficulty} · ${currentExercise.kind}`;
  $("exerciseTitle").textContent = currentExercise.title;
  $("exercisePrompt").textContent = currentExercise.prompt;
  renderTestCases(currentExercise.test_cases || []);
  $("sqlInput").value = "";
  lastResult = null;
}

function renderTestCases(testCases) {
  const select = $("testCaseSelect");
  select.innerHTML = "";
  testCases.forEach((testCase) => {
    const option = document.createElement("option");
    option.value = testCase.id;
    option.textContent = testCase.label;
    select.appendChild(option);
  });
  updateTestCaseNote();
}

function selectedTestCase() {
  if (!currentExercise?.test_cases?.length) return null;
  return currentExercise.test_cases.find((item) => item.id === $("testCaseSelect").value) || currentExercise.test_cases[0];
}

function updateTestCaseNote() {
  const testCase = selectedTestCase();
  $("testCaseNote").textContent = testCase ? testCase.expected : "当前题目没有测试样例。";
}

function loadTestCase() {
  const testCase = selectedTestCase();
  if (!testCase) return;
  $("sqlInput").value = testCase.sql;
  $("feedback").className = "feedback muted";
  $("feedback").textContent = `已载入：${testCase.label}。${testCase.expected}`;
}

async function runTestCase() {
  loadTestCase();
  await submitAnswer();
}

function renderSchema(schema) {
  const root = $("schemaView");
  root.innerHTML = "";
  schema.tables.forEach((table) => {
    const box = document.createElement("div");
    box.className = "schema-table";
    const columns = table.columns
      .map((column) => `${column.name} ${column.type}${column.pk ? " PK" : ""}`)
      .join(" · ");
    box.innerHTML = `<header>${table.table}</header><div class="columns">${columns}</div>`;
    const preview = document.createElement("div");
    preview.className = "table-wrap";
    preview.innerHTML = tableHtml(table.preview);
    box.appendChild(preview);
    root.appendChild(box);
  });
}

async function submitAnswer() {
  if (!currentExercise) return;
  const sql = $("sqlInput").value;
  const data = await api("/api/answer", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, exercise_id: currentExercise.id, sql }),
  });
  lastResult = data;
  $("feedback").className = `feedback ${data.correct ? "ok" : "bad"}`;
  $("feedback").innerHTML = `
    <strong>${data.correct ? "正确" : "需要修改"} · ${data.score} 分 · ${judgeLabel(data.judge_source)}</strong><br>
    ${escapeHtml(data.feedback)}<br>
    ${data.next_steps.map(escapeHtml).join("<br>")}
  `;
  $("actualRows").innerHTML = tableHtml(data.actual_rows);
  $("expectedRows").innerHTML = tableHtml(data.expected_rows);
  renderProgress(data.summary);
}

function showSolution() {
  if (!lastResult) {
    $("feedback").className = "feedback muted";
    $("feedback").textContent = "请先提交一次答案，再查看参考答案。";
    return;
  }
  $("sqlInput").value = lastResult.expected_sql;
}

function showHint() {
  if (!currentExercise) return;
  $("feedback").className = "feedback muted";
  $("feedback").innerHTML = currentExercise.hints.map(escapeHtml).join("<br>");
}

async function askAgent() {
  const question = $("questionInput").value.trim();
  if (!question) return;
  $("askBtn").disabled = true;
  $("askBtn").textContent = "回复中...";
  $("qaAnswer").textContent = "SQL Tutor Agent 正在思考...\n";
  try {
    await streamAgentAnswer(question);
  } catch (error) {
    $("qaAnswer").textContent = `流式回复失败：${error.message}`;
  } finally {
    $("askBtn").disabled = false;
    $("askBtn").textContent = "提问";
  }
}

async function streamAgentAnswer(question) {
  const response = await fetch("/api/ask-stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      exercise_id: currentExercise?.id,
      question,
    }),
  });
  if (!response.ok || !response.body) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || "请求失败");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let answerStarted = false;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line);
      if (event.type === "meta") {
        $("qaAnswer").textContent = `${tutorSourceLabel(event.source)}\n`;
        answerStarted = true;
      } else if (event.type === "delta") {
        if (!answerStarted) {
          $("qaAnswer").textContent = "";
          answerStarted = true;
        }
        $("qaAnswer").textContent += event.text;
      }
    }
  }

  if (buffer.trim()) {
    const event = JSON.parse(buffer);
    if (event.type === "delta") $("qaAnswer").textContent += event.text;
  }
}

function renderProgress(summary) {
  $("avgScore").textContent = summary.average_score;
  $("correctRate").textContent = `正确率 ${summary.correct_rate}%`;
}

function renderAgentStatus(status) {
  const box = $("agentStatus");
  if (!status) return;
  box.className = `agent-status ${status.enabled ? "on" : "off"}`;
  box.innerHTML = status.enabled
    ? `<strong>${escapeHtml(status.agent_name)}</strong><br>已启用 LLM Agent 判题：${escapeHtml(status.model)}`
    : `<strong>${escapeHtml(status.agent_name)}</strong><br>未配置外部 LLM，当前使用本地兜底判题。`;
}

function judgeLabel(source) {
  if (source === "llm_agent") return "LLM Judge Agent";
  if (source === "agent_error_fallback") return "Agent 失败后本地兜底";
  return "本地兜底";
}

function tutorSourceLabel(source) {
  if (source === "llm_agent") return "SQL Tutor Agent 正在流式回复：";
  if (source === "agent_error_fallback") return "Tutor Agent 调用失败，显示本地兜底：";
  return "本地兜底回复：";
}

function tableHtml(rows) {
  if (!rows || rows.length === 0) return '<div class="columns">无返回行</div>';
  const columns = Object.keys(rows[0]);
  const head = columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("");
  const body = rows
    .map((row) => `<tr>${columns.map((column) => `<td>${escapeHtml(row[column])}</td>`).join("")}</tr>`)
    .join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

$("resetBtn").addEventListener("click", startSession);
$("submitBtn").addEventListener("click", submitAnswer);
$("solutionBtn").addEventListener("click", showSolution);
$("hintBtn").addEventListener("click", showHint);
$("askBtn").addEventListener("click", askAgent);
$("loadCaseBtn").addEventListener("click", loadTestCase);
$("runCaseBtn").addEventListener("click", runTestCase);
$("testCaseSelect").addEventListener("change", updateTestCaseNote);
$("difficultySelect").addEventListener("change", refreshExercises);
$("kindSelect").addEventListener("change", refreshExercises);
$("scenarioSelect").addEventListener("change", startSession);

init().catch((error) => {
  $("feedback").className = "feedback bad";
  $("feedback").textContent = error.message;
});
