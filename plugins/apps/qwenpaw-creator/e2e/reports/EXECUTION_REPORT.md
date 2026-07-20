# Creator 重构 E2E 执行报告

> 历史归档：本报告记录的是 2026-07-11、文件原生存储切换之前的候选版本，
> 仅用于追溯当时的执行证据，不代表当前 `project.json` + Runtime 文件实现的验收状态。

本报告只记录当前 `backend-creator-agent` 重构的同轮 release acceptance。所有状态均来自公开 HTTP、真实 Chromium、真实外部进程或明确列出的代码级门禁；没有通过 SQLite 写入、内部 service 调用或测试专用 HTTP API 造成功状态。旧 v1 `/ai`、`/agent`、PUT Project 与 Next 路由结果不计入通过。

## 运行信息

```yaml
status: PARTIAL_ACTIVE
executed_at: 2026-07-11T15:31:23+08:00
git_commit: 62684866d80974f4f13ccc405cdce1d2647569c1
origin_main: 24e505e03ba54b0f916267c10673cc28b65f7eed
cutover_data_root: /private/tmp/qwenpaw-cutover-final-a.uBr7Nd
natural_pending_source: /private/tmp/qwenpaw-provider-review2.h3Qg8V
cutover_backend_url: http://127.0.0.1:18114
cutover_ui_url: http://127.0.0.1:5174
browser: Chromium via pytest-playwright; in-app Browser manual acceptance by main thread
pytest_summary:
  collected: 24
  non_pending_previous_full_run: 18 passed, 5 deselected, 79.18s
  non_pending_current_full_run: 18 passed, 6 deselected, 32.61s
  non_pending_current_restart_spot_checks: 4/4 passed across isolated reruns
  natural_pending_public: 2 passed, 11.17s
  natural_pending_restart: 2 passed, 12.73s
  paid_provider_sealing: 1 passed, 297.90s
  chromium: 11 passed
  public_http_or_external_process: 12 passed
  external_restart_module: 7 passed, 1 real late-media case active
code_quality:
  py_compile: pass
  git_diff_check_e2e: pass
```

24 个 case 必须拆分执行：场景 11 会真实 Accept 一个 Decision Group，两个 PENDING restart case 会各自再克隆一次源数据根，真实 provider SEALING 与迟到 WAN gate 也使用独立场景副本。因而不能把会相互污染的 destructive case 放在同一个 staging 上串跑。生产 consistency gate 补丁完成后，当前候选已统一复跑 18 个 non-pending case 并全绿；上方 spot check 仅保留为崩溃点的独立证据。

## 实际命令

