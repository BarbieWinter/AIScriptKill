# 玩法与剧本包工作流

## 玩家玩法流程

预期用户旅程记录在 `/docs/FRONTEND_EXPERIENCE_DESIGN.md`：

```text
/library
  -> /library/{script_id}
  -> /play/{script_id}/select
  -> /play/{session_id}
  -> /play/{session_id}/review
```

当前前端实现大体遵循这个形态，但角色选择路由名为 `/play/[sessionId]/select`，而它在创建会话前实际把该片段当作 script id 使用。

## 当前前端 Mock 流程

对活跃玩法屏幕而言，最丰富的行为在前端本地：

1. `/library` 把雪村作为硬编码剧本选项展示。
2. `/library/[id]` 可以使用 `api.getPackage`；live 模式读取后端 `GET /packages/{id}`，Mock 模式读取本地 Mock 包。
3. 角色选择使用硬编码角色，并跳转到生成的本地 session id。
4. `/play/[sessionId]` 在 live 模式从后端读取 session 状态并连接真实 WebSocket 心跳；Mock 模式从 `getMockEngine()` 和 `mockScenes` 初始化 Zustand store。
5. `MockWsClient` 只在 Mock 模式发出模拟事件，例如聊天、线索解锁、证据发现、阶段变化和 BGM 变化。
6. `SceneHotspots`、`ChatPanel`、`EvidenceBackpack` 和 `FinalSubmission` 等组件直接调用 Mock 引擎。
7. 复盘可以调用 `api.getReview`；除非 `NEXT_PUBLIC_USE_MOCK=false`，否则使用 Mock 复盘数据。

这对 UX 迭代有用，但还不是端到端的真实后端流程。

## 当前真实后端会话流程

已实现的后端流程是：

1. 通过 `POST /api/v1/packages?publish=true` 导入并发布剧本包。
2. 使用 `POST /api/v1/sessions` 创建会话，传入 `script_id`、`preferred_character_id` 和可选 `player_name`。
3. `engine/repositories/session_seed.py` 检查剧本包已发布、找到 `engine.entry_stage`、验证所选角色可玩，并 seed 一个 `SessionRuntimeState`。
4. `engine/repositories/session_mutations.py` 插入 `game_sessions`，创建 `initial` 检查点并提交。
5. 游戏动作经过 `POST /api/v1/sessions/{session_id}/actions`，并走 `engine/services/action_mappers.py` 中的确定性映射。
6. 效果会持久化聊天消息、发现记录、状态 patch 和检查点。
7. 最终提交经过 `POST /api/v1/sessions/{session_id}/final-submission`，持久化 `final_submissions` 和 `reviews`，并把会话标记为完成。
8. `/review` 返回已持久化的复盘。

真实后端尚未执行 AI DM/NPC 生成、条件 DSL 求值、剧本包定义的热点行为或实时 WebSocket 事件流。

## 剧本包导入流程

当前导入路径：

```text
zip upload
  -> packages route
  -> import_service.PackageUpload
  -> load_package_archive(bytes, publish)
  -> package_yaml/package_records/package_validation modules
  -> PackageImportRepository.import_package()
  -> upsert script_packages
  -> delete existing structure rows
  -> insert stages, characters, clues, evidences, scenes, media, endings

loose package directory
  -> load_package_directory(path, publish)
  -> package_directory_archive()
  -> same in-memory zip loading path
```

重要行为：

- 归档必须是有效 zip。
- 隐藏文件由 `engine/core/package_archive.py` 过滤。
- 必须恰好存在一个 `package.yml` 路径。
- 阶段和角色是必需的。
- `metadata.id` 必须使用小写字母、数字和连字符。
- 重复 id、未知阶段/角色/场景/线索/证据/媒体/结局引用、不支持的事件动作和缺失本地素材会让导入失败。
- 角色缺少某些阶段知识不会阻止导入，但会通过 `ScriptPackageImport.warnings` 返回 warning。
- 剧本包状态默认是 `draft`；当导入请求使用 `publish=true` 时为 `published`。
- 重新导入已有 package id 会替换该剧本包的结构行。

## 查询流程和防剧透控制

会话数据查询会先加载会话，强制执行服务层访问检查，再读取剧本包/运行期数据：

- 线索和证据通过 `session_discoveries` join，所以这些端点只返回已发现行。
- 角色和卡牌查询使用当前会话状态加已存储的剧本包数据。
- `session_context.py` 在可见性敏感查询前设置当前阶段和玩家角色的 Postgres session settings，与 `supabase/migrations/004_rls_policies.sql` 中的 RLS 设计匹配。

RLS 策略保护认证用户的直接表访问，但引入 service-role 访问、匿名会话或新查询端点时，仍需仔细审查后端服务本身。

## 需要关注的工作流缺口

- 已检查实现中，前端角色选择没有调用真实 `api.createSession`。
- 主玩法 live 模式已使用真实 session 读取和 `WsClient` 心跳，但具体动作还没有走真实 `api.performAction`。
- 后端 WebSocket 只支持心跳，而文档和前端 Mock 期望很多玩法事件。
- 后端动作行为尚未由导入剧本包的阶段/热点/证据规则驱动。
- 后端最终评分是固定占位逻辑。
- `script-packages/snow-village` 缺少 package YAML 文件，因此不能按现状导入。

## 变更指引

做真实集成工作时，从一个很薄的纵向切片开始：

1. 确保真实剧本包可以导入并发布。
2. 让角色选择调用 `api.createSession`，并使用返回的 session id 跳转。
3. 让一个玩法动作调用 `api.performAction`，并根据响应更新 Zustand。
4. 仅在 REST 状态转换可靠后再添加后端 WebSocket 事件。
5. 在导入剧本包数据完整后，再添加剧本包驱动规则和条件 DSL 求值。

做内容工作流时，扩展 schema 前先创建剧本包 fixtures 和 loader 测试。当前剧本包 loader 是后端可摄取内容范围的最强事实来源。
