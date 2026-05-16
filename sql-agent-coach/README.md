# SQL Agent Coach

基于大模型 Agent 思路的 SQL 随身教练系统。项目包含可配置的 `JudgeAgent`：配置 LLM API 后由 Agent 参与 SQL 判题、评分和错因解释；未配置密钥时使用本地规则兜底，保证系统仍可离线运行。

## 功能

- 自动生成数据库 schema 和实例数据
- 按场景、题型、难度生成 SQL 练习题
- 执行并比对用户 SQL 与参考 SQL 的结果
- 接入 LLM Judge Agent 进行结构化判题裁决
- Agent 答疑支持流式回复，边生成边显示
- 每道题内置正确、错误、语法错误、安全拦截测试样例，可一键载入或运行
- 给出正确性判断、错误解析、提示和改进建议
- 记录练习历史，输出最终成绩与学习建议
- 提供本地浏览器 demo

## 运行

```powershell
cd "E:\New project\sql-agent-coach"
python app.py
```

浏览器打开：

```text
http://127.0.0.1:8000
```

## 接入 LLM Judge Agent

默认情况下，系统不假装已经接入外部模型，而是在页面显示“本地兜底判题”。要启用真实 Agent 判题，启动前设置环境变量：

DeepSeek 推荐配置：

```powershell
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
$env:SQL_COACH_JUDGE_PROVIDER="deepseek"
$env:SQL_COACH_LLM_MODEL="deepseek-v4-flash"
$env:SQL_COACH_LLM_BASE_URL="https://api.deepseek.com"
python app.py
```

如果只设置 `DEEPSEEK_API_KEY`，系统也会自动使用 `deepseek-v4-flash` 和 `https://api.deepseek.com/chat/completions`。

通用 OpenAI-compatible 配置：

```powershell
$env:SQL_COACH_LLM_API_KEY="你的 API Key"
$env:SQL_COACH_LLM_MODEL="你的模型名"
$env:SQL_COACH_LLM_BASE_URL="https://api.openai.com/v1/chat/completions"
python app.py
```

启用后，判题反馈会显示 `LLM Judge Agent`。当前实现没有引入 LangChain；它是自定义 Agent 编排：SQLite 工具执行、结果差异构造、JudgeAgent 调用大模型返回结构化裁决。

## 测试

```powershell
cd "E:\New project\sql-agent-coach"
python -m unittest discover -s tests
```

## 目录

```text
sql-agent-coach/
  app.py                  # 本地 HTTP 服务与 API
  core/
    agent.py              # SQL Coach Agent 主逻辑
    judge_agent.py        # LLM Judge Agent 接入与本地兜底
    catalog.py            # 场景库、schema、样例数据、题库
  static/
    index.html            # Demo 前端
    app.js
    styles.css
  docs/
    technical_report.md   # 技术原理与架构报告
  tests/
    test_agent.py
```
