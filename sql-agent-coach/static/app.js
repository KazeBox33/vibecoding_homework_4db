let sessionId = null;
let currentScenario = "ecommerce";
let currentExercise = null;
let exercises = [];
let schemaSnapshot = null;
let lastResult = null;
const exerciseAttempts = new Map();

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
  schemaSnapshot = data.schema;
  renderSchema(data.schema);
  exercises = data.exercises;
  populateConceptOptions();
  renderExercises();
  chooseExercise(exercises[0]?.id);
  renderChatHistory([]);
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
  populateConceptOptions();
  renderExercises();
  chooseExercise(filteredExercises()[0]?.id);
}

function renderExercises() {
  const list = $("exerciseList");
  list.innerHTML = "";
  const visibleExercises = filteredExercises();
  if (!visibleExercises.length) {
    list.innerHTML = '<div class="muted">当前筛选条件下没有题目。</div>';
    return;
  }
  visibleExercises.forEach((exercise) => {
    const item = document.createElement("div");
    item.className = "exercise-card" + (currentExercise?.id === exercise.id ? " active" : "");
    item.onclick = () => chooseExercise(exercise.id);
    const result = exerciseAttempts.get(exercise.id);
    const resultText = result ? ` · 最近 ${result.score} 分` : "";
    item.innerHTML = `
      <span class="pill">${exercise.difficulty} · ${exercise.kind}</span>
      <strong>${exercise.title}</strong>
      <small class="muted">${exercise.concepts.join(" / ")}${resultText}</small>
    `;
    list.appendChild(item);
  });
}

function filteredExercises() {
  const keyword = $("searchInput").value.trim().toLowerCase();
  const concept = $("conceptSelect").value;
  return exercises.filter((exercise) => {
    const conceptMatched = !concept || concept === "全部" || exercise.concepts.includes(concept);
    const haystack = [
      exercise.title,
      exercise.prompt,
      exercise.difficulty,
      exercise.kind,
      ...(exercise.concepts || []),
      ...(exercise.required_tables || []),
      ...(exercise.output_columns || []),
    ]
      .join(" ")
      .toLowerCase();
    const keywordMatched = !keyword || haystack.includes(keyword);
    return conceptMatched && keywordMatched;
  });
}

function populateConceptOptions() {
  const current = $("conceptSelect").value || "全部";
  const concepts = Array.from(new Set(exercises.flatMap((exercise) => exercise.concepts || []))).sort();
  optionList($("conceptSelect"), ["全部", ...concepts]);
  $("conceptSelect").value = concepts.includes(current) ? current : "全部";
}

function chooseExercise(id) {
  currentExercise = exercises.find((item) => item.id === id) || null;
  renderExercises();
  if (!currentExercise) {
    $("exerciseMeta").textContent = "无题目";
    $("exerciseTitle").textContent = "没有匹配题目";
    $("exercisePrompt").textContent = "请调整难度或题型筛选。";
    $("exerciseGuide").innerHTML = "";
    $("focusedSchemaView").innerHTML = "";
    renderTestCases([]);
    return;
  }
  $("exerciseMeta").textContent = `${currentExercise.difficulty} · ${currentExercise.kind}`;
  $("exerciseTitle").textContent = currentExercise.title;
  $("exercisePrompt").textContent = currentExercise.prompt;
  renderExerciseGuide(currentExercise);
  renderFocusedSchema(currentExercise);
  renderTestCases(currentExercise.test_cases || []);
  $("sqlInput").value = "";
  lastResult = null;
}

function renderExerciseGuide(exercise) {
  const tables = exercise.required_tables?.length ? exercise.required_tables : ["查看左侧 Schema"];
  const columns = exercise.output_columns?.length ? exercise.output_columns : ["按题目要求输出"];
  const steps = exercise.solution_steps?.length ? exercise.solution_steps : ["先观察样例数据，再逐步补全 SQL。"];
  $("exerciseGuide").innerHTML = `
    <div class="guide-box">
      <strong>需要关注的表</strong>
      <ul>${tables.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </div>
    <div class="guide-box">
      <strong>目标输出列</strong>
      <ul>${columns.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </div>
    <div class="guide-box">
      <strong>建议解题步骤</strong>
      <ul>${steps.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </div>
  `;
}

function renderFocusedSchema(exercise) {
  const root = $("focusedSchemaView");
  if (!schemaSnapshot || !exercise?.required_tables?.length) {
    root.innerHTML = '<div class="muted">请选择题目后查看相关表。</div>';
    return;
  }
  const tables = schemaSnapshot.tables.filter((table) => exercise.required_tables.includes(table.table));
  root.innerHTML = "";
  tables.forEach((table) => root.appendChild(schemaTableElement(table, true)));
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
    root.appendChild(schemaTableElement(table, false));
  });
}

