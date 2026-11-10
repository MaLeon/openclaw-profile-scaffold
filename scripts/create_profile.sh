#!/usr/bin/env bash
# End-to-end OpenClaw profile scaffold.
#
# Example:
#   ./create_profile.sh --profile acme --port 25789 \
#       --kb /root/predoc_acme/500QA.docx --entity "PT Acme Indonesia" \
#       --tavily-key tvly-xxx --deepseek-key sk-xxx \
#       --channel whatsapp --expect 500
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE="" PORT="" AGENT="" KB="" ENTITY="" TAVILY_KEY="" DEEPSEEK_KEY=""
CHANNEL="whatsapp" KB_LANG="id" EXPECT=0 SKIP_ONBOARD=0

while [ $# -gt 0 ]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --agent) AGENT="$2"; shift 2 ;;
    --kb) KB="$2"; shift 2 ;;
    --entity) ENTITY="$2"; shift 2 ;;
    --tavily-key) TAVILY_KEY="$2"; shift 2 ;;
    --deepseek-key) DEEPSEEK_KEY="$2"; shift 2 ;;
    --channel) CHANNEL="$2"; shift 2 ;;
    --lang) KB_LANG="$2"; shift 2 ;;
    --expect) EXPECT="$2"; shift 2 ;;
    --skip-onboard) SKIP_ONBOARD=1; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

die() { echo "ERROR: $*" >&2; exit 1; }
say() { echo -e "\n== $* =="; }
render_template() {
  python3 - "$1" "$2" "$PROFILE" "$AGENT" "$PORT" "$ENTITY" "$CHANNEL" "$KB_LANG" <<'PY'
import sys

source, destination, profile, agent, port, entity, channel, kb_lang = sys.argv[1:]
values = {
    "{{PROFILE}}": profile,
    "{{AGENT}}": agent,
    "{{PORT}}": port,
    "{{ENTITY}}": entity,
    "{{CHANNEL}}": channel,
    "{{KB_LANG}}": kb_lang,
}
with open(source, encoding="utf-8") as f:
    rendered = f.read()
for token, value in values.items():
    rendered = rendered.replace(token, value)
with open(destination, "w", encoding="utf-8") as f:
    f.write(rendered)
PY
}

