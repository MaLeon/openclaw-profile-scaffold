---
name: "openclaw-profile-scaffold"
description: "Scaffold a new isolated OpenClaw profile: state dir, gateway unit, CLI wrapper, agent workspace, and FAQ knowledge base from a source document."
status: proposal
version: "v1"
date: "2026-11-10T08:44:57.012Z"
---

# OpenClaw Profile Scaffold

Builds a complete, production-shaped OpenClaw profile from a knowledge-base source file, mirroring the layout already used by the `nli` / `mli` / `osl` profiles on this host.

## When to use

- "Create a new profile/bot for <client>" with a source document (docx/xlsx/txt) that should become its knowledge base.
- Cloning an existing profile's structure for a new tenant on the same machine.

## Inputs

| Parameter | Required | Example | Notes |
|---|---|---|---|
| `profile` | yes | `mli2` | lowercase letters/digits/`-`/`_`; becomes `~/.openclaw-<profile>` |
| `port` | yes | `25789` | must be free; convention `<n>789` (18789 main, 19789, 20789, 21789, 22789, 23789, 24789) |
| `kb_source` | yes | `/root/predoc_mli/FINAL_MLI_500_QA.docx` | docx / txt / md / xlsx |
| `tavily_key` | yes | `tvly-...` | written to `plugins.entries.tavily.config.webSearch.apiKey` |
| `deepseek_key` | yes | `sk-...` | DeepSeek provider credential used during onboarding |
| `agent_id` | no | defaults to `profile` | business agent id (`main` is always created too) |
| `channel` | no | `whatsapp` (default), `wechat-kf`, `none` | routed to the business agent |
| `kb_lang` | no | `id` (default), `zh`, `en` | primary KB language |
| `expect` | no | `500` | expected Q&A count; build fails on mismatch |

`profile` and `agent_id` must start with a lowercase letter or digit and contain only lowercase letters, digits, `-` or `_`. The agent id `main` is reserved for the admin agent. `port` must be an integer from 1 to 65535.

## Procedure

### 0. Preflight
```bash
ss -ltn | grep -q ":$PORT " && echo "port busy" && exit 1
test -e ~/.openclaw-$PROFILE && echo "profile exists" && exit 1
openclaw --version && python3 -c 'import docx'   # python-docx for .docx; openpyxl for .xlsx/.xlsm
```
Never reuse a port, never overwrite an existing profile dir.

### 1. Scaffold the profile (state dir, config, workspace seed, unit)
```bash
openclaw onboard --profile "$PROFILE" --non-interactive --accept-risk \
  --flow quickstart --mode local \
  --auth-choice deepseek-api-key --deepseek-api-key "$DEEPSEEK_KEY" \
  --gateway-auth token --gateway-bind loopback --gateway-port "$PORT" \
  --workspace ~/.openclaw-$PROFILE/workspace \
  --install-daemon --skip-channels --skip-skills --skip-hooks
```
Creates `~/.openclaw-<profile>/{openclaw.json,openclaw.log,agents/,credentials/,identity/,logs/,media/,npm/,plugin-skills/,skill-workshop/,state/,workspace/,workspace-attestations/}` plus `~/.config/systemd/user/openclaw-gateway-<profile>.service`.

Verify the unit name carries the profile suffix. If onboarding installed `openclaw-gateway.service` instead (no suffix), generate the unit from `templates/gateway.service` — never share the main unit.

### 2. Merge business agent, model, search and channel config
Run `scripts/configure_profile.py` (idempotent JSON merge, keeps a timestamped backup):
- `agents.defaults`: workspace `~/.openclaw-<profile>/workspace`, model `deepseek/deepseek-flash`
- `agents.list`: `main` + business agent with `workspace ~/.openclaw-<profile>/workspace_<agent>`, `memorySearch.provider=none`, minimal tool policy (read/message/write/edit/memory_search/memory_get, `fs.workspaceOnly=true`, deny exec/web/cron/gateway/sessions_*)
- `plugins.entries.tavily.config.webSearch.apiKey` + `tools.web.search={provider:tavily,enabled:true}`
- `channels.<channel>` and `bindings` route → business agent
- `gateway.{mode:local,bind:loopback,port}`, `session.dmScope=per-account-channel-peer`

Then `openclaw --profile "$PROFILE" config validate`.

### 3. Business workspace files
Copy `templates/workspace/*` into `workspace_<agent>/`, substituting `{{PROFILE}} {{AGENT}} {{PORT}} {{ENTITY}} {{KB_LANG}}`: `AGENTS.md`, `IDENTITY.md`, `SOUL.md`, `USER.md`, `MEMORY.md`, `TOOLS.md`, `HEARTBEAT.md`, `interfaces.md`, `.gitignore` (`faq/`, `media/`), plus `memory/` with a dated note.

Keep the seeded `workspace/` as the admin/debug area: remove `BOOTSTRAP.md` (back it up) and state inside that it is internal-only, so the default agent never runs a first-run bootstrap or impersonates the business agent.

