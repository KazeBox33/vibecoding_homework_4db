# SQL Agent Coach

基于大模型 Agent 的 SQL 辅助学习系统。项目面向 SQL 初学者和进阶练习者，围绕“生成数据库、生成题目、提交 SQL、Agent 判题、错因分析、学习建议”形成完整训练闭环。

本仓库为 `vibecoding_homework_4db` 作业项目，核心代码位于 [`sql-agent-coach/`](sql-agent-coach/)。

## 项目亮点

- **自动生成练习环境**：内置电商订单、校园课程两个业务场景，启动后自动创建 SQLite schema 与实例数据。
- **多类型 SQL 题目**：覆盖筛选查询、连接查询、聚合统计、子查询、窗口函数等题型。
- **题目可读性增强**：每题展示相关表结构、样例数据、目标输出列和建议解题步骤。
- **灵活题库选择**：支持按场景、难度、题型、知识点、关键词筛选，并可随机选题或推荐下一题。
- **Agent 判题闭环**：先执行参考 SQL 与用户 SQL，再把结构化结果差异交给 `JudgeAgent` 裁决。
- **DeepSeek / OpenAI-compatible 接入**：支持配置 DeepSeek API，默认模型可使用 `deepseek-v4-flash`。
- **会话型 Agent 答疑**：同一练习 session 会记录多轮聊天历史，Tutor Agent 会结合上下文理解追问。
- **流式 Agent 回复**：提问时通过流式接口逐段显示 Tutor Agent 回复。
- **可离线兜底运行**：未配置 API Key 时使用本地规则判题，确保系统可以稳定演示。
- **一键测试样例**：每道题内置正确、错误、语法错误、安全拦截样例，可直接载入或运行。
- **复制粘贴容错**：自动清理 ```sql Markdown 代码块包装，避免复制示例 SQL 后误判。
- **学习反馈与统计**：自动返回得分、错因解释、下一步建议、平均分和正确率。

## 效果预览

启动后访问本地页面：

```text
http://127.0.0.1:8000
```

页面包含：

- 左侧：场景选择、题目筛选、schema 与样例数据
- 中间：题目描述、相关表结构、解题步骤、测试样例、SQL 编辑区
- 右侧/下方：判题反馈、用户结果、参考结果、多轮 Agent 答疑

## 系统架构

```mermaid
flowchart LR
    U["用户"] --> UI["Web 前端"]
    UI --> API["Python HTTP API"]
    API --> A["SqlLearningAgent"]
    A --> C["Catalog 场景/题库"]
    A --> DB["SQLite 沙箱"]
    A --> E["Evaluator 结果差异"]
    E --> J["JudgeAgent"]
    J --> LLM["DeepSeek / OpenAI-compatible LLM"]
    J --> F["反馈与评分"]
    F --> UI
```

核心思路：

1. 系统为每个 session 创建独立 SQLite 内存数据库。
2. 用户提交 SQL 后，系统执行参考 SQL 与用户 SQL。
3. `Evaluator` 构造列、行、结果内容、执行错误等结构化信息。
4. `JudgeAgent` 调用大模型返回 JSON 裁决：`correct`、`score`、`feedback`、`next_steps`。
5. 如果没有配置外部模型，系统自动使用本地规则兜底。

## 快速开始

### 完整启动流程

下面流程适合第一次从 GitHub 拉取项目的使用者。

#### 1. 克隆仓库

```powershell
git clone git@github.com:KazeBox33/vibecoding_homework_4db.git
cd vibecoding_homework_4db\sql-agent-coach
```

如果没有配置 SSH，也可以使用 HTTPS：

```powershell
git clone https://github.com/KazeBox33/vibecoding_homework_4db.git
cd vibecoding_homework_4db\sql-agent-coach
```

#### 2. 检查 Python

项目默认只依赖 Python 标准库，无需安装额外依赖。建议使用 Python 3.10+：

```powershell
python --version
```

#### 3. 启动系统

不配置 API Key 也可以启动，此时系统会使用本地规则兜底判题：

```powershell
python app.py
```

看到服务启动后，在浏览器打开：

```text
http://127.0.0.1:8000
```

#### 4. 可选：启用真实 DeepSeek Agent

如果希望 Judge Agent 和 Tutor Agent 调用真实大模型，在同一个 PowerShell 窗口中先设置环境变量，再启动：

```powershell
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
$env:SQL_COACH_JUDGE_PROVIDER="deepseek"
$env:SQL_COACH_LLM_MODEL="deepseek-v4-flash"
$env:SQL_COACH_LLM_BASE_URL="https://api.deepseek.com"
python app.py
```

配置成功后，页面中的 Agent 状态会显示已启用 LLM Agent，判题反馈会标记 `LLM Judge Agent`。

#### 5. 页面使用流程

1. 在左侧选择数据场景，例如“电商订单”或“校园课程”。
2. 按难度、题型、关键词或知识点筛选题目，也可以随机选题。
3. 查看题目下方的相关表结构、样例数据、目标输出列和建议步骤。
4. 在 SQL 编辑区输入答案，或选择内置测试样例一键载入。
5. 点击“提交判题”，系统会执行参考 SQL 和用户 SQL，并给出得分、错因、结果对比和下一步建议。
6. 在 Agent 答疑区追问，例如“这题为什么要 GROUP BY？”或“我下一步应该怎么写？”。同一 session 的答疑会保留上下文。
7. 练习多题后查看平均分、正确率和学习建议。

## 接入 DeepSeek Judge Agent

如果希望真正使用大模型 Agent 判题，在启动前设置环境变量：

```powershell
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
$env:SQL_COACH_JUDGE_PROVIDER="deepseek"
$env:SQL_COACH_LLM_MODEL="deepseek-v4-flash"
$env:SQL_COACH_LLM_BASE_URL="https://api.deepseek.com"

