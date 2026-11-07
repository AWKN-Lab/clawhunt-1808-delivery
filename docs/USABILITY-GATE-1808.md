# 可用性闸门（#1808 任务 1/5）

判定口径：每闸只认本机真实执行结果；未执行的闸直接记 **FAIL**，不以静态校验冒充通过。

| # | 闸门 | 判定 | 实测命令 / 证据 |
|---|---|---|---|
| 1 | 可安装 | **PASS** | `.venv\Scripts\python.exe -m pip install -r requirements.txt` → exit 0（Python 3.12.13） |
| 2 | 可启动 | **PASS** | `.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`；`curl.exe /api/v1/health` → 200，`{"status":"ok","db":"ok","kb_docs":9,"kb_chunks":27}` |
| 3 | 首响 ≤2s、首字 ≤2.5s | **PASS** | `python scripts/http_smoke.py` → `first_byte=40.1ms first_char=40.1ms` |
| 4 | 7/7 报名闭环 | **PASS** | `python scripts/http_smoke.py` → `progress.done=7`、`actions=["booking_confirmed"]`、candidate 13 字段齐全；`tests/test_api_flow.py` |
| 5 | 容器一键起 | **PASS** | 2026-11-07 在 WSL2 Ubuntu 26.04 + Docker Engine 29.1.3 + Compose v2.40.3 实跑：`docker compose config` exit 0；`docker compose up --build --abort-on-container-exit` → UP_EXIT=0，api/postgres/redis 均 Up (healthy)；`docker compose exec -T api python scripts/ci_container_check.py` → 7/7、`actions=["booking_confirmed"]`、candidate 13 字段齐全、CONTAINER CHECK PASS（exit 0）；停止后退出码 api=0 / postgres=0 / redis=0 |

结论：**5 PASS / 0 FAIL**。容器闸以真实运行结果通过（Docker Engine 装于 WSL2 Ubuntu；GitHub Actions 仍未运行，不声称任何 CI run 号）。
