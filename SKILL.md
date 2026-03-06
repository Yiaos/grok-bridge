---
name: grok-bridge
description: 通过 Safari JS 注入控制 SuperGrok，将 Grok 变成命令行工具
version: 2.0.0
---

# Grok Bridge v2

通过 Mac Safari 上已登录的 SuperGrok 网页，将 Grok 变成命令行工具。
v2 使用 Safari JavaScript 注入（`do JavaScript`），比 v1 的 Peekaboo 方式快 10x。

## 用法

```bash
# 一问一答
bash skills/our/grok-bridge/scripts/grok_chat.sh "你的问题"

# 自定义超时
bash skills/our/grok-bridge/scripts/grok_chat.sh "深度分析问题" --timeout 120

# 带截图
bash skills/our/grok-bridge/scripts/grok_chat.sh "问题" --screenshot
```

## 架构 (v2)
```
VPS (小灵)
  → SSH root@Mac
    → osascript → Safari "do JavaScript"
      → grok.com textarea 注入 + Enter 提交
      → 轮询 DOM 等待回复完成
      → 提取回复文本 → stdout
```

## 前提
- Mac SSH 可达（root@100.92.28.97）
- Safari Developer Settings:
  - ✅ Allow remote automation
  - ✅ Allow JavaScript from Apple Events
  - ✅ Allow JavaScript from Smart Search field
- Safari 已打开 grok.com 且已登录 SuperGrok
- 不需要 Peekaboo（v2 纯 JS 注入）

## 原理
1. `osascript` → Safari `do JavaScript` 注入文本到 textarea
2. 文本通过 base64 编码传输（处理特殊字符）
3. 模拟 Enter KeyboardEvent 提交
4. 轮询 DOM 内容，连续 2 次相同则认为回复完成
5. 提取 `document.body.innerText`，解析出 Grok 的回答

## 与 v1 的区别
| 特性 | v1 (Peekaboo) | v2 (JS injection) |
|------|---------------|-------------------|
| 输入方式 | pbcopy + Cmd+V | JS textarea.value |
| 提交方式 | Peekaboo press return | JS KeyboardEvent |
| 提取回复 | 截图 + OCR | DOM innerText |
| 速度 | ~30s | ~10s |
| 依赖 | Peekaboo | 仅 osascript |
| 特殊字符 | base64 + pbcopy | base64 + atob() |

## 限制
- 依赖 Safari 登录态（SuperGrok 订阅）
- 不支持并发（单标签页）
- macOS SSH 不允许 keystroke（System Events），所以用 JS KeyboardEvent