[ -n "$PROFILE" ] || die "--profile required"
[ -n "$PORT" ] || die "--port required"
[ -n "$KB" ] || die "--kb required"
[ -n "$ENTITY" ] || die "--entity required"
[ -n "$TAVILY_KEY" ] || die "--tavily-key required"
[[ "$PROFILE" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die "invalid profile: use lowercase letters, digits, '-' or '_'"
[[ -z "$AGENT" || "$AGENT" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die "invalid agent: use lowercase letters, digits, '-' or '_'"
[[ "$PORT" =~ ^[0-9]{1,5}$ ]] || die "invalid port: expected an integer from 1 to 65535"
(( 10#$PORT >= 1 && 10#$PORT <= 65535 )) || die "invalid port: expected an integer from 1 to 65535"
PORT=$((10#$PORT))
AGENT="${AGENT:-$PROFILE}"
[[ "$AGENT" != "main" ]] || die "--agent cannot be 'main'; main is reserved for the admin agent"
STATE="/root/.openclaw-$PROFILE"
WS="$STATE/workspace_$AGENT"

say "0. preflight"
ss -ltn 2>/dev/null | grep -q ":$PORT " && die "port $PORT already in use"
[ -e "$STATE" ] && die "$STATE already exists (move it aside first)"
command -v openclaw >/dev/null || die "openclaw CLI not found"
command -v python3 >/dev/null || die "python3 not found"
[ -f "$KB" ] || die "KB source not found: $KB"
case "$KB" in
  *.docx) python3 -c 'import docx' 2>/dev/null || die "python-docx missing (pip3 install python-docx)" ;;
  *.xlsx|*.xlsm) python3 -c 'import openpyxl' 2>/dev/null || die "openpyxl missing" ;;
esac
echo "ok: profile=$PROFILE port=$PORT agent=$AGENT entity=$ENTITY kb=$KB"

if [ "$SKIP_ONBOARD" = "0" ]; then
  say "1. onboard (state dir, config, workspace seed, unit)"
  [ -n "$DEEPSEEK_KEY" ] || die "--deepseek-key required for onboarding"
  openclaw onboard --profile "$PROFILE" --non-interactive --accept-risk \
    --flow quickstart --mode local \
    --auth-choice deepseek-api-key --deepseek-api-key "$DEEPSEEK_KEY" \
    --gateway-auth token --gateway-bind loopback --gateway-port "$PORT" \
    --install-daemon --skip-channels --skip-skills --skip-hooks
else
  say "1. onboard skipped"
fi

say "2. config merge (agents, plugins, channels, bindings)"
mkdir -p "$WS"
python3 "$SKILL_DIR/scripts/configure_profile.py" \
  --config "$STATE/openclaw.json" --profile "$PROFILE" --agent "$AGENT" \
  --port "$PORT" --workspace "$WS" --tavily-key "$TAVILY_KEY" --channel "$CHANNEL"
openclaw --profile "$PROFILE" config validate || die "config validate failed"

say "3. workspace files"
for tpl in "$SKILL_DIR"/templates/workspace/*; do
  base="$(basename "$tpl")"
  [ "$base" = "gitignore" ] && base=".gitignore"
  [ "$base" = "BOOTSTRAP.md" ] && continue
  render_template "$tpl" "$WS/$base"
done
mkdir -p "$WS/memory"
cat > "$WS/memory/$(date +%F).md" <<EOF
# $(date +%F)

## Profile 初始化

- profile: \`$PROFILE\`｜agent: \`$AGENT\`｜端口: $PORT｜主体: $ENTITY
- 知识库来源: \`$KB\`（语言: $KB_LANG）
- 渠道: $CHANNEL（配对/授权待完成）
EOF

if [ -f "$STATE/workspace/BOOTSTRAP.md" ]; then
  mkdir -p "$STATE/backups/workspace-admin-$(date +%Y%m%d)"
  mv "$STATE/workspace/BOOTSTRAP.md" "$STATE/backups/workspace-admin-$(date +%Y%m%d)/BOOTSTRAP.md.removed"
fi
printf '%s\n' "# IDENTITY.md - Admin Workspace" "" \
  "- **Name:** $PROFILE-admin" \
  "- **Role:** 管理/调试工作区，不对外、不承接客户对话；业务由 \`$AGENT\` agent 在 \`$WS\` 处理。" \
  > "$STATE/workspace/IDENTITY.md"

say "4. knowledge base"
python3 "$SKILL_DIR/scripts/build_kb.py" --source "$KB" --out "$WS/faq" \
  --lang "$KB_LANG" --entity "$ENTITY" --expect "$EXPECT"

say "5. systemd unit"
UNIT="openclaw-gateway-$PROFILE.service"
UNIT_PATH="/root/.config/systemd/user/$UNIT"
if [ ! -f "$UNIT_PATH" ]; then
  echo "unit missing; generating from template"
  mkdir -p "$(dirname "$UNIT_PATH")"
  render_template "$SKILL_DIR/templates/gateway.service" "$UNIT_PATH"
  systemctl --user daemon-reload
fi
grep -q "OPENCLAW_PROFILE=$PROFILE" "$UNIT_PATH" || die "unit does not carry profile env: $UNIT_PATH"
echo "unit ok: $UNIT"

say "6. CLI wrapper"
render_template "$SKILL_DIR/templates/openclaw-profile.wrapper" "/usr/local/bin/openclaw-$PROFILE"
chmod +x "/usr/local/bin/openclaw-$PROFILE"
sh -n "/usr/local/bin/openclaw-$PROFILE" || die "wrapper syntax error"

say "7. start + verify"
systemctl --user enable --now "$UNIT"
sleep 5
openclaw-"$PROFILE" gateway status || die "gateway status failed; inspect the unit logs before continuing"

cat <<EOF

== done ==
profile : $PROFILE
state   : $STATE
workspace: $WS
unit    : $UNIT
wrapper : /usr/local/bin/openclaw-$PROFILE
next    : pair the channel, then send a test message and confirm the reply language.
EOF
