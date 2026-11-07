# #1808 交付说明（任务 1/5：骑手报名对话引擎 + 政策知识库 + 评测）

> 验收口径：**本地可复跑证据为准**。本轮不启用 GitHub Actions，不声称任何 CI run 号。

## 1. 交付物

| 项 | 值 |
|---|---|
| 远端仓库 | https://github.com/AWKN-Lab/clawhunt-1808-delivery |
| 分支 / 基线 SHA（本轮更正前） | `master` / `a7b8d9f8f64004665eb40e47c7f42149b9499a09` |
| 远端文件数 | 69（不含 `.github/workflows/*`；本轮新增本说明） |
| 本地工程 | `D:\AWKN-Lab\clawhunt\work\1808\repo` |
| 技术栈 | Python 3.12 + FastAPI（契约 v1）+ SQLite（评测）/ PostgreSQL 16 + pgvector（compose）+ Redis（compose）+ mock LLM；Docker Compose |

## 2. 启动与复跑（README 三步法）

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- 等价一键脚本：`.\run.ps1`
- 一键验收：`.\verify.ps1` → **VERIFY PASS，exit 0**
- 真实 HTTP 冒烟：`$env:PYTHONPATH='.'; .\.venv\Scripts\python.exe scripts\http_smoke.py` → **7/7 + SMOKE PASS**

## 3. 本地实测证据

| 项 | 实测结果 |
|---|---|
| 单元测试 | **100 passed**，exit 0 |
| 评测集（fail-closed） | **300 条**（booking 210 / policy 45 / negative 30 / injection 15） |
| 字段抽取准确率 | **1.0**（门槛 ≥0.95） |
| 政策问答正确率 | **1.0**（门槛 ≥0.90） |
| 违规输出 | **0**（门槛 0） |
| 提示词注入拦截 | **15/15**（门槛 ≥10 全拦截） |
| 未成年立即终止 | **8/8** |
| PII 进模型请求 | **0** |
| 手写留出集（泛化探针） | **26/26**：报名 12/12、政策 10/10、负面 4/4；1 条月粒度边界单列（见下） |
| 真实 HTTP 报名 | **7/7**，`progress.done=7`，`actions=["booking_confirmed"]`，candidate 13 字段齐全 |
| SSE 首字节 | **49.0ms**（门槛 ≤2000ms） |
| 变异自证 | RED（改 `is_minor` 必红）→ GREEN（恢复必绿） |

### 3b. 容器路径实测（2026-11-07 补测）

执行目录：`D:\AWKN-Lab\clawhunt\work\1808\repo`（`delivery\1808` 目录只含交付说明与 CI 附件，compose 定义位于工程仓库）。

```text
docker compose config                                    → exit 0
docker compose up --build --abort-on-container-exit      → UP_EXIT=0
api / postgres / redis                                   → Up (healthy)
GET /api/v1/health                                       → 200 {"status":"ok","db":"ok","redis":"ok","llm_mode":"mock","llm_fault":"none","kb_docs":9,"kb_chunks":27}
docker compose exec -T api python scripts/ci_container_check.py
                                                         → 7/7 progress=7 actions=['booking_confirmed']；candidate 13 字段齐全；CONTAINER CHECK PASS（exit 0）
docker compose stop 后各容器退出码                        → api=0 / postgres=0 / redis=0
```

运行环境：WSL2 Ubuntu 26.04 内 Docker Engine 29.1.3（`apt install docker.io`）+ Docker Compose v2.40.3；`docker version` Client/Server 均 29.1.3，API 1.52（linux/amd64）；`docker run --rm hello-world` exit 0。

证据文件（仓库相对路径）：

- `docs/EVIDENCE.md`（第 3 节 300 条评测、第 3b 节独立留出集）
- `docs/AC-MAP.md`、`docs/USABILITY-GATE-1808.md`、`VERIFICATION.md`
- `eval/report.json`、`eval/report.md`
- `eval/cases/heldout.jsonl`、`eval/heldout_check.py`
- `tests/`、`scripts/http_smoke.py`

## 4. AC 状态：9/9

| AC | 状态 | 说明 |
|---|---|---|
| AC0 成果优先 | PASS | 公开仓 + README 三步法 + 一键验收 |
| AC1 7 项报名闭环 | PASS | 本地真实 HTTP 7/7；容器内 `ci_container_check.py` 7/7 + `booking_confirmed`，两条路径均通过 |
| AC2 评测集 ≥300 / 负面 ≥30 | PASS | 300 条，指标全部达门槛 |
| AC3 未成年立即终止 | PASS | 8/8 + 即时性断言 |
| AC4 PII 不进模型 | PASS | 审计日志扫描 0 命中 |
| AC5 政策带出处 / 未命中转人工 | PASS | 引用断言 + 未命中用例 |
| AC6 模型故障降级 | PASS | 超时/错误注入单测 |
| AC7 注入拦截 | PASS | 15/15 |
| AC8 单测一条命令全绿 | PASS | pytest + verify.ps1 + 变异自证 |

