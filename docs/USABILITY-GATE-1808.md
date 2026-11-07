# 可用性闸门（#1808 任务 1/5）

判定口径：每闸只认本机真实执行结果；未执行的闸直接记 **FAIL**，不以静态校验冒充通过。

| # | 闸门 | 判定 | 实测命令 / 证据 |
|---|---|---|---|
| 1 | 可安装 | **PASS** | `.venv\Scripts\python.exe -m pip install -r requirements.txt` → exit 0（Python 3.12.13） |
| 2 | 可启动 | **PASS** | `.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`；`curl.exe /api/v1/health` → 200，`{"status":"ok","db":"ok","kb_docs":9,"kb_chunks":27}` |
| 3 | 首响 ≤2s、首字 ≤2.5s | **PASS** | `python scripts/http_smoke.py` → `first_byte=40.1ms first_char=40.1ms` |
| 4 | 7/7 报名闭环 | **PASS** | `python scripts/http_smoke.py` → `progress.done=7`、`actions=["booking_confirmed"]`、candidate 13 字段齐全；`tests/test_api_flow.py` |
| 5 | 容器一键起 | **FAIL** | 未执行 `docker compose up`。`docker info` 报 `failed to connect to the docker API ...`；仅完成 `docker compose config --quiet`(exit 0) 与 `scripts/compose_check.py` 静态校验。CI 未推送，容器 job 未运行 |

结论：**4 PASS / 1 FAIL**。容器闸 FAIL 的原因是本机 Docker daemon 不可用，不代表 compose 定义无效；但按“没实测写 FAIL”口径，不得记为通过。
