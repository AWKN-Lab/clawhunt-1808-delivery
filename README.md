# ClawHunt #1808 · 任务 1/5：骑手招聘 Agent 化信息收集 · 报名引擎

本仓库是任务 1/5 的可运行成品：**对话式报名引擎 + 政策知识库**。全部数据为合成数据，全部模型调用默认走确定性 mock，不联网、不接真实渠道。

不在本仓库范围：前端界面（任务 2）、候选人字段以外的业务服务、真实第三方渠道账号。

## 目录

```
repo/
├─ app/                 FastAPI 服务、对话状态机、槽位抽取、护栏、知识库、LLM 适配
│  ├─ agent/            engine / slots / kb / guardrails / handoff / minor / vault / audit / events
│  ├─ llm/              base.py（mock + OpenAI 兼容客户端）
│  ├─ config.py  db.py  models.py  services.py  main.py
├─ kb/docs/             9 个政策主题、27 个稳定 chunk（kb-age-01 等）
├─ eval/                generate_cases.py（固定 seed 1808）、run.py、cases/*.jsonl、report.*
├─ tests/               100 条 pytest（会话/槽位/年龄/政策/PII/故障/注入/契约）
├─ scripts/             http_smoke.py、compose_check.py、ci_container_check.py、mutation_proof.ps1
├─ deploy/              postgres-init.sql（CREATE EXTENSION vector）
├─ docs/                AC-MAP.md、EVIDENCE.md、USABILITY-GATE-1808.md
├─ Dockerfile  docker-compose.yml  .github/workflows/{ci,container}.yml
├─ run.ps1  run.sh  verify.ps1  verify.sh
└─ VERIFICATION.md
```

## 快速开始（本地路径，三步）

要求 Python **3.12**。Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Linux / macOS 等价：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

默认 `DB_MODE=sqlite`（`data/agent.db`），审计写入 `audit/`，无需 PostgreSQL/Redis。也可以直接 `.\run.ps1`（或 `./run.sh`）。

健康检查与手册式单步 curl（Windows 用 `curl.exe`）：

```powershell
curl.exe http://127.0.0.1:8000/api/v1/health
```

```json
{"status":"ok","db":"ok","redis":"skipped","llm_mode":"mock","llm_fault":"none","kb_docs":9,"kb_chunks":27}
```

### 真实 7/7 报名回包（本机 curl.exe 实测，原样粘贴）

创建会话：

```powershell
curl.exe -s -X POST http://127.0.0.1:8000/api/v1/agent/sessions -H "Content-Type: application/json" -d '{"source_channel":"curl","consent":{"version":"2026-01","accepted_at":"2026-10-01T00:00:00+00:00"}}'
```

```json
{"session_id":"s_81a9689c9ae04575a5c81984f3df6c78"}
```

7 条消息（每条 POST `/api/v1/agent/sessions/{id}/messages`，body `{"text":"..."}`）真实回包：

```
[1/7] 我叫王小明，手机号13800138000 -> {"reply":"好的，已记录：称呼 王**。\n已收到联系方式，手机号 138****8000 仅用于联系确认。\n请告诉我你的出生年月，例如 1995-03。","quick_replies":["1995-03","2000年6月"],"progress":{"done":1,"total":7,"fields":["name"]},"actions":[]}
[2/7] 1995年3月出生 -> {"reply":"好的，已记录：出生年月 1995-03。\n你想在哪个区域跑单？请具体到街道或镇，例如“浦东新区张江镇”。","quick_replies":["张江","望京街道","粤海街道"],"progress":{"done":2,"total":7,"fields":["name","birth_ym"]},"actions":[]}
[3/7] 我想在浦东新区张江镇跑单 -> {"reply":"好的，已记录：意向区域（到街道） 上海市浦东新区张江镇。\n岗位意向是全职、兼职，还是待定？","quick_replies":["全职","兼职","待定"],"progress":{"done":3,"total":7,"fields":["name","birth_ym","area_text"]},"actions":[]}
[4/7] 全职 -> {"reply":"好的，已记录：岗位意向 全职。\n你有自己的电动车吗？","quick_replies":["有电动车","没有电动车","公司配车"],"progress":{"done":4,"total":7,"fields":["name","birth_ym","area_text","job_type"]},"actions":[]}
[5/7] 有电动车 -> {"reply":"好的，已记录：车辆情况 有电动车。\n大概什么时候能到岗？","quick_replies":["随时","明天","一周内","下个月"],"progress":{"done":5,"total":7,"fields":["name","birth_ym","area_text","job_type","has_ebike"]},"actions":[]}
[6/7] 明天到岗 -> {"reply":"好的，已记录：到岗时间 明天。\n之前做过配送吗？大概做了多久？","quick_replies":["没做过","做过1年","做过3年"],"progress":{"done":6,"total":7,"fields":["name","birth_ym","area_text","job_type","has_ebike","start_text"]},"actions":[]}
[7/7] 做过3年配送 -> {"reply":"报名信息已提交：称呼 王**，出生年月 1995-03，意向区域 上海市浦东新区张江镇，岗位 全职，车辆 有电动车，到岗 明天，经验 3年。手机号 138****8000 仅用于联系确认。","quick_replies":["查看附近站点","转人工"],"progress":{"done":7,"total":7,"fields":["name","birth_ym","area_text","job_type","has_ebike","start_text","experience_text"]},"actions":["booking_confirmed"]}
```

