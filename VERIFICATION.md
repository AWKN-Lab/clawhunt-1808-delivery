# 验证记录（#1808 任务 1/5）

执行环境：Windows，Python 3.12.13（`.venv`），工作目录 `D:\AWKN-Lab\clawhunt\work\1808\repo`。
执行时间：2026-11-07（Asia/Shanghai）。

## 一键验证

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File verify.ps1
```

真实结果：`exit code 0`，最后一行 `VERIFY PASS`。链路为：

| 步骤 | 命令 | 结果 |
|---|---|---|
| pytest | `.venv\Scripts\python.exe -m pytest -q` | `100 passed, 1 warning in 9.01s`；STEP PASS |
| 评测 | `.venv\Scripts\python.exe -m eval.run` | `extraction_accuracy=1.0`、`qa_accuracy=1.0`、`violations=0`、`injection=15/15`、`minor=8/8`、`pii_in_model_requests=0`；`conclusion=PASS`；STEP PASS |
| 容器静态校验 | `python scripts\compose_check.py` | 13 项 OK，`COMPOSE STATIC PASS`；STEP PASS |
| HTTP 冒烟 | `python scripts\http_smoke.py` | 7/7 报名、candidate 齐全、`first_byte=46.8ms`、`first_char=46.8ms`；`SMOKE PASS`；STEP PASS |
| 变异自证 | `powershell -File scripts\mutation_proof.ps1` | `MUTATION RED` → `MUTATION GREEN` → `MUTATION PROOF PASS`；STEP PASS |

## 变异自证细节

变异对象：`app/agent/minor.py` 中 `return age_at(birth_ym, today) < 18` 改为 `return False`。

真实输出：

```
F                                                                        [100%]
FAILED tests/test_rules.py::test_age_gate_by_month - AssertionError: assert False
MUTATION RED (expected): 18-year gate test failed under mutation
.                                                                        [100%]
MUTATION GREEN (restored): 18-year gate test passed
MUTATION PROOF PASS
```

脚本在 `finally` 中恢复原文件；恢复后聚焦测试重新变绿，证明测试真的在约束该行为，而不是恒绿。

## 评测阈值（fail-closed）

`eval/run.py` 的退出码：

- `0`：全部闸门通过。
- `1`：`extraction_accuracy < 0.95`、`qa_accuracy < 0.90`、`violations > 0`、注入未全拦、未成年未即时终止、模型请求体出现 PII 中任一失败。
- `2`：用例构成不足（总数 < 300、负面 < 30、注入 < 10）。

本次实测退出码 `0`。用例构成：booking 210 / policy 45 / negative 30 / injection 15 = 300。

## PII 硬断言

`tests/test_guardrails.py::test_pii_never_reaches_model_request` 实际读取 `audit/model_requests.jsonl`，断言：

1. 每条模型请求 payload 中 `13800138000` 与 `110101199001011234` 出现次数为 0。
2. 手机号 token 通过 `/api/v1/vault/tokens/{token}` 可回取原文 `13800138000`。
3. SQLite `messages` 表中只存 `PHONE_TOKEN_*` / `NAME_TOKEN_*`，不存原文。

## 故障注入

`tests/test_resilience.py::test_model_fault_degrades_without_losing_progress` 以 `LLM_FAULT=timeout` 和 `LLM_FAULT=error` 各跑一遍：回复含降级前缀与 `handoff` action，`progress.done` 不清零，会话保持 `active` 可继续，最终仍能完成 7/7 报名。

## 未验证项（如实声明）

1. 本机 Docker daemon 不可用（`docker info` exit 1，npipe 连接失败），**未执行** `docker compose up`、未在容器内跑 7 项报名。
2. GitHub Actions workflow 已写入但未推送、未运行。
3. 真实 OpenAI 兼容模型未联调（默认 mock，不联网）。
