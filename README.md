# Skill Expert Agent

> Skill 专家智能体 — 你反复跟 AI 强调的那些规矩，该有个地方存下来

粘一段对话，收成一份能直接放进项目的 `SKILL.md`：
要求按四类归档、每条都指得回原话、出门前过一遍 14 项体检、一键落地到 Claude Code / ChatGPT / 通用短版。
再粘一段，它变成第二版。

**默认零依赖跑通**：内置规则引擎，不联网、不要 Key、无成本。配上 API Key 自动切到模型。

---

## 内置案例

三段不同行业的真实感对话，点开就能试：

| 案例 | 痛点 | 产出 |
|---|---|---|
| 客服回复话术 | 十个客服十种说法，体验全靠运气 | `support-reply-rules` |
| 数据口径对齐 | 同一个 GMV，三个部门报出三个数 | `data-report-rules` |
| 面试评估标准 | 评价表上全是「感觉不错」，复盘时查无实据 | `hiring-rules` |

选这三类，是因为它们最容易"人一走，规矩就散"，也最少被人系统地沉淀下来。

---

## 快速开始

```bash
# 1) 建虚拟环境
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2) 装依赖
pip install -e .

# 3) 起服务
python run.py                    # 或 uvicorn app.main:app --reload --port 8100

# 4) 打开
# http://127.0.0.1:8100
```

首次启动会自动建 `data/sea.db`。想换模型，把 `.env.example` 复制成 `.env` 再填 Key：

```bash
cp .env.example .env
# 编辑 .env，填 SEA_LLM_API_KEY / SEA_LLM_MODEL
```

支持任何 OpenAI 兼容端点：OpenRouter / DeepSeek / 智谱 / 本地 vLLM。
Key 为空时 `SEA_PROVIDER=auto` 会自动落回规则引擎，不会报错。

---

## 这个项目在做什么

人对着 AI 说的话，去掉闲聊和任务请求，剩下的期待只分四种：

| 类型 | 例子 | 决定什么 |
|---|---|---|
| 偏好 `preference` | "语气克制一点"、"别太正式" | 像不像你 |
| 约束 `constraint` | "不要出现「大概」"、"必须复述问题" | 能不能用 |
| 工作流 `workflow` | "先道歉再给方案"、"先核总数再发" | 按不按顺序 |
| 示例 `example` | "反例是…正例是…"、"照这句的写法" | 分歧时听谁的 |

四类刚好落进 `SKILL.md` 的三段正文，所以聚类和字段映射是同一步的两面。

### 五步流水线

| 步 | 做什么 | 实现 |
|---|---|---|
| 1 圈句 | 从人类发言里切句、过滤寒暄与任务请求、四类打标 | `core/signals.py` |
| 2 归档 | 语义归一 + 确定性去重，跨桶冲突时约束优先 | `core/clusters.py` |
| 3 落格 | 四桶 → body 四段 | `core/compose.py` |
| 4 成稿 | name → description → body 逐字段产出 | `core/pipeline.py` |
| 5 体检 | 12 条格式规则 + 2 条语义规则 | `core/lint.py` |

整个过程通过 SSE 实时推送，前端不是定时器动画，是真的字段到达。

### 14 条校验规则

12 条格式（name kebab-case / 保留词 / description 双焦点 / body 长度与 H1）+ 2 条语义：

- `signal-unverified` — 原句在对话里找不到对应片段，可能是模型自造
- `rule-conflict` — 两条约束语义互斥（"必须用 X" vs "禁止 X"）

`signal-unverified` 是整套系统里唯一能真正拦住幻觉的机制：每条信号都带 `quote`，
必须能在原文里定位（模糊匹配 ≥ 0.82）。没有溯源的"AI 提炼"，本质上是让模型写一篇关于你的开放作文。

### 版本累积

同一个 skill 再次提炼时：

- `sid` 精匹配（同一句话 → 同一个 sid）
- 文本相似度模糊匹配（≥ 0.80 → 视为同一规则）
- 认不出来的 → 新增
- **旧版有、新版没提到的 → 只标记 `orphan`，不删除**

最后一条是硬原则。误删一条约束的代价，远高于多留一条：多留只是啰嗦，误删会让 AI 重新犯你纠正过的错。

---

## 目录结构