```bash
cd qwenpaw-creator/e2e

# 收集门禁
../../.venv/bin/python -m pytest -p no:cacheprovider --collect-only -q

# cutover 浏览器、HTTP、安全与不依赖 PENDING 的外部进程测试
CREATOR_E2E_BASE_URL=http://127.0.0.1:5174 \
CREATOR_E2E_STRICT=1 PYTHONDONTWRITEBYTECODE=1 \
../../.venv/bin/python -m pytest -p no:cacheprovider -q -m 'not pending' -s

# fresh APFS clone A：PENDING deferred/Overlay；然后双 Chromium token CAS
CREATOR_E2E_BASE_URL=http://127.0.0.1:5179 \
CREATOR_E2E_PENDING_PROJECT_ID=project-d7d86eda96a55851bd57f2bfa36a002e \
CREATOR_E2E_PENDING_TRANSACTION_ID=transaction-270fd33836d548e5a55e96e047d73fc0 \
CREATOR_E2E_STRICT=1 ../../.venv/bin/python -m pytest -p no:cacheprovider -q \
  tests/test_pending_public_contract.py::test_pending_action_commands_are_durable_deferred_with_zero_task_or_run_delta -s

CREATOR_E2E_BASE_URL=http://127.0.0.1:5179 \
CREATOR_E2E_PENDING_PROJECT_ID=project-d7d86eda96a55851bd57f2bfa36a002e \
CREATOR_E2E_PENDING_TRANSACTION_ID=transaction-270fd33836d548e5a55e96e047d73fc0 \
CREATOR_E2E_STRICT=1 ../../.venv/bin/python -m pytest -p no:cacheprovider -q \
  tests/test_pending_public_contract.py::test_two_browser_contexts_only_one_decision_wins_and_stale_token_is_409 -s

# 每个用例再从未改动的自然 PENDING 源各自 APFS-clone
CREATOR_E2E_BASE_URL=http://127.0.0.1:5179 \
CREATOR_E2E_PENDING_SNAPSHOT_ROOT=/private/tmp/qwenpaw-provider-review2.h3Qg8V \
CREATOR_E2E_PENDING_PROJECT_ID=project-d7d86eda96a55851bd57f2bfa36a002e \
CREATOR_E2E_PENDING_TRANSACTION_ID=transaction-270fd33836d548e5a55e96e047d73fc0 \
CREATOR_E2E_STRICT=1 ../../.venv/bin/python -m pytest -p no:cacheprovider -q \
  tests/test_backend_restart_recovery.py::test_pending_deferred_command_survives_external_backend_restart \
  tests/test_backend_restart_recovery.py::test_review_accept_before_and_after_commit_crashes_are_atomic -s

# 显式付费 gate：正常公开 Goal + qwen3.7-plus，精确 SEALING pause/SIGKILL
CREATOR_E2E_PENDING_SNAPSHOT_ROOT=/private/tmp/qwenpaw-provider-review2.h3Qg8V \
CREATOR_E2E_RUN_PROVIDER_SEALING=1 CREATOR_E2E_PROVIDER_SEALING_TIMEOUT=2400 \
CREATOR_E2E_STRICT=1 ../../.venv/bin/python -m pytest -p no:cacheprovider -q \
  tests/test_backend_restart_recovery.py::test_natural_provider_sealing_crash_rolls_back_and_recovers_to_review -s
```

## E2E 硬证据

