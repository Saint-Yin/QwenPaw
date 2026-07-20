# Creator E2E（Playwright + pytest）

这套测试只面向重构后的唯一 Creator 契约：`/api/creator/projects/**`、semantic Command、page-specific View、受控媒体路由和 HashRouter UI。浏览器定位器严格对应 `origin/main@24e505e03ba54b0f916267c10673cc28b65f7eed` 保留的可见文案、DOM 层级与交互，不再保留任何旧 `/ai/**`、`/agent/**`、PUT Project 或 Next 文件路由用例。

## 前置

1. 后端以待验收的 `CREATOR_DATA_ROOT` 启动在 `127.0.0.1:18110`。
2. Vite UI 启动在 `127.0.0.1:5173`，并把 `/api/creator` 代理到该后端。
3. 安装测试依赖及 Chromium：

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## 运行

```bash
cd qwenpaw-creator/e2e
CREATOR_E2E_STRICT=1 python -m pytest -q
```

Release acceptance 通常分成无 PENDING fixture 的确定性门禁与一次性 PENDING staging：

```bash
# 当前 cutover rehearsal：浏览器、HTTP、安全与外部进程故障注入
CREATOR_E2E_STRICT=1 python -m pytest -q -m 'not pending'

# 真实 seal 后的一次性 staging；不设置 STRICT 时缺 fixture 会明确 skip
python -m pytest -q -m pending -rs
```

`CREATOR_E2E_STRICT=1` 会把服务未启动或 rehearsal 项目缺失视为失败；日常本地开发不设置时会 skip。三个迁移项目/Unit ID 均可用 `CREATOR_E2E_*_ID` 环境变量覆盖。

PENDING_REVIEW 没有测试后门。多标签 token CAS 与 PENDING 操作门测试只接受由真实 Creator 流程 seal 的公开 fixture，并要求至少两个独立 PENDING Group：

```bash
CREATOR_E2E_PENDING_PROJECT_ID='<project-id>' \
CREATOR_E2E_PENDING_TRANSACTION_ID='<optional-transaction-id>' \
CREATOR_E2E_STRICT=1 python -m pytest -q -m pending
```

文件化 Runtime 的断电、重启、租约接管和中间写入故障改由
`backend/tests/project_files`、`backend/tests/runtime_files`、
`backend/tests/source_analysis` 与 `backend/tests/media_files` 中的确定性故障注入
覆盖。E2E 不再加载 Runtime 内部实现，也不保留基于旧数据库事务 pause hook 的
测试入口；浏览器验收只通过公开 HTTP 契约观察结果。

## 覆盖

- `buttons`：origin Home 卡片与 720px Composer、模型密钥只写边界、Project 创建无 Goal/Task、删除。
- `cutover`：迁移 R2V/Edit canonical View 在 origin Plan/Workbench 中的呈现、28 秒 R2V 方案、56 秒 Edit timeline、分镜图与裁剪预览媒体、Section/Final Compose 阻断及旧 `/canvas` 404。
- `assets`：origin 六分类统一卡片网格、右侧 Inspector、真实 1957 秒视频元数据，以及“补充资料”multipart 的 `ATTACH_SOURCE`。
- `contract`：旧 HTTP 路由/旧 payload 无 fallback、Project/Asset idempotency replay 与 payload drift 409、真实 Composer 文件上传在首条 Goal 前后的原子边界。
- `security`：路径逃逸、跨 Project exact AssetVersion ref、伪造 Artifact ref、未公开 Specialist role 写入口。
- `pending`：公开 PENDING fixture 上 Analyze/Generate/Execute/Compose durable deferred 且零 Transaction Task/Run 增量、ATTACH_SOURCE 只进入 Overlay、两个独立浏览器 context 的 stale decision token 409。
- `restart`：公开 HTTP 层只验证服务重启后的 Project、Session、Task 与 Review 可见性；文件原子写、租约接管和中间故障由后端确定性测试负责。

所有新增上传用例都让浏览器/HTTP 客户端把真实 multipart 发到运行中的后端；不使用 `route.fulfill` 模拟成功。恢复能力必须由隔离数据根上的后端故障注入测试证明，E2E 不通过内部 service 造数。

真实 LLM/VLM、图像和视频 provider 调用属于有成本的 release acceptance，使用后端模型探测与专门生成用例单独执行；本套浏览器回归不会隐式消耗额度。