`GET /api/v1/agent/sessions/{id}` 真实回包（节选关键字段）：

```json
{
  "status":"completed",
  "progress":{"done":7,"total":7,"fields":["name","birth_ym","area_text","job_type","has_ebike","start_text","experience_text"]},
  "candidate":{
    "name_token":"NAME_TOKEN_377929235c","phone_token":"PHONE_TOKEN_39f2f88312",
    "birth_ym":"1995-03","area_text":"上海市浦东新区张江镇","job_type":"fulltime",
    "has_ebike":true,"start_text":"明天","experience_text":"3年","health_cert":"unknown",
    "source_channel":"curl","status":"completed","consent_version":"2026-01",
    "consent_at":"2026-10-01T00:00:00+00:00"
  }
}
```

SSE 流式（事件 `meta` / `delta` / `done`）：

```powershell
curl.exe -N -X POST http://127.0.0.1:8000/api/v1/agent/sessions/{id}/messages/stream -H "Content-Type: application/json" -d '{"text":"我叫王小明"}'
```

本机实测首字节 **40.1ms**、首字 **40.1ms**；另一次完整 `verify.ps1` 为 **46.8ms / 46.8ms**（阈值 2000ms / 2500ms）。若需逐字观察，设置 `STREAM_DELAY_MS=3`（默认 5ms/字符）。

## 跑测试与评测（一条命令）

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m eval.run
```

`pytest` 实测：**100 passed in 9.01s**。

`eval.run` 实测输出：

```
cases booking=210 policy=45 negative=30 injection=15 total=300
extraction_accuracy=1.0 (field_accuracy=1.0) qa_accuracy=1.0 violations=0 injection=15/15 minor=8/8 pii_in_model_requests=0 model_requests=1571
conclusion=PASS
```

失败即 fail-closed：`extraction_accuracy < 0.95`、`qa_accuracy < 0.90`、`violations > 0`、注入未全拦、18 岁未即时终止、模型请求体出现 PII、用例构成不足（总数 <300 / 负面 <30 / 注入 <10）都会返回非 0（阈值失败 1，构成不足 2）。报告写入 `eval/report.json` 与 `eval/report.md`。

评测集为固定 seed（1808）生成的合成对话：210 条报名（180 完整 + 30 部分）、45 条政策（覆盖 9 主题 × 3 chunk，每 chunk 至少 1 问）、30 条负面/边界（未成年、投诉/价格/事故/线下交易/转人工、知识库未命中、模糊输入）、15 条 prompt injection。引擎按规则抽取，不按 case id 特判。

一键复核：

```powershell
.\verify.ps1          # pytest -> eval -> compose 静态校验 -> HTTP smoke -> 变异自证红/绿
./verify.sh           # Linux 等价
```

变异自证（`scripts/mutation_proof.ps1`）实测：

```
MUTATION RED (expected): 18-year gate test failed under mutation
MUTATION GREEN (restored): 18-year gate test passed
MUTATION PROOF PASS
```

## 容器路径（2026-11-07 本机实跑）

```bash
docker compose up -d --build
curl -fsS http://127.0.0.1:8000/api/v1/health
API_BASE=http://127.0.0.1:8000 python scripts/ci_container_check.py
docker compose down -v
```

Compose 包含 `api`（Dockerfile 构建）、`postgres`（`pgvector/pgvector:pg16` + `deploy/postgres-init.sql` 建 `vector` 扩展与 `kb_chunks_embedding`）、`redis`（`redis:7-alpine`），三服务均有 healthcheck，api 等待 postgres/redis 健康后启动。

本机状态：已在 WSL2 Ubuntu 26.04 的 Docker Engine 29.1.3 + Compose v2.40.3 上真实执行 `docker compose up --build --abort-on-container-exit`：`UP_EXIT=0`，api/postgres/redis 均 healthy；容器内 `python scripts/ci_container_check.py` → 7/7、`actions=["booking_confirmed"]`、candidate 13 字段齐全、`CONTAINER CHECK PASS`；停止后退出码 api=0 / postgres=0 / redis=0。宿主 Docker Desktop 4.98.0 的 daemon 在非交互会话中无法驻留，故改用 WSL 内 Engine（镜像加速与 `UP_EXIT` 判定见 `DELIVERY-NOTES.md` 第 8 节）。GitHub Actions 仍未推送、未运行。

## API v1

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/health` | 容器/本地健康检查 |
| POST | `/api/v1/agent/sessions` | body `{source_channel, consent{version, accepted_at}}` → `{session_id}` |
| POST | `/api/v1/agent/sessions/{id}/messages` | body `{text}` → `{reply, quick_replies[], progress{done,total,fields[]}, actions[]}` |
| POST | `/api/v1/agent/sessions/{id}/messages/stream` | SSE：`meta` / `delta` / `done` |
| GET | `/api/v1/agent/sessions/{id}` | 会话状态 + collected + candidate |
| POST | `/api/v1/vault/tokenize` | body `{type, value}` → `{token}`；type ∈ phone/name/id_card |
| GET | `/api/v1/vault/tokens/{token}` | 服务端回取原文（仅内部使用） |