- `test_external_backend_sigkill_restart_preserves_public_state_and_replays`：真实 uvicorn 在 committed safe boundary 被 `SIGKILL`，同一数据根重启后 Project、Conversation、AssetVersion、SUCCEEDED Task 与 CANCELLED Session 均保留；Project/Conversation/Asset ingest/interrupt 响应跨重启逐字节 replay 一致，payload drift 为 409，未新增 Goal/Transaction/Run/provider 调用。
- `test_active_manual_edit_hard_stop_closes_transaction_without_stop_prompt`：先只上传一半公开 Command JSON 后硬杀，重启确认 Plan、Session、Goal、Transaction、消息、Task、Run 全部零变化；再完整提交 `CREATE_SECTION`，只产生一条固定 `frontend_manual_edit` 消息。interrupt 后 Transaction/Goal/Session 均 CANCELLED，无 stop Prompt、Task 或 Run；再次硬杀/重启仍保持同一终态，interrupt replay 逐字节一致。
- `test_blob_publish_before_asset_manifest_crash_recovers_atomically`：测试入口只在真实 `_store_blob` 返回后、AssetVersion manifest commit 前写 marker 并 `SIGSTOP`；父进程 `SIGKILL`。重启后同一 Task 成功，checksum、公开 content 与物理 blob 一致，只有一个 AssetVersion；replay 不重复创建。
- `test_running_asset_import_resumes_same_task_after_sigkill`：真实 multipart 文件夹上传 120 个 64 KiB 文件；第二 HTTP client 公开观察 `asset_import=RUNNING` 且至少一个 blob 已持久后硬杀。原上传连接真实断开；重启恢复同一个 taskId 为 SUCCEEDED，120 个结果 checksum/content 与 blob 完整对应、零失败、零 Run/Transaction，replay 不新增 Task，drift 为 409。
- `test_pending_deferred_command_survives_external_backend_restart`：自然 seal 的 PENDING_REVIEW clone 上，四种动作只落 durable deferred command，Review/Decision Group/Task/Run 不变；硬杀/重启后 response replay 逐字节一致，deferred 状态仍存在。
- `test_review_accept_before_and_after_commit_crashes_are_atomic`：Accept 请求只发送部分 body 后硬杀，Review bytes 与 PENDING token 完全不变；完整 Accept 返回 200 后再硬杀，`ACCEPTED_APPLIED` 持久，response replay 逐字节一致，旧 token 409，Task/Run 零增量。
- `test_natural_provider_sealing_crash_rolls_back_and_recovers_to_review`：公开创建项目 `project-a74db4c9b48758409b5db00e8eae7078`、Session `session-7356c697bdbb5f43a9088f07065ced5e`、Transaction `transaction-784c33bb4c7549dd81f106cc1be5e280`；真实 qwen3.7-plus 完成 Creative Strategy 与 Review Consistency。独立测试入口在同一 SQLite transaction 内、状态已写为 SEALING 而 Review Manifest 尚未发布时生成 `review_sealing_before_manifest` marker（PID 69424）并 `SIGSTOP`；父进程 `SIGKILL`。无 hook 重启后同一 Transaction 自动恢复为 PENDING_REVIEW，ReviewRevision 与 PENDING Decision Groups 可公开读取，Runs 全终态且 Tasks 为空。结果：`1 passed in 297.90s`。
- 真实链还暴露并修复了两个 restart authority 问题：长 provider/model recovery 原先在 ASGI bind 前同步等待，R2V 根重启 24 分钟仍无 LISTEN；现在由受监督后台 recovery lane 接管，阻塞 recovery 时 API 仍可服务的专项测试通过，含真实复杂 R2V APFS clone 的 uvicorn health 在 11 秒内返回 200。另一个问题是每次重启都会把已 exact imported 的 SUCCEEDED Task 再写一次并改变 `updatedAt`；`mark_imported` 现在只在 immutable refs 已真实存在时落一次 marker，后续 reconcile 原样 no-op。对应 unit authority 测试、Ruff/py_compile/diff-check 通过，真实外部 SIGKILL/replay case 重跑 `1 passed in 77.23s`，Task JSON 跨重启精确不变。
- 后台 recovery 改为非阻塞启动后，blob-before-manifest case 不再假设 health=Task 已终态，而是通过公开 Task API 等待同一个 durable Task；修正后的真实 crash/restart 用例 `1 passed in 52.10s`。这只调整观察时序，不放宽 checksum、唯一 AssetVersion、content bytes 或 replay 断言。
- 自然 PENDING fixture 原件保持未修改：Project `project-d7d86eda96a55851bd57f2bfa36a002e`、Session `session-e7348f2bed725c4988bdd2d2d1906994`、Transaction `transaction-270fd33836d548e5a55e96e047d73fc0`、Review `review-manifest-ef71c62eb24e42ffb44aa2ad7fc01a73`，原始 2 个 PENDING Group、0 Task、9 个 SUCCEEDED Run。所有 destructive 操作只发生在 APFS clone。
- 真实纯 R2V 链自然 seal：Project `project-56fd3205fbc45d41a50ae067b9d436c0`、Session `session-a6fe54c41282521b905691d6edf9d838`、Transaction `transaction-e4975389bf714582a8e58f79f6925c1a` 最终公开状态为 `PENDING_REVIEW`；Review `review-manifest-d1e7792870e94c68bd815370e1567fc9` / Revision `revision-420e21ac3857415aa18932cfafeb4b4c` 含 10 个 PENDING Decision Group，零非终态 Run/Task。两张真实 storyboard 与两段 wan2.7-r2v Unit 视频的 4 个 Task、Section/Final compose 的 2 个 Task 均 `SUCCEEDED` 且 `result.imported=true`。Review media comparison 精确记录 Unit 视频各 `4.04s`、Section `8.103492s`、Final `8.102993s`；两段 Unit 视频的 `inputStoryboardRefs` 分别指向各自 exact storyboard ArtifactVersion，Section provenance 精确指向两个 Unit 视频，Final provenance 精确指向 Section 视频。最终视频 checksum 为 `sha256:3c4dd1987d5c4fd650d29ef4fe8c6d54f69b03f13337d4687967ea94dfa50af7`，下载后 ffprobe/完整 decode 验证为 1920×1080 H.264 + AAC。
- R2V 媒体快照不能直接改 `CREATOR_DATA_ROOT` 后启动：第一次把 APFS clone 直接作为新根时，生产 `StorageIntegrity` 正确把该副本标为 `ERROR`，报告 6 个 `MEDIA_VERSION_STORAGE_INVALID`（不可变 Artifact 的本地 locator 不在对应 canonical namespace）。该副本未执行任何业务 mutation，已停止并删除；没有改 DB URL 绕过。后续 destructive 场景只从冻结原件建立独立 clone，并由单一协调者把历史 canonical anchor symlink 串行指向当前 clone；每场先以公开 HTTP 断言 Session/Transaction/Review 不变、6 个媒体 locator 可读且 checksum 一致，才允许操作。
- Destructive Review 场景只记录 clean clone：#7 首次副本在 Revise 后误用 invalid model 导致 Session `ERROR`，整份丢弃；clean clone 才得到下方 PASS 证据。#8 的首次副本沿用旧“两 Unit”Goal 而被 consistency 正确 BLOCKED，随后出现内部 seal 尝试，整份丢弃且不计证据；第二份 clean clone 进一步暴露 SUCCESS consistency 后未满足 Post/Impact prerequisites、模型仍重复 consistency/猜 completion context 的通用门控问题（公开消息 seq 642–650），同样不计 PASS。通用 prerequisite snapshot、same-head duplicate-consistency rejection 与幂等 `completion_blocked` 已完成，相关 Creator/Review/completion 回归 `33 passed`。修复后的 pristine #8 在公开 `DELETE_UNIT` 后又真实暴露已删 Unit 的 Workbench GET 将 `ProjectionInputError` 泄漏为 HTTP 500；这是契约性 NotFound 缺口。生产修复新增精确 `ProjectionResourceNotFoundError` 子类，只将 current/historical Workbench 及 Section Compose 的“目标不存在”映射为顶层 `code=NOT_FOUND` 的 404，其他投影/存储错误仍闭合失败；API/Format 定向回归 `15 passed`，Ruff/py_compile 通过。同一真实数据副本重启后继续场景，未完成 Reject 恢复前仍不计 PASS。
- 同一 pristine #8 副本在 404 修复后重启，7/7 个公开 owner-closure Command 均为 `APPLIED`，Task 保持 11 个且 active=0、Working Head=44。但 Post Run 成功返回后，公开消息 seq 621–633 连续至少 13 次 `CREATOR_OUTPUT_REJECTED`，Session 陷入无边界的模型/Output Guard 自动重试。运行时已立即停止，该状态明确不计 PASS。通用修复保留了 Runtime marker/id/status 对整份 raw reply 的强校验，仅将 Workspace dependency 窄化为 delegate 的结构化 `target_refs`，允许 task/总结描述历史上已删 identity；拒绝反馈现在投影 exact rule/ref，同 transaction/head/rule/ref 连续第 3 次会持久转为 `WAITING_USER_INPUT`，合法 action、新用户输入或 head 变化会重置计数。Creator Loop/Message Boundary/Driver 独立回归 `37 passed`，Ruff 通过；同一真实副本重启后继续，未完成 Reject 恢复前仍不计 PASS。
- #8 最终从上述同一 pristine 副本全公开收口：新 Goal `goal-a88972e6edc74a1693024692c81c2a1a`、Transaction `transaction-be0ac3c831814a669c573263da08e41e`自然 seal 为 Review `review-manifest-19fb58347c414ce38814aa5685f341ad` / Revision `revision-b35366f8498e4ebdaf3c59ac95ae708d`。删除 Group `decision-group-3150304742f74208bbf87f5cb0515bc4` 含 25 个 operation，同组覆盖完整 `fold-airplane` Unit 子树、storyboard/video selected refs 和 `post/sections/intro/sequence/001000--fold-airplane.ref`。Reject 前 Plan 仅 `release-catch`、fold Workbench=404；使用 fresh token 公开 Reject 后 Group=`REJECTED`且 token 旋转，Plan 恢复 `[fold-airplane, release-catch]`、fold Workbench=200、selected storyboard/video 精确恢复为 `artifact-version-task-4a864...` / `artifact-version-task-c25a...`，Section sequence 恢复两个 Unit exact video refs；Final 不在该 Group 中且 refs 保持。Reject 前后 Task 均为 11、active=0，历史 fold video checksum `sha256:9a4bc3d6ac5085d40ee3ef8f401a9d844bbcc0fe3dbaf4c105455b73201d07bd` 与 review operation 均可读。seal 只有 seq653 一次 consistency delegate、seq655 合法 yield、seq657 唯一 SUCCESS、seq658 唯一 exact `completion_context`、seq659 使用其参数完成；无第二个 same-head consistency、无空 yield、无猜测 completion 参数。
- 真实纯 AI Edit 链自然 seal：Project `project-be1bf2ebf6935fcab4b0d856b2abb1d4`、Session `session-ff0b89fceea451cb803c5f0cc1f520e3`、Transaction `transaction-5acf411bf6ce4c4889eaf0e0e9d3ae51` 最终公开状态为 `PENDING_REVIEW`。Review `review-manifest-307507e9c3fa47938e6cda7b1632d72a` / Revision `revision-0e46b7f4bdbe45b89f26185b32f8396d` 只有 Group `decision-group-9e5d58b8416f497fb12f7eccb78314e6`（title `project:plan`、PENDING），零运行中 Task。真实 ingest Task、2 个 `ai_edit_plan` Task 与 3 个 `ai_edit_execute` Task 均 `SUCCEEDED` 且 exact imported；最终 Task `task-470b0a313fce4b3f9ae174bdd7625c4c` 指向 selected/current v3 Artifact `artifact-version-task-470b0a313fce4b3f9ae174bdd7625c4c`，checksum `sha256:5dd9bff5709d32ffdc23bb4b88f92d2328e71cd285aea6b582e3bf1333dfe60f` 与文件 SHA-256 精确一致。用户在真实前端把 clip 明确设为 0.6–16.5s（15.9s），并通过公开授权执行；最终媒体 ffprobe 为 `15.978679s`、H.264 640×360 + AAC 48kHz mono。应用内浏览器 AgentDock Review Center 显示 1 Group / 29 个 immutable text diff；`查看` 深链到 exact asset/version field，重复点击使 `reviewPulse` 改变，120 次采样中 `review-flash` 46 次可见。