python app.py
```

也可以只设置 `DEEPSEEK_API_KEY`，系统会自动选择 DeepSeek 默认配置：

```powershell
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
python app.py
```

启用后，前端 Agent 状态会显示 `LLM Agent 判题`，判题结果中会标记 `LLM Judge Agent`。

## 通用 OpenAI-Compatible 配置

如果使用其他兼容 Chat Completions 的服务：

```powershell
$env:SQL_COACH_LLM_API_KEY="你的 API Key"
$env:SQL_COACH_LLM_MODEL="你的模型名"
$env:SQL_COACH_LLM_BASE_URL="https://api.openai.com/v1/chat/completions"

python app.py
```

## 测试

运行单元测试：

```powershell
cd sql-agent-coach
python -m unittest discover -s tests
```

当前测试覆盖：

- schema 与样例数据生成
- 正确 SQL 判题
- 错误 SQL 反馈
- 非只读 SQL 安全拦截
- Judge Agent 接管判题
- DeepSeek 配置识别
- 前端测试样例数据返回

## 项目结构

```text
vibecoding_homework_4db/
  README.md
  sql-agent-coach/
    app.py
    core/
      agent.py
      catalog.py
      judge_agent.py
    static/
      index.html
      app.js
      styles.css
    docs/
      technical_report.md
      output.pptx
    tests/
      test_agent.py
```

## 关键文件

| 文件 | 说明 |
| --- | --- |
| `sql-agent-coach/app.py` | 本地 HTTP 服务与 API 路由 |
| `sql-agent-coach/core/agent.py` | 学习流程编排、题目生成、判题入口 |
| `sql-agent-coach/core/judge_agent.py` | DeepSeek / LLM Judge Agent 接入 |
| `sql-agent-coach/core/catalog.py` | 场景库、schema、样例数据、题库 |
| `sql-agent-coach/static/` | 浏览器交互界面 |
| `sql-agent-coach/docs/technical_report.md` | 技术原理与架构报告 |
| `sql-agent-coach/docs/function_flow_summary.md` | 功能模块与流程图总结 |
| `sql-agent-coach/docs/output.pptx` | 演示 PPT |

## 当前实现说明

当前没有引入 LangChain、OpenClaw 或 Hermes 作为运行时依赖，而是采用轻量自定义 Agent 编排：

- SQLite 作为工具执行层
- Evaluator 负责构造结果差异
- JudgeAgent 调用 DeepSeek 或 OpenAI-compatible 大模型
- 本地规则判题作为兜底策略

这种实现更轻量，便于本地运行和课堂演示。如果课程要求必须展示 LangChain 等框架，也可以把 `JudgeAgent` 替换为 LangChain `Runnable` 或 `AgentExecutor`。

## 安全策略

系统只允许执行 `SELECT` 或 `WITH` 开头的只读 SQL，并拦截：

- 多语句执行
- `DROP`
- `INSERT`
- `UPDATE`
- `DELETE`
- `ALTER`
- `CREATE`
- `ATTACH`
- `DETACH`

这样可以保证练习过程中不会破坏内存数据库。

## 交付内容

- 可运行 Web 系统
- DeepSeek Judge Agent 接入
- SQL 题库与测试样例
- 单元测试
- 技术报告
- 演示 PPT