### 4. Build the knowledge base
```bash
python3 scripts/build_kb.py --source "$KB_SOURCE" --out workspace_<agent>/faq \
  --lang "$KB_LANG" --entity "$ENTITY" --expect "$EXPECT"
```
Produces `faq/faq_<lang>.md` (continuous `QA-1..N`, four sections: question / precise answer / next step / compliance basis), `faq/services.md` (scope + verification skeleton) and `qa.json` for review.

Validation gate before going live:
- count equals `--expect`
- numbering contiguous `1..N`, no duplicates
- every entry has all four sections
- no placeholder text (`TODO`, `{{...}}`) left

### 5. CLI wrapper (mandatory on Linux/systemd)
Create `/usr/local/bin/openclaw-<profile>` from `templates/openclaw-profile.wrapper`:
```sh
export OPENCLAW_PROFILE=<profile>
export OPENCLAW_STATE_DIR=/root/.openclaw-<profile>
export OPENCLAW_CONFIG_PATH=/root/.openclaw-<profile>/openclaw.json
export OPENCLAW_GATEWAY_PORT=<port>
export OPENCLAW_SYSTEMD_UNIT=openclaw-gateway-<profile>.service
exec /usr/bin/openclaw "$@"
```
**Why:** `openclaw --profile <p> gateway status|restart|stop` resolves the *default* unit regardless of `--profile`; only `OPENCLAW_SYSTEMD_UNIT` fixes it. Without the wrapper, restart/stop can hit the main gateway.

### 6. Start and verify
```bash
systemctl --user daemon-reload
systemctl --user enable --now openclaw-gateway-$PROFILE.service
openclaw-$PROFILE gateway status            # unit file + port must match, probe ok
openclaw-$PROFILE gateway call sessions.list --json
```
If RPC needs an explicit target:
```bash
TOKEN=$(python3 -c 'import json;print(json.load(open("/root/.openclaw-'$PROFILE'/openclaw.json"))["gateway"]["auth"]["token"])')
openclaw --profile $PROFILE gateway call sessions.list --url ws://127.0.0.1:$PORT --token "$TOKEN" --json
```

### 7. Channel hookup (manual where API-gated)
- **whatsapp**: pair via QR (`openclaw-$PROFILE qr` / WhatsApp login), then send a test message.
- **wechat-kf**: needs `corpId`, `appSecret`, `token`, `encodingAESKey`, `webhookPath`, plus backend authorization ("可调用接口的应用" + "通过API管理微信客服账号"). Verify `gettoken` → `kf/account/list`; errcode **48002** means authorization is still missing — report it, do not retry blindly.

## Verification checklist

- [ ] `~/.openclaw-<profile>/openclaw.json` valid (`config validate`), mode 600
- [ ] unit `openclaw-gateway-<profile>.service` active, port matches config
- [ ] wrapper exists, executable, `gateway status` shows the profile unit
- [ ] `workspace_<agent>/` has all 8 md files + `faq/` + `memory/`
- [ ] KB counts/numbering/sections validated, no placeholders
- [ ] admin `workspace/` has no `BOOTSTRAP.md`
- [ ] smoke: one inbound message → reply in the KB language

## Gotchas (learned the hard way)

1. **Unit resolution**: `--profile` does not affect systemd unit lookup. Always use the wrapper.
2. **Config watcher**: the running gateway may rewrite `openclaw.json` and drop unknown/legacy fields. After edits re-run `config validate` and diff the file.
3. **Secrets**: keys live in `openclaw.json` (mode 600) and service env; never commit or echo them.
4. **`faq/` is gitignored** in agent workspaces — backups must copy files explicitly.
5. **Ports**: the main gateway owns 18789; confirm a free `<n>789` with `ss -ltn`.
6. **First boot is slow** (extensions can be 100MB+); `gateway status` probe may time out before warm.
7. **Session store**: `agents/<agent>/sessions/sessions.json`; reset stale sessions via the `sessions.reset` RPC after identity/KB changes so the agent reloads workspace context.
8. **Don't hand-write the unit** unless onboarding failed to suffix it.

## Rollback

```bash
systemctl --user disable --now openclaw-gateway-$PROFILE.service
rm /root/.config/systemd/user/openclaw-gateway-$PROFILE.service
mv /root/.openclaw-$PROFILE /root/.openclaw-$PROFILE.bak-$(date +%Y%m%d)
rm /usr/local/bin/openclaw-$PROFILE
```
Prefer moving the state dir aside over deleting it.

## Files

- `scripts/create_profile.sh` — end-to-end driver (preflight → onboard → config → workspace → KB → unit → wrapper → verify)
- `scripts/configure_profile.py` — idempotent `openclaw.json` merge
- `scripts/build_kb.py` — Q&A source → `faq/faq_<lang>.md` + `services.md`
- `templates/openclaw-profile.wrapper`, `templates/gateway.service`, `templates/workspace/*.md`