首次 SEALING gate 的目标文本同时要求“建立 R2V Unit”和“禁止生成 storyboard/video”，而 completion validator 正确要求 R2V Unit 必须选择真实 storyboard/video ArtifactVersion；该测试目标不可满足，agent 因此持续修复 registry 而不能 seal。该测试被纠正为只修改 project-level creative brief、明确不创建 Section/Unit 的合法 change 后，5 分钟内完成上述精确故障验证。两个超时窗口不记为候选实现失败，也没有通过伪造 ref 绕过 validator。

## 前端代码门禁与独立应用内浏览器

主线程回传的前端代码门禁为 21 个测试文件 / 123 tests passed，`npm run typecheck`、Vite build 与 package verify 全部通过。candidate、工作树与 `origin/main@24e505e03ba54b0f916267c10673cc28b65f7eed` 的 `src/app/globals.css` SHA-256 均为 `176a288f8dd695774613c8a26a4832aceb6aa8f2bb050ae1020c4c444e6cede3`。

以下为同一候选版本上的 1280×720 应用内浏览器实操，独立于 pytest Chromium 计数：

| 页面/操作 | 状态 | 可见与交互证据 |
|---|---|---|
| Plan 与 `origin/main` 对照 | PASS | header、main、buttons、article 的可见层级与 class 逐项相同。 |
| Home / 模型配置 | PASS | Home 正常；已有模型密钥只显示安全遮罩，不回显 secret。 |
| Assets | PASS | 真实资产卡片 → Inspector → 详情弹窗 → Prompt 本地草稿输入 → 不保存关闭，全链可操作。 |
| R2V Workbench | PASS | 2 shots、7s/15s、storyboard/version/input refs 均正确可见。 |
| AI Edit Workbench | PASS | 7 个 VLM panels；7 个 keyframe video 的 `currentTime` 与 source 时长一致；timeline 与 v1/v2 可见。 |
| AgentDock | PASS | 打开 → 输入未发送草稿 → 键盘清空 → 发送按钮恢复 disabled → 关闭，状态一致。 |
| 删除的 Canvas routes | PASS | Canvas 列表与 Canvas detail 均显示“页面未找到”。这是用户允许的唯一前端表面删除。 |

