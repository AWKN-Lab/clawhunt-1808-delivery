# AC0–AC8 对照表（#1808 任务 1/5）

状态口径：**已实现并实测** / **部分（本地实测、容器待 CI）** / **未实现**。

| AC | 要求 | 状态 | 实现与证据 |
|---|---|---|---|
| AC0 | 可运行成果 + 启动说明 | 已实现并实测 | `README.md` 三步法；`run.ps1` / `run.sh`；`app/main.py`；本机 Python 3.12.13 启动成功，`GET /api/v1/health` 返回 200 |
| AC1 | `docker compose up` 后 curl 完成 7 项报名，progress 7/7 + candidate 字段 | 部分（本地 HTTP 实测，容器待 CI） | 本地路径 `scripts/http_smoke.py` 真实 HTTP 7/7 + `docs/EVIDENCE.md` curl 回包；`tests/test_api_flow.py::test_seven_slot_booking_completes`；容器定义 `docker-compose.yml` / `Dockerfile`；本机 Docker daemon 不可用，未 `compose up` |
| AC2 | 评测集 ≥300、负面/边界 ≥30、一条命令输出 extraction≥95%、qa≥90%、violations=0 | 已实现并实测 | `eval/generate_cases.py`（seed 1808）、`eval/cases/*.jsonl`（210/45/30/15）、`eval/run.py`；实测 `extraction_accuracy=1.0`、`qa_accuracy=1.0`、`violations=0`；报告 `eval/report.json|md`；`tests/test_eval_cases.py`；另有独立手写留出集 `eval/cases/heldout.jsonl` + `eval/heldout_check.py`，报名 12/12、政策 10/10（见 EVIDENCE 3b） |
| AC3 | 未满 18 立即终止 `end_minor` | 已实现并实测 | `app/agent/minor.py`；`app/agent/engine.py`；`tests/test_resilience.py::test_minor_ends_immediately`；`tests/test_rules.py::test_age_gate_by_month`；评测 `minor=8/8`；口径按 kb-age-03 的月粒度（YYYY-MM），2008-11 边界见 EVIDENCE 3b |
| AC4 | 手机号/身份证不进入模型请求体；可回取原文 | 已实现并实测 | `app/agent/guardrails.py`（`redact_before_model`）、`app/agent/vault.py`、`app/agent/audit.py`；`tests/test_guardrails.py::test_pii_never_reaches_model_request`；评测 `pii_in_model_requests=0` |
| AC5 | 政策回答带出处；知识库未命中返回 handoff | 已实现并实测 | `kb/docs/*.md`（9 主题 27 chunk）；`app/agent/kb.py`；`tests/test_policy.py`（9 主题引用 + `kb_miss` handoff）；评测 `qa_accuracy=1.0` |
| AC6 | 模型超时降级且报名不中断 | 已实现并实测 | `app/llm/base.py`（timeout/error）、`app/agent/engine.py` 降级分支；`tests/test_resilience.py::test_model_fault_degrades_without_losing_progress`（参数 timeout/error） |
| AC7 | ≥10 条 prompt injection 全部拦截 | 已实现并实测 | `app/agent/guardrails.py` 15 类模式；`tests/test_guardrails.py::test_injection_is_blocked_without_model_call`（15 条参数化）；评测 `injection=15/15` |
| AC8 | 单测一条命令全绿 + 验证记录 | 已实现并实测 | `python -m pytest -q` → **100 passed**；`verify.ps1` / `verify.sh`；`VERIFICATION.md`；变异自证红/绿通过 |

## 未完成 / 未实跑清单

1. `docker compose up` 未在本机执行（daemon 不可用），CI 未推送因此容器 job 未实际运行。
2. 真实 DeepSeek/OpenAI 模型未联调（本机无 key，默认 mock）。
3. 前端界面、真实第三方渠道账号不在本任务范围。
