# OpenClaw Profile Scaffold

快速为一台 Linux 主机创建隔离的 OpenClaw profile：配置 gateway、业务 agent、工作区、知识库和独立 CLI wrapper。

> 当前脚本面向使用 `/root` 运行 OpenClaw、由 systemd user unit 管理 gateway 的 Linux 主机。它会修改系统级 `/usr/local/bin`，并启动 systemd 服务；请先阅读下方的前置条件和执行流程。

## 功能

- 检查 profile 名称、端口、知识库文件、OpenClaw CLI 和 Python 依赖。
- 运行 `openclaw onboard`，并将配置合并到独立 profile。
- 创建业务 agent 工作区和初始化记忆文件。
- 从知识库源文件生成 `faq_<lang>.md`、`services.md` 和 `qa.json`。
- 安装 profile 专属 systemd gateway unit 与 `openclaw-<profile>` 命令包装器。
- 启动 gateway 并检查 `gateway status`。

## 前置条件

- Linux，使用 root 账户运行；脚本路径和文件位置目前固定为 `/root`、`/usr/local/bin` 与 `/root/.config/systemd/user`。
- 已安装并可执行 `openclaw` CLI，且该版本支持脚本中的 `onboard` 参数和 systemd user unit。
- Bash、Python 3、`ss`、`systemctl`。
- `.docx` 来源需要 `python-docx`；`.xlsx` 和 `.xlsm` 来源需要 `openpyxl`。
- DeepSeek API key（首次 onboard 时需要）和 Tavily API key。
- 知识库源文件为 `.docx`、`.txt`、`.md`、`.xlsx` 或 `.xlsm`。

安装 Python 文档依赖示例：

```bash
python3 -m pip install python-docx openpyxl
```

只需安装实际文件类型对应的依赖。`openclaw` 的安装方式请按目标主机的 OpenClaw 部署流程完成。

## 创建 profile

```bash
bash scripts/create_profile.sh \
  --profile acme \
  --port 25789 \
  --kb /root/knowledge/acme-qa.docx \
  --entity "PT Acme Indonesia" \
  --tavily-key "$TAVILY_API_KEY" \
  --deepseek-key "$DEEPSEEK_API_KEY" \
  --channel whatsapp \
  --lang id \
  --expect 500
```

命名和端口约束：

- `--profile` 和 `--agent` 以小写字母或数字开头，只能包含小写字母、数字、`-`、`_`。
- `main` 是保留的管理 agent 名称，不能作为业务 agent。
- `--port` 必须为 1–65535 的空闲端口。建议每个 profile 使用不同端口。
- profile 对应的状态目录已存在时，脚本会停止，不会覆盖。

### 参数

| 参数 | 必需 | 默认值 | 说明 |
|---|---:|---|---|
| `--profile` | 是 | — | 新 profile 名称；状态目录为 `/root/.openclaw-<profile>` |
| `--port` | 是 | — | gateway 端口 |
| `--kb` | 是 | — | 知识库源文件路径 |
| `--entity` | 是 | — | 对外业务主体名称，会写入知识库和 workspace 模板 |
| `--tavily-key` | 是 | — | Tavily 搜索插件 API key |
| `--deepseek-key` | 首次 onboard 必需 | — | DeepSeek API key；使用 `--skip-onboard` 时不需要 |
| `--agent` | 否 | 与 profile 相同 | 业务 agent ID；不能是 `main` |
| `--channel` | 否 | `whatsapp` | `whatsapp`、`wechat-kf` 或 `none`；`none` 不添加渠道路由 |
| `--lang` | 否 | `id` | 知识库语言：`id`、`zh` 或 `en` |
| `--expect` | 否 | `0` | 预期问答条数；大于 0 时数量不匹配会中止生成 |
| `--skip-onboard` | 否 | 关闭 | 跳过 onboard；仅用于已准备好 profile 状态目录和 `openclaw.json` 的情况 |

密钥通过命令行参数传给脚本，配置文件会写入 Tavily key，并设置为权限 `600`。在共享主机上运行时，请考虑命令行参数可能被同机进程读取；不要把真实密钥写入 README、shell 历史或提交记录。

## 知识库格式与解析

问答源建议每个问题和答案各占一个段落或单元格，并使用明确前缀，例如：

```text
Q1: 你们提供哪些服务？
A1: 我们提供……
Q2: 需要准备哪些材料？
A2: 通常需要……
```

解析器也识别英文、印尼文和中文的常见 Q/A 前缀（例如 `Question:`、`Pertanyaan 1:`、`问1：`、`Answer:`、`Jawaban 1:`、`答1：`）。没有前缀时，仅会尝试识别以 `?` 结尾且下一行较长的问答对；建议使用显式前缀，并通过 `--expect` 校对条数。

当前提取方式有以下限制：

- `.docx` 只读取正文段落，不读取 Word 表格中的内容。
- `.txt` 和 `.md` 按非空行解析。
- `.xlsx` 和 `.xlsm` 按工作表顺序读取单元格值，再交给同一问答解析器。
- `--expect` 只校验识别出的问答总数；脚本不会判断答案是否正确或完整，也不会自动审核生成内容。

生成文件位于业务工作区的 `faq/` 目录：

- `faq_<lang>.md`：连续编号的问答条目，包含问题、回答、下一步和合规提示。
- `services.md`：服务范围与官方核验点的待补充模板。
- `qa.json`：供人工复核的问答源数据。

请在接入渠道前人工检查问答解析结果、`services.md` 的占位内容和业务合规性。

## 完成后

脚本会创建以下主要资源：

- profile 配置及状态目录：`/root/.openclaw-<profile>`。
- 业务工作区：`/root/.openclaw-<profile>/workspace_<agent>`。
- systemd unit：`openclaw-gateway-<profile>.service`。
- CLI wrapper：`/usr/local/bin/openclaw-<profile>`。

查看服务状态：

```bash
openclaw-acme gateway status
```

脚本不会完成 WhatsApp 配对或微信客服 API 授权。请按渠道要求完成连接，再发送一条测试消息，确认业务 agent 使用正确的知识库和语言响应。

## 单独使用工具

只生成知识库：

```bash
python3 scripts/build_kb.py \
  --source /root/knowledge/acme-qa.docx \
  --out /tmp/acme-faq \
  --lang id \
  --entity "PT Acme Indonesia" \
  --expect 500
```

检查 `openclaw.json` 合并预览（只输出 profile、agent、端口等摘要，不写入配置）：

```bash
python3 scripts/configure_profile.py \
  --config /root/.openclaw-acme/openclaw.json \
  --profile acme --agent acme --port 25789 \
  --workspace /root/.openclaw-acme/workspace_acme \
  --tavily-key "$TAVILY_API_KEY" \
  --channel whatsapp --dry-run
```

## 仓库结构

```text
SKILL.md                         Codex skill 使用说明和操作流程
scripts/create_profile.sh       端到端 profile 创建脚本
scripts/configure_profile.py    OpenClaw JSON 配置合并
scripts/build_kb.py             问答源解析与知识库生成
templates/gateway.service       systemd unit 模板
templates/openclaw-profile.wrapper  profile 专属 CLI wrapper 模板
templates/workspace/            业务 agent 工作区模板
```

更详细的操作步骤和已知 OpenClaw 运维注意事项见 [`SKILL.md`](SKILL.md)。