## §13.4 验收矩阵

| # | 场景 | 当前状态 | 本轮证据或仍在运行的真实链 |
|---:|---|---|---|
| 1 | 纯 R2V | PASS | 两张真实 storyboard → 两个 exact storyboard-first wan2.7-r2v Unit（各 4.04s）→ Section compose（8.103492s）→ Final compose（8.102993s）→ consistency → 自然 seal。Review `review-manifest-d1e779...` / Revision `revision-420e21...` 含 10 个 PENDING Group，6 个成功媒体/合成 Task 全部 exact imported，最终 H.264/AAC 文件完整解码通过。 |
| 2 | 纯 AI Edit | PASS | Project `project-be1bf2...` 完成真实视频 upload、公开手调 timeline 0.6–16.5s、授权、BUILD/EXECUTE/重新渲染；最终 Task `task-470b0a...` 与 v3 Artifact 同后缀均 exact imported/selected/current，checksum 与文件 SHA-256 一致，ffprobe `15.978679s` H.264 640×360 + AAC。自然 Review `review-manifest-3075...` 仅 Group `decision-group-9e5...`；真实前端 Review Center 已验证 29 diff、exact deep-link 与重复查看 highlight replay。 |
| 3 | 混合项目 | PAUSED | 有效 canonical 新生产链尚未启动；第一次非canonical clone 被 StorageIntegrity 拒绝并删除。因最新 `origin/main@24e505e0` 的 AI Edit/storyboard retry 语义正在移植到新内核，按 release 指令暂停，待代码门禁完成与 #12 释放 canonical anchor 后再从 frozen pristine clone 执行。 |
| 4 | 用户软干预 | PASS | 真实 qwen3.7-plus 项目 `project-0ca73...`：运行中第二条公开 message 记录 `queued_until_message_boundary`，合法边界后进入同 Session；同 Goal 的后续消息 seq 由 Runtime 消费。 |
| 5 | ACTIVE 用户手改 | PASS | 公开 `CREATE_SECTION`/manual edit 与真实 provider 并发；run `run-c95e...` 的公开 SUCCESS summary 明确保留用户权威值，旧结果未覆盖。另有 deterministic outbox/硬停/重启证据。 |
| 6 | PENDING 手改 | PASS | 自然 PENDING clone 上 Overlay `manual-overlay-b93...`；strategy Group `SUPERSEDED_BY_USER_EDIT`、plan Group `ACCEPTED_APPLIED`，approved revision `revision-56ca...`，收口后才建立 resume tx `transaction-038c...`。 |
| 7 | 部分审阅 | PASS | clean canonical clone 启动保持同 Session/Transaction/Revision 与 10 个 PENDING Group；Accept `project:header` Group `decision-group-6f37...` 推进 Approved Revision `revision-8228...`，Reject `unit:fold-airplane` Group `decision-group-dbb...`（含真实 Video ref operation `review-operation-7389...` / Artifact `...c25a...`），Revise `unit:release-catch` Group `decision-group-5693...`。Revise 后历史 operation GET 200，仍可看到真实 `...9581...` Video afterVersionRef；Session RUNNING、Transaction REVISING、Task 总数仍 11，无 ERROR。 |
| 8 | 删除闭包/Reject 恢复 | PASS | 新 Transaction `transaction-be0ac3...` 自然 seal；25-op Group `decision-group-3150...` 同组包含完整 fold Unit、storyboard/video selected refs 和 Section sequence ref。Reject 前 fold Workbench=404，Reject 后=200 且 storyboard/video/Section refs 全部恢复 exact 历史 ArtifactVersion；Task 11/active0 不变。自然 seal 仅一次 consistency/yield/SUCCESS/context/complete，无重复或猜测。 |
| 9 | 硬停止 | PASS | 旧 Goal/Transaction/Run 均 CANCELLED，无 stop Prompt/新 Task；明确继续后创建新 Goal `goal-3ae...` 与 lazy tx `transaction-1654...`，旧状态未复活。另有外部进程重启门禁。 |
| 10 | 进程崩溃恢复 | PASS | outbox 前后、blob/manifest 中间、公开 Task RUNNING、真实 provider SEALING、PENDING、Accept commit 前后均已逐点 SIGKILL/恢复；见上方 7 个外部进程 case。 |
| 11 | 多标签 token CAS | PASS | 两个独立 Chromium context 对同 Group 决定：第一个 200，旧 token 409。真实 accept-vs-manual-edit 竞态另得 accept 200、edit 409 `STALE_PRESENTATION_VERSION`，第二 tab 旧 token 409。 |
| 12 | 迟到媒体 | ACTIVE | 测试入口已实现真实 WAN `poll=SUCCEEDED` gate：所有同 Task 并发 poll 都等待 release；公开 cancel + `DELETE_UNIT` + 自然 seal 后才释放，并要求 `task.quarantined`、Task/Review/Header/Plan/公开 ArtifactVersion 引用集合不变及确定性目标 Artifact 404。等待 canonical clone 串行 handoff 后执行，不调用内部 TaskRegistry。 |
| 13 | 旧客户端 | PASS | 旧路由/PUT 404，旧 Project payload 422，未知 Command 400，`task_type`/`t2v` 422；无效请求前后 Plan/Session/active Transaction 不变。 |
| 14 | 安全与幂等 | PASS | 路径逃逸、跨 Project exact ref、伪造 Artifact、role 写入口均拒绝；Project/Asset/Conversation/interrupt/Task replay 与 drift 含跨重启验证。 |
| 15 | 首轮素材边界 | PASS | 真实浏览器 multipart；ingest 前 IDLE/无 Goal/Transaction/Task/消息，成功后首条 Goal 精确挂载 AssetVersion refs。 |
| 16 | Pending 操作门 | PASS | Analyze/Generate/Execute/Compose 全部 durable deferred；ATTACH_SOURCE 只进入 Overlay；Review 收口前零新增 Run，唯一允许的 transaction-less ingest Task 完成；重启后 deferred/replay 保持。 |
| 17 | 异步多 Run | PASS | 公开 command `command-6f3f...` 命中的 Story Run `run-5e0c...` 因 read-set 变化成为 STALE，marker/summary 为空且 staleReason=`READ_SET_STALE`；不相交的 Visual Run `run-2a3e...` 从 RUNNING_MODEL 继续到 SUCCEEDED，Plan 保留 `FINAL_READSET_USER_AUTHORITY`。 |

场景 4/5/6/9/11/17 的相关代码矩阵为 87 passed in 29.04s，涉及的 11 个 Python 文件 Ruff clean。该代码级结果用于支持真实运行证据，不替代上表中的公开 Runtime/浏览器状态。

## 当前收口状态

测试套件当前收集 24 个 release case；生产 consistency gate 补丁后的 18 个 non-pending case 已在当前候选上统一复跑全绿。场景 10 的全部指定崩溃点已有逐点证据，真实纯 R2V、纯 AI Edit 与部分审阅已 PASS；混合项目、删除闭包和迟到媒体仍在运行。整份 §13.4 继续保持 `PARTIAL_ACTIVE`，任何 ACTIVE/NOT_RUN 场景都没有以历史数据或代码级测试冒充 E2E PASS。
