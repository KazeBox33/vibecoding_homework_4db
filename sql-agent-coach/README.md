# SQL Agent Coach

基于大模型 Agent 思路的 SQL 随身教练系统。项目包含可配置的 `JudgeAgent`：配置 LLM API 后由 Agent 参与 SQL 判题、评分和错因解释；未配置密钥时使用本地规则兜底，保证系统仍可离线运行。

## 功能

- 自动生成数据库 schema 和实例数据
- 按场景、题型、难度生成 SQL 练习题
- 每题展示相关表结构、目标输出列和建议解题步骤
- 支持关键词、知识点、随机选题和推荐下一题
- 执行并比对用户 SQL 与参考 SQL 的结果
- 接入 LLM Judge Agent 进行结构化判题裁决
- Agent 答疑保存同一 session 的多轮聊天上下文
- Agent 答疑支持流式回复，边生成边显示
- 每道题内置正确、错误、语法错误、安全拦截测试样例，可一键载入或运行
- 自动清理复制粘贴时带入的 ```sql Markdown 代码块
- 给出正确性判断、错误解析、提示和改进建议
- 记录练习历史，输出最终成绩与学习建议
- 提供本地浏览器 demo

## 从 GitHub 拉取后如何启动

### 1. 进入项目目录

如果你在仓库根目录：

```powershell
cd sql-agent-coach
```

如果你是在本机当前工程目录：

```powershell
cd "E:\New project\sql-agent-coach"
```

### 2. 检查 Python

项目默认只依赖 Python 标准库，无需安装额外依赖。建议 Python 3.10+：

```powershell
python --version
```

### 3. 启动本地服务

不配置 API Key 也可以运行，此时系统会使用本地规则兜底判题：

```powershell
python app.py
```

浏览器打开：

```text
http://127.0.0.1:8000
```

### 4. 页面使用流程

1. 选择数据场景，例如“电商订单”或“校园课程”。
2. 用难度、题型、关键词或知识点筛选题目，也可以随机选题。
3. 查看当前题目的相关表结构、样例数据、目标输出列和建议解题步骤。
4. 在 SQL 编辑区写答案，或从内置测试样例中选择正确/错误/语法错误/安全拦截样例。
5. 点击“提交判题”，系统会展示得分、错因、下一步建议、用户结果和参考结果。
6. 在 Agent 答疑区提问。Tutor Agent 会结合当前题目、schema 和同一 session 的历史对话回答。
7. 做完多道题后查看平均分、正确率和学习建议。

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

## 查看项目总结 PPT

仓库中还包含一份网页 PPT 汇报材料：

```text
docs/project-summary-ppt/index.html
```

直接用浏览器打开即可横向翻页演示：

- 左右方向键翻页
- `ESC` 打开索引
- `B` 切换静态模式

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
    function_flow_summary.md # 功能模块与流程图总结
  tests/
    test_agent.py
```