## 5. 必须如实写的限制

1. **GitHub Actions 未运行**：workflow 未推送，没有任何 run 号；本说明中的数字全部来自本机执行。
2. **容器 job 已在本机执行（GitHub Actions 仍未运行）**：2026-11-07 在 WSL2 Ubuntu 26.04 内安装 Docker Engine 29.1.3 + Compose v2.40.3，`docker compose up --build` 真实启动 api/postgres/redis 并通过容器内 7/7 验收；仍**没有**任何 CI run 号。
3. **USABILITY_GATE 5/5**：容器闸已按真实运行结果改为 PASS（见 `docs/USABILITY-GATE-1808.md`）。
4. **AC 9/9**：AC1 的本地 HTTP 与容器两条路径均实测通过。
5. **300 条评测集的定性**：为固定种子合成集，词表与抽取器同源，1.0 仅代表自洽与回归稳定；**句式泛化能力以 27 条手写留出集（26/26）为准**。
6. **留出集边界项**：`ho-n05`（2008-11 出生）按知识库 kb-age-03 的月粒度口径（YYYY-MM，按当月计周岁）在 2026-11 已满 18，故保持 `active`；该项作为口径边界单列，不计入通过率。
7. **模型**：默认 mock LLM；真实大模型接入未实测。

## 6. 未启用的 CI 附件

`D:\AWKN-Lab\clawhunt\work\delivery\1808\workflows\`
- `ci.yml`、`container.yml`：**已备好、未推送、未启用**（说明见同目录 `README.md`）。

## 7. 平台侧

- 本轮**未发送任何 PATCH、未新增投标**；#1808/13450 的投标文案维持现状。

## 8. 复现环境（容器路径）

本机 Docker Desktop 4.98.0 虽已安装，但其 daemon 在非交互会话中启动后即被回收（`com.docker.service` 为 Stopped，`\\.\pipe\dockerDesktopLinuxEngine` 不存在），因此容器验证改用 **WSL2 内的 Docker Engine**，不需要 Docker Desktop 商业授权，也不需要 UAC。

| 项 | 实测值 |
|---|---|
| 宿主 | Windows 10.0.26200.9711；Hyper-V hypervisor present |
| WSL | WSL 2.6.3.0（内核 6.6.87.2-1），默认发行版 Ubuntu、版本 2 |
| 发行版 | Ubuntu 26.04 LTS（PID1 = systemd，cgroup v2 可用） |
| 引擎 | Docker Engine **29.1.3**（`apt install docker.io`），containerd 2.2.2 |
| Compose | Docker Compose **v2.40.3**（`docker-compose-v2`） |
| API | Client/Server 29.1.3，API 1.52，linux/amd64 |
| 冒烟 | `docker run --rm hello-world` → `Hello from Docker!`，exit 0 |

### 8.1 安装命令（WSL 内，无需 UAC）

```bash
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
```

### 8.2 镜像加速的坑

- 现象：Docker Hub 直连拉取 `hello-world` 报 `registry-1.docker.io: i/o timeout`；`python:3.12-slim` / `pgvector/pgvector:pg16` 同样会被卡住。
- 处理：写入 `/etc/docker/daemon.json` 后 `sudo systemctl restart docker`：

```json
{"registry-mirrors":["https://docker.m.daocloud.io","https://docker.1ms.run","https://docker.xuanyuan.me"]}
```

- 其他坑：PyPI 直连速度约 20–30 kB/s，`pip install` 阶段会明显拉长构建时间（1808 首次构建约 20 分钟），属网络环境因素，不是 Dockerfile/compose 定义问题；换到正常网络或配置 PyPI 镜像即可。
- 镜像加速只影响本机拉取基础镜像，不写进任何交付物，也不影响 CI。

### 8.3 `UP_EXIT` 判定方式

`api` 是长驻服务，`docker compose up --build --abort-on-container-exit` 不会自行结束。判定步骤：

```bash
# 1) 后台起栈，退出码写入日志
docker compose up --build --abort-on-container-exit > /tmp/up.log 2>&1; echo UP_EXIT=$? >> /tmp/up.log
# 2) 等健康
curl -fsS http://127.0.0.1:8000/api/v1/health
# 3) 跑验收（容器内）
docker compose exec -T api python scripts/ci_container_check.py
# 4) 主动 stop 触发 abort，再读 UP_EXIT
docker compose stop
grep UP_EXIT /tmp/up.log
# 5) 每个容器的退出码（必须在 down 之前取）
docker compose ps -a --format json
# 6) 清理
docker compose down -v
```

本次结果：`UP_EXIT=0`，`api=0 / postgres=0 / redis=0`。构建失败时 `UP_EXIT` 非 0 且完整日志在 `/tmp/up.log`，需按日志定位，不要只报“失败”。

### 8.4 复现路径差异

`delivery\1808` 目录只放交付说明与 CI 附件，**compose 与 Dockerfile 在工程仓库** `D:\AWKN-Lab\clawhunt\work\1808\repo`，容器命令必须在工程目录执行。
