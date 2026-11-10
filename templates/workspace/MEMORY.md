# MEMORY.md - 长期记忆

## 初始化

- profile `{{PROFILE}}`，agent `{{AGENT}}`，网关端口 {{PORT}}，状态目录 `/root/.openclaw-{{PROFILE}}`。
- 主体：{{ENTITY}}。
- 知识库：`faq/faq_{{KB_LANG}}.md`（唯一权威），`faq/services.md`（服务范围与核验点）。
- CLI：用 `openclaw-{{PROFILE}} ...` 管理网关（`--profile` 会误解析到主网关单元）。