function schemaTableElement(table, focused) {
  const box = document.createElement("div");
  box.className = "schema-table" + (focused ? " focused" : "");
  const columns = table.columns
    .map((column) => `${column.name} ${column.type}${column.pk ? " PK" : ""}`)
    .join(" · ");
  box.innerHTML = `<header>${table.table}</header><div class="columns">${columns}</div>`;
  const preview = document.createElement("div");
  preview.className = "table-wrap";
  preview.innerHTML = tableHtml(table.preview);
  box.appendChild(preview);
  return box;
}

async function submitAnswer() {
  if (!currentExercise) return;
  const sql = $("sqlInput").value;
  const data = await api("/api/answer", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, exercise_id: currentExercise.id, sql }),
  });
  lastResult = data;
  exerciseAttempts.set(currentExercise.id, { score: data.score, correct: data.correct });
  renderExercises();
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

function chooseRandomExercise() {
  const visibleExercises = filteredExercises();
  if (!visibleExercises.length) return;
  const next = visibleExercises[Math.floor(Math.random() * visibleExercises.length)];
  chooseExercise(next.id);
}

function recommendExercise() {
  const visibleExercises = filteredExercises();
  if (!visibleExercises.length) return;
  const unfinished = visibleExercises.find((exercise) => !exerciseAttempts.has(exercise.id));
  if (unfinished) {
    chooseExercise(unfinished.id);
    return;
  }
  const weakest = [...visibleExercises].sort((a, b) => {
    const scoreA = exerciseAttempts.get(a.id)?.score ?? 101;
    const scoreB = exerciseAttempts.get(b.id)?.score ?? 101;
    return scoreA - scoreB;
  })[0];
  chooseExercise(weakest.id);
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
  appendChatMessage("user", question);
  $("questionInput").value = "";
  const assistantBubble = appendChatMessage("assistant", "SQL Tutor Agent 正在思考...");
  try {
    await streamAgentAnswer(question, assistantBubble);
  } catch (error) {
    assistantBubble.textContent = `流式回复失败：${error.message}`;
  } finally {
    $("askBtn").disabled = false;
    $("askBtn").textContent = "提问";
  }
}

async function streamAgentAnswer(question, assistantBubble) {
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
        assistantBubble.textContent = `${tutorSourceLabel(event.source)}\n`;
        answerStarted = true;
      } else if (event.type === "delta") {
        if (!answerStarted) {
          assistantBubble.textContent = "";
          answerStarted = true;
        }
        assistantBubble.textContent += event.text;
        scrollChatToBottom();
      }
    }
  }

  if (buffer.trim()) {
    const event = JSON.parse(buffer);
    if (event.type === "delta") assistantBubble.textContent += event.text;
  }
  scrollChatToBottom();
}

function renderChatHistory(messages) {
  const root = $("chatMessages");
  root.innerHTML = "";
  if (!messages.length) {
    root.innerHTML = '<div class="chat-empty">可询问题目思路、表关系、聚合或 JOIN。</div>';
    return;
  }
  messages.forEach((message) => appendChatMessage(message.role, message.content));
}

function appendChatMessage(role, content) {
  const root = $("chatMessages");
  const empty = root.querySelector(".chat-empty");
  if (empty) root.innerHTML = "";
  const wrapper = document.createElement("div");
  wrapper.className = `chat-message ${role === "user" ? "user" : "assistant"}`;
  const label = document.createElement("div");
  label.className = "chat-role";
  label.textContent = role === "user" ? "你" : "SQL Tutor Agent";
  const bubble = document.createElement("div");
  bubble.className = "chat-bubble";
  bubble.textContent = content;
  wrapper.appendChild(label);
  wrapper.appendChild(bubble);
  root.appendChild(wrapper);
  scrollChatToBottom();
  return bubble;
}

function scrollChatToBottom() {
  const root = $("chatMessages");
  root.scrollTop = root.scrollHeight;
}

async function clearChat() {
  if (!sessionId) return;
  await api("/api/chat-clear", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
  renderChatHistory([]);
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
$("questionInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter") askAgent();
});
$("clearChatBtn").addEventListener("click", clearChat);
$("loadCaseBtn").addEventListener("click", loadTestCase);
$("runCaseBtn").addEventListener("click", runTestCase);
$("testCaseSelect").addEventListener("change", updateTestCaseNote);
$("searchInput").addEventListener("input", () => {
  renderExercises();
  if (!filteredExercises().some((exercise) => exercise.id === currentExercise?.id)) chooseExercise(filteredExercises()[0]?.id);
});
$("conceptSelect").addEventListener("change", () => {
  renderExercises();
  if (!filteredExercises().some((exercise) => exercise.id === currentExercise?.id)) chooseExercise(filteredExercises()[0]?.id);
});
$("randomBtn").addEventListener("click", chooseRandomExercise);
$("recommendBtn").addEventListener("click", recommendExercise);
$("difficultySelect").addEventListener("change", refreshExercises);
$("kindSelect").addEventListener("change", refreshExercises);
$("scenarioSelect").addEventListener("change", startSession);

init().catch((error) => {
  $("feedback").className = "feedback bad";
  $("feedback").textContent = error.message;
});