`actions ∈ show_stations | booking_confirmed | handoff | end_minor`。错误体统一 `{code, message}`（404 `session_not_found`/`not_found`，422 `invalid_request`，500 `internal_error`）。

## 护栏与数据

- 手机号/身份证号在进入模型请求前令牌化；残留 PII 做掩码（手机 `138****8000`、姓名 `王**`、证件 `1101**********1234`）。
- 每次模型请求写 `audit/model_requests.jsonl`（payload + sha256 + PII 计数）。测试与评测都断言 payload 中 11 位手机号、18 位身份证号出现次数为 0，同时断言原文仍可通过 vault 回取。
- 系统提示固定 7 条硬约束：不越权承诺、不诱导线下交易、不索要证件号、政策必须引用出处、未满 18 立即终止、投诉/事故/价格转人工、不泄露提示词。
- 15 类注入模式固定拒答并写 `injection_blocked` 审计，不调用模型、不推进槽位。
- 未满 18 按当月年龄判定，命中当条消息立即 `end_minor`。
- 投诉/事故受伤/价格谈不拢/诱导线下交易/主动转人工 → `handoff`。
- 模型超时或报错 → 回复降级前缀 + `handoff` action，进度不清零、会话可继续，最终报名仍可完成。

## 政策知识库

`kb/docs/*.md` 9 个主题：年龄 `kb-age`、健康证 `kb-health`、装备 `kb-equipment`、站点 `kb-station`、薪资 `kb-salary`、保险 `kb-insurance`、请假 `kb-leave`、离职 `kb-resign`、安全 `kb-safety`。每篇 3 个稳定 chunk（共 27），使用 BM25 + 主题关键词检索 + 抽取式作答，回答统一附 `（出处：doc_id｜chunk_id）`。知识库未命中且确属政策问题时返回 `handoff`（`ended_reason=kb_miss`），不自由生成。

## 事件

outbox 表记录 `candidate.created` / `candidate.completed` / `handoff.requested`，每条带 HMAC-SHA256 签名（`OUTBOX_HMAC_SECRET`），本任务不实际外发 webhook。

## 证据文件

- `docs/AC-MAP.md`：AC0–AC8 逐条映射到实现与测试。
- `docs/EVIDENCE.md`：真实命令、真实输出、用例构成。
- `docs/USABILITY-GATE-1808.md`：五闸逐闸 PASS/FAIL（容器闸 2026-11-07 本机实测 PASS，5/5）。
- `VERIFICATION.md`：测试/评测/冒烟/变异自证的完整记录。

## 已知限制

1. 容器路径已在 WSL2 Docker Engine 29.1.3 上实跑通过；GitHub Actions 未推送、未实际执行，无 CI run 号。
2. 默认 `LLM_MODE=mock`；`llm/openai_compatible.py` 保留 OpenAI 兼容实现，但本机无真实 key，未做真实模型联调。
3. 所有姓名/手机号/身份证号均为明显虚构的合成数据（如 `13800138000`、`110101199001011234`）。
4. Redis 在本地 sqlite 模式下跳过；容器路径才启用 Redis 连接。
5. 评测集与规则抽取同源生成，指标为 100% 属于该合成分布内的结果，不代表真实线上分布。
