#!/usr/bin/env python3
"""Idempotent openclaw.json merge for a new business profile.

Usage:
  configure_profile.py --config ~/.openclaw-mli/openclaw.json \
      --profile mli --agent mli --port 24789 \
      --workspace /root/.openclaw-mli/workspace_mli \
      --tavily-key tvly-xxx [--channel whatsapp|wechat-kf|none]
"""
import argparse
import json
import os
import re
import shutil
import time

MINIMAL_ALLOW = ["read", "message", "write", "edit", "memory_search", "memory_get"]
MINIMAL_DENY = [
    "exec", "process", "code_execution", "apply_patch", "browser", "canvas",
    "web_search", "web_fetch", "cron", "gateway", "sessions_spawn",
    "sessions_send", "sessions_history", "sessions_list", "skill_workshop",
    "session_status",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--agent", required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--tavily-key", required=True)
    ap.add_argument("--channel", default="whatsapp", choices=["whatsapp", "wechat-kf", "none"])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    name_pattern = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
    if not name_pattern.fullmatch(a.profile):
        ap.error("--profile must contain lowercase letters, digits, '-' or '_', and start with a letter or digit")
    if not name_pattern.fullmatch(a.agent):
        ap.error("--agent must contain lowercase letters, digits, '-' or '_', and start with a letter or digit")
    if a.agent == "main":
        ap.error("--agent 'main' is reserved for the admin agent")
    if not 1 <= a.port <= 65535:
        ap.error("--port must be between 1 and 65535")

    cfg = json.load(open(a.config, encoding="utf-8"))
    state_dir = os.path.dirname(os.path.abspath(a.config))

    agents = cfg.setdefault("agents", {})
    defaults = agents.setdefault("defaults", {})
    defaults["workspace"] = defaults.get("workspace") or os.path.join(state_dir, "workspace")
    defaults.setdefault("models", {})["deepseek/deepseek-flash"] = {"alias": "DeepSeek"}
    defaults["model"] = {"primary": "deepseek/deepseek-flash"}

    lst = agents.setdefault("list", [{"id": "main"}])
    if not any(x.get("id") == "main" for x in lst):
        lst.insert(0, {"id": "main"})
    entry = next((x for x in lst if x.get("id") == a.agent), None)
    if entry is None:
        entry = {"id": a.agent}
        lst.append(entry)
    entry.update({
        "name": a.agent,
        "workspace": a.workspace,
        "agentDir": os.path.join(state_dir, "agents", a.agent, "agent"),
        "model": "deepseek/deepseek-flash",
        "memorySearch": {"provider": "none"},
        "tools": {
            "profile": "minimal",
            "alsoAllow": MINIMAL_ALLOW,
            "deny": MINIMAL_DENY,
            "fs": {"workspaceOnly": True},
        },
    })

    gw = cfg.setdefault("gateway", {})
    gw["mode"] = "local"
    gw["bind"] = gw.get("bind") or "loopback"
    gw["port"] = a.port
    gw.setdefault("auth", {}).setdefault("mode", "token")
    if not gw["auth"].get("token"):
        gw["auth"]["token"] = os.urandom(24).hex()
    gw.setdefault("controlUi", {}).setdefault("allowInsecureAuth", True)
    gw.setdefault("tailscale", {"mode": "off", "resetOnExit": False})

    cfg.setdefault("session", {})["dmScope"] = "per-account-channel-peer"
    cfg.setdefault("tools", {}).setdefault("profile", "full")
    cfg["tools"].setdefault("web", {}).setdefault("search", {}).update(
        {"provider": "tavily", "enabled": True}
    )

    plugins = cfg.setdefault("plugins", {}).setdefault("entries", {})
    plugins.setdefault("deepseek", {}).update({"enabled": True})
    tavily = plugins.setdefault("tavily", {"enabled": True})
    tavily["enabled"] = True
    tavily.setdefault("config", {}).setdefault("webSearch", {})["apiKey"] = a.tavily_key

    if a.channel != "none":
        ch = cfg.setdefault("channels", {}).setdefault(a.channel, {})
        if a.channel == "whatsapp":
            ch.setdefault("selfChatMode", False)
            ch["dmPolicy"] = ch.get("dmPolicy", "open")
            ch["allowFrom"] = ch.get("allowFrom", ["*"])
        bindings = cfg.setdefault("bindings", [])
        if not any(b.get("agentId") == a.agent and b.get("match", {}).get("channel") == a.channel for b in bindings):
            bindings.append({
                "type": "route",
                "agentId": a.agent,
                "match": {"channel": a.channel},
                "session": {"dmScope": "per-peer" if a.channel == "whatsapp" else "per-account-channel-peer"},
            })

    cfg.setdefault("logging", {})["file"] = os.path.join(state_dir, "openclaw.log")
    cfg.setdefault("meta", {})["lastTouchedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

    if a.dry_run:
        print(json.dumps({
            "dry_run": True,
            "profile": a.profile,
            "agent": a.agent,
            "port": a.port,
            "channel": a.channel,
            "config": a.config,
            "workspace": a.workspace,
            "secrets": "redacted",
        }, ensure_ascii=False, indent=2))
        return

    bak = a.config + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(a.config, bak)
    tmp = a.config + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, a.config)
    os.chmod(a.config, 0o600)
    print(f"config updated: {a.config} (backup {os.path.basename(bak)})")


if __name__ == "__main__":
    main()
