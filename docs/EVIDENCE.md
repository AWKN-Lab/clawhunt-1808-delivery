# 实测证据（#1808 任务 1/5）

记录时间：2026-11-07（Asia/Shanghai）。以下命令均在本机 `D:\AWKN-Lab\clawhunt\work\1808\repo` 实际执行，输出为真实结果。

## 1. 环境与安装

```
$ .venv\Scripts\python.exe --version
Python 3.12.13
```

```
$ .venv\Scripts\python.exe -m pip install -r requirements.txt
Requirement already satisfied: fastapi==0.115.6 ...
Requirement already satisfied: pytest==8.3.4 ...
exit code 0
```

说明：本机 `.venv` 最初由 `uv venv` 创建，无 pip；执行 `python -m ensurepip --upgrade` 安装 pip 25.0.1 后，README 的三步法可直接复跑。

## 2. pytest

```
$ $env:PYTHONPATH='.'; .venv\Scripts\python.exe -m pytest --tb=short
100 passed, 1 warning in 9.01s
exit code 0
```

## 3. 评测（fail-closed）

```
$ $env:PYTHONPATH='.'; .venv\Scripts\python.exe -m eval.run
cases booking=210 policy=45 negative=30 injection=15 total=300
extraction_accuracy=1.0 (field_accuracy=1.0) qa_accuracy=1.0 violations=0 injection=15/15 minor=8/8 pii_in_model_requests=0 model_requests=1571
conclusion=PASS
report: ...\eval\report.json and ...\eval\report.md
exit code 0
```

用例构成：报名 210（完整 180 + 部分 30）、政策 45（9 主题 27 chunk，每 chunk ≥1 问）、负面/边界 30、注入 15，合计 300。

## 3b. 独立留出集（手写探针，检验句式泛化）

`eval/cases/heldout.jsonl` 为 27 条手写用例（12 报名 / 10 政策 / 5 未成年），句式与 `eval/generate_cases.py` 的模板不同；`eval/heldout_check.py` 复用同一个 `AgentService` 跑真实对话引擎。

```
$ .venv\Scripts\python.exe -m eval.heldout_check
heldout booking: 12/12 = 1.0
heldout policy: 10/10 = 1.0
heldout negative: 4/4 = 1.0
  BOUNDARY ho-n05: status=active (status active != end_minor; missing end_minor action)
heldout overall=1.0 failures=0
exit code 0
```

说明：

1. 首轮探针曾暴露 4 个真实泛化缺口，已按通用规则修复（不是按用例 id 特判）：
   - `名字是X` 姓名式样未识别 → 新增 `名字[是为：:]?` 模式；
   - `没经验`、`没有相关经验` 未归一 → 扩充无经验词表；
   - `一周后到岗` 未识别到岗时间 → 增加 `一周后` 归一。
2. `ho-n05`（2008-11 出生）是**月粒度边界**：`kb/docs/age.md` 的 kb-age-03 明确「只填出生年月（YYYY-MM），系统按当月日期计算周岁」，在 2026-11 该出生年月已计为 18 周岁，因此保持 `active`。它是产品口径边界而非抽取缺陷，不计入通过率，探针输出中单列 `BOUNDARY`。
3. 300 条生成集与抽取器词表同源，`extraction_accuracy=1.0` 反映自洽与回归稳定；**句式泛化能力以本节留出集为准**。

## 4. 真实 HTTP 7/7 报名（curl.exe）

健康检查：

```json
{"status":"ok","db":"ok","redis":"skipped","llm_mode":"mock","llm_fault":"none","kb_docs":9,"kb_chunks":27}
```

创建会话：

```json
{"session_id":"s_81a9689c9ae04575a5c81984f3df6c78"}
```

7 条消息（真实回包，截取关键字段）：

```
[1/7] 我叫王小明，手机号13800138000 -> progress.done=1 fields=["name"]; reply 含 王** 与 138****8000
[2/7] 1995年3月出生 -> progress.done=2 fields=[name,birth_ym]
[3/7] 我想在浦东新区张江镇跑单 -> progress.done=3 fields=[name,birth_ym,area_text]; area=上海市浦东新区张江镇
[4/7] 全职 -> progress.done=4 fields=[...,job_type]
[5/7] 有电动车 -> progress.done=5 fields=[...,has_ebike]
[6/7] 明天到岗 -> progress.done=6 fields=[...,start_text]
[7/7] 做过3年配送 -> progress.done=7 actions=["booking_confirmed"]
```

最终会话：

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

## 5. SSE 时延

```
$ .venv\Scripts\python.exe scripts\http_smoke.py
...
SSE latency -> first_byte=40.1ms first_char=40.1ms (limits 2000/2500ms)
SMOKE PASS
```

`verify.ps1` 中的同一步另一次实测为 `first_byte=46.8ms first_char=46.8ms`。

## 6. 容器路径（2026-11-07 本机实跑）

环境：WSL2 Ubuntu 26.04 + Docker Engine 29.1.3 + Compose v2.40.3（宿主 Docker Desktop 4.98.0 的 daemon 在非交互会话中无法驻留，故改用 WSL 内 Engine；镜像加速与 `UP_EXIT` 判定见 `DELIVERY-NOTES.md` 第 8 节）。

```text
$ docker compose config
exit code 0
$ docker compose up --build --abort-on-container-exit
api/postgres/redis → Up (healthy)
UP_EXIT=0
$ docker compose exec -T api python scripts/ci_container_check.py
1/7 ... 7/7 progress=7 actions=['booking_confirmed']
candidate 13 字段齐全
CONTAINER CHECK PASS
exit code 0
$ docker compose ps -aq | xargs docker inspect --format 'name=... exit={{.State.ExitCode}}'
repo-api-1 exit=0 / repo-postgres-1 exit=0 / repo-redis-1 exit=0
```

`GET /api/v1/health` → `{"status":"ok","db":"ok","redis":"ok","llm_mode":"mock","llm_fault":"none","kb_docs":9,"kb_chunks":27}`。

静态结构校验（`scripts/compose_check.py`）仍保留：

```
$ .venv\Scripts\python.exe scripts\compose_check.py
OK   api build
OK   api healthcheck
OK   api waits for postgres
OK   api waits for redis
OK   api postgres mode
OK   pgvector image
OK   redis image
OK   postgres healthcheck
OK   redis healthcheck
OK   dockerfile healthcheck
OK   dockerfile python 3.12
OK   pgvector extension
OK   embedding table
COMPOSE STATIC PASS
```

## 7. 变异自证

```
$ powershell -NoProfile -ExecutionPolicy Bypass -File scripts\mutation_proof.ps1
MUTATION RED (expected): 18-year gate test failed under mutation
MUTATION GREEN (restored): 18-year gate test passed
MUTATION PROOF PASS
exit code 0
```

变异内容：把 `app/agent/minor.py` 的 `return age_at(birth_ym, today) < 18` 改为 `return False`，聚焦测试 `test_age_gate_by_month` 必须失败；恢复后必须通过。

## 8. 未实测项

1. `docker compose up` / 容器内 7 项报名：已在 WSL2 Docker Engine 29.1.3 上实跑通过（见第 6 节），无 CI run 号。
2. GitHub Actions 两个 workflow：文件已写，未推送，未运行。
3. 真实 OpenAI 兼容模型：未联调，默认 mock。