```
app/
  main.py            FastAPI 入口
  config.py          pydantic-settings 配置
  db.py              SQLAlchemy 引擎、表定义、建表
  repo.py            数据访问（runs / events / skills / versions）
  schemas.py         领域模型（Signal / Clusters / Skill / Issue）
  samples.py         三个内置示例对话
  core/
    preprocess.py    清洗、脱敏、说话人切分、token 估算
    signals.py       规则引擎：切句 → 打分 → 分型 → 去重
    clusters.py      四类归并
    compose.py       命名 / description / body 生成
    lint.py          12 + 2 条校验
    merge.py         版本合并与 diff
    export.py        三端导出
    quote_check.py   原句溯源
    llm.py           模型调用（OpenAI 兼容）
    pipeline.py      五段编排 + 事件发射
    bus.py           进程内事件总线
  api/               runs / skills / pages
  templates/         Jinja2 页面 + 导出模板
  static/            app.css / app.js（原生 JS，无构建链）
tests/               46 个用例
```

---

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/runs` | `{conversation, base_skill_id?}` → `{run_id}` |
| `GET` | `/api/runs/{id}/stream` | SSE，支持 `Last-Event-ID` 重放 |
| `GET` | `/api/runs/{id}` | 当前快照 |
| `GET` | `/api/runs/{id}/preview?format=` | 不落库预览导出物 |
| `GET` | `/api/runs/{id}/export?format=` | 不落库直接下载 |
| `POST` | `/api/runs/{id}/save` | 落库为版本 |
| `GET` | `/api/skills` | 列表 |
| `GET` | `/api/skills/{id}/versions` | 版本列表 |
| `GET` | `/api/skills/{id}/export?format=` | 下载（claude-code / chatgpt / memory） |
| `DELETE` | `/api/skills/{id}` | 删除 |

SSE 事件：`stage` / `signal` / `cluster` / `field` / `delta` / `diff` / `lint` / `notice` / `done` / `error`。
事件先落库再推送，`Last-Event-ID` 可重放，刷新页面不丢进度。

---

## 测试

```bash
pytest -q
```

46 个用例，覆盖：14 条 lint 规则、信号抽取与去重、版本合并（含"默认不删"）、三端导出、完整五段流水线、噪音拒绝。

---

## 与参考实现的差别

本项目对标 [赋范空间 Skill Distiller](https://www.beyondata.com/playground/skill-distiller) 的方法论，
但那边是纯前端演示（4 个预置 fixture + `setTimeout` 假流式），这里是真引擎：

| 维度 | 参考实现 | 本项目 |
|---|---|---|
| 案例剧本 | 写作 / 代码规范 / 设计规范 | 客服话术 / 数据口径 / 面试评估 |
| 提炼 | 预置数据回放 | 规则引擎 / 模型，真解析 |
| 流式 | `setTimeout` 伪造 | SSE 真实字段到达 |
| 防幻觉 | 无 | `quote` 溯源校验 |
| 存储 | localStorage | SQLite + 不可变版本表 |
| 累积 | 预置 v2 数据 | sid + 相似度匹配 + 三层 diff |
| 长对话 | 不支持 | 截断保头保尾 + 提示 |
| 断线恢复 | 无 | 事件落库 + 重放 |

> 只借用了公开的方法论（SKILL.md 的三层加载机制、四类要求的分型思路），
> 案例剧本、界面文案、代码与数据结构均为重写。界面上那套"五幕舞台剧 / 三色灯 / 调教信号"
> 的表述已全部换成本项目的说法（圈句、归档、落格、体检）。

---

## 已知限制

- 规则引擎是启发式的：中文短句效果好，长段落和口语化极强的内容会漏抽。真实场景建议配 Key 走模型。
- 没有多用户 / 权限，是单机自用工具。
- SQLite 单文件，写入是串行的。真要多人用，把 `SEA_DB_URL` 换成 Postgres。
- 长对话目前用"保头保尾"截断，还没做滑窗 map-reduce（见 roadmap）。

## Roadmap

- [ ] 长对话滑窗 + 跨窗口冲突消解
- [ ] embedding 去重（替换字符 bigram，远程语义重复更准）
- [ ] 累积时的规则冲突人工确认 UI
- [ ] Postgres + 多用户
- [ ] CLI：`sea distill conversation.txt -o ./skills`
