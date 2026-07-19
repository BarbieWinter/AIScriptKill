---
status: accepted
accepted: 2026-07-17
scope: Multiplayer v1
---

# YAML 是阶段、材料与结算的玩法权威

## Context

多人房间会同时存在真人输入、网络事件和 AI 输出。如果其中任何一方都能临时决定
阶段、材料或结局，相同剧本将无法稳定恢复，也无法防止主持模型越权。

## Decision

每个阶段由读本期、讨论期和可选结算组成。公共材料的揭晓节点、结算模式、投票影响
和最终推理模式均由 YAML 预先声明，并由确定性运行时执行。AI DM 只能表达主持文本
与受约束提示；房主也只有房间管理权限。

## Consequences

- 不同剧本可以选择直接推进、秘密投票、共同选择或最终推理。
- 并发、断线或模型输出不能改变谜题和结局。
- MP-0 只冻结 standalone authoring contract；现有 loader 尚不接受多人字段，避免把
  “可校验”误解为“可发布并执行”。

## Scope

将 contract 接入 package loader、引用校验和多人运行时属于 MP-1。
