# Notes Editor v3.0 — 轻量 Markdown 在线编辑器 | Lightweight Markdown Online Editor

带分屏实时预览的轻量级 Markdown 在线编辑器。通过简洁的网页界面浏览、编辑和管理 Markdown 文件。

A lightweight Markdown online editor with split-screen live preview. Browse, edit, and manage Markdown files through a clean web interface.

---

## 功能 | Features

- **分屏预览 Split-Screen Preview** — 编辑器旁实时渲染 Markdown Real-time rendering alongside editor
- **文件浏览 File Browser** — 导航和管理 Markdown 文件 Navigate and manage files
- **自动保存 Auto-Save** — 带视觉反馈的自动保存 Automatic saving with visual feedback
- **Cookie 认证 Cookie-based Auth** — 简易身份验证 Simple authentication system
- **Markdown 支持** — 完整 CommonMark + GitHub Flavored Markdown

## 快速启动 | Quick Start

```bash
cd notes-editor
python3 server.py
```

打开 Open `http://localhost:8080`

## 认证 | Authentication

凭据通过 `~/.shell-server/config.json` 管理。未找到配置时使用 `secrets.token_urlsafe()` 生成回退令牌。密码验证采用 SHA-256 哈希与恒定时间比较。

Credentials are managed via `~/.shell-server/config.json`. A fallback token is generated if no config is found. Password verification uses SHA-256 hashing with constant-time comparison.

## 技术栈 | Tech Stack

- Python 3 `http.server`
- 纯 CSS/JavaScript 前端 Pure CSS/JS frontend
- Markdown-to-HTML 渲染 rendering

## 许可证 | License

MIT
