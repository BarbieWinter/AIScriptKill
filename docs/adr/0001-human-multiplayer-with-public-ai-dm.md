---
status: accepted
accepted: 2026-07-17
scope: Multiplayer v1
---

# 真人多人优先，AI 只辅助公共主持

## Context

AIScriptKill 已经具备单人玩家与 AI NPC 的技术基础，但首个联机闭环如果同时扩展
真人房间、AI NPC 和 AI 主持，会让身份、私密信息与流程权威相互竞争。

## Decision

首个多人版本优先支持真人玩家共同完成读本、讨论和结算，暂停扩展
“单人玩家 + 多个 AI NPC”。AI DM 面向全房间进行节点式主持、规则解释和
全员同意的渐进提示，但不私聊、不扮演独立 NPC，也不决定阶段、材料、投票、
答案或结局。

## Consequences

- 已有 T-2.4 RAG 保留，联机闭环稳定后复用于公共 DM。
- 首版非玩家人物使用 YAML 预写内容，不运行独立 AI NPC。
- 模型不可用时，YAML 固定主持文本必须保证游戏能够完整运行。

## Scope

本 ADR 决定产品与权威边界，不选择具体模型供应商，也不实现 DM 运行时。
