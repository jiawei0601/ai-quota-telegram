#!/usr/bin/env python3
"""ai-quota-telegram：把 Claude Code／Codex CLI／Antigravity CLI（agy）目前的額度用量與重置時間推到 Telegram。

用法：
  python ai_quota_report.py            # 查詢並推 Telegram
  python ai_quota_report.py --dry-run  # 只印在終端，不推
  python ai_quota_report.py --only claude,codex   # 只查指定工具

設定（擇一，優先序由高到低）：
  1. 環境變數 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
  2. 腳本同目錄的 .env
  3. ~/.ai-quota-telegram.env

資料來源（都不會消耗模型額度，憑證只在本機讀取、只送往各家官方端點）：
  Claude : GET https://api.anthropic.com/api/oauth/usage，用 ~/.claude/.credentials.json 的 accessToken；
           token 過期時先用一次最小 haiku 呼叫讓 claude CLI 刷新（CLAUDE_AUTO_REFRESH=0 可關），
           仍失敗才退回 ~/.claude/rate-limits.json（終端 claude 的 statusline 落地檔，若有）
  Codex  : GET https://chatgpt.com/backend-api/wham/usage，用 ~/.codex/auth.json 的 access_token；
           端點失敗退回 ~/.codex/sessions 最新 session 記錄的 rate_limits
  agy    : 執行 `agy --print "/quota"`，解析回傳的 TSV
"""
import glob
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows 隱藏視窗預設 cp950，emoji 會炸
except Exception:
    pass

HOME = Path.home()
HERE = Path(__file__).resolve().parent


# ---------- 共用 ----------
def load_config():
    cfg = {}
    for p in (HOME / ".ai-quota-telegram.env", HERE / ".env"):
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg


def fmt_ts(v):
    """epoch 秒或 ISO 字串 → 本地時間 mm/dd HH:MM"""
    try:
        if isinstance(v, (int, float)):
            return time.strftime("%m/%d %H:%M", time.localtime(v))
        if isinstance(v, str):
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone().strftime("%m/%d %H:%M")
    except Exception:
        pass
    return "?"


def pct(v):
    return "?" if v is None else f"{float(v):.0f}%"


def get_json(url, headers):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "ai-quota-telegram", **headers})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


# ---------- Claude Code ----------
def claude_refresh_token():
    """access token 過期時，用一次最小的 haiku 呼叫讓 Claude Code 自己刷新 token（耗幾百 token，可用
    CLAUDE_AUTO_REFRESH=0 關閉）。`claude auth status` 不會刷新，實測只有真的發模型請求才會。"""
    if os.environ.get("CLAUDE_AUTO_REFRESH", "1") == "0":
        return False
    try:
        subprocess.run(["claude", "-p", "回覆 ok", "--model", "haiku", "--max-turns", "1"], capture_output=True,
                       timeout=120, shell=(os.name == "nt"), cwd=os.environ.get("TEMP") or os.environ.get("TMPDIR") or ".")
        return True
    except Exception:
        return False


def claude():
    d = HOME / ".claude"
    try:
        c = json.load(open(d / ".credentials.json", encoding="utf-8"))["claudeAiOauth"]
        if c.get("expiresAt", 0) / 1000 <= time.time() and claude_refresh_token():
            c = json.load(open(d / ".credentials.json", encoding="utf-8"))["claudeAiOauth"]
        if c.get("expiresAt", 0) / 1000 > time.time():
            u = get_json("https://api.anthropic.com/api/oauth/usage",
                         {"Authorization": "Bearer " + c["accessToken"], "anthropic-beta": "oauth-2025-04-20"})
            fh, sd = u.get("five_hour") or {}, u.get("seven_day") or {}
            lines = [f"5h 已用 {pct(fh.get('utilization'))}（重置 {fmt_ts(fh.get('resets_at'))}）",
                     f"7日 已用 {pct(sd.get('utilization'))}（重置 {fmt_ts(sd.get('resets_at'))}）"]
            for key, label in (("seven_day_opus", "7日 Opus"), ("seven_day_sonnet", "7日 Sonnet")):
                w = u.get(key) or {}
                if w.get("utilization") is not None:
                    lines.append(f"{label} 已用 {pct(w.get('utilization'))}")
            return lines
        note = "token 已過期，退回 statusline 檔"
    except FileNotFoundError:
        return ["⚠ 找不到 ~/.claude/.credentials.json，請先在本機登入 Claude Code"]
    except Exception as e:
        note = f"端點失敗 {type(e).__name__}，退回 statusline 檔"
    try:
        s = json.load(open(d / "rate-limits.json", encoding="utf-8"))
        rl = s.get("rate_limits") or {}
        fh, sd = rl.get("five_hour") or {}, rl.get("seven_day") or {}
        age = int((time.time() - s.get("ts", 0)) / 60)
        return [f"5h 已用 {pct(fh.get('used_percentage'))}（重置 {fmt_ts(fh.get('resets_at'))}）",
                f"7日 已用 {pct(sd.get('used_percentage'))}（重置 {fmt_ts(sd.get('resets_at'))}）",
                f"⚠ {note}（{age} 分鐘前）；開一次終端 claude 即可刷新 token"]
    except Exception:
        return [f"⚠ 拿不到（{note}，也沒有 statusline 檔）；開一次終端 claude 即可刷新 token"]


# ---------- Codex CLI ----------
def codex_window_lines(primary, secondary, pkey="used_percent", wkey="limit_window_seconds", rkey="reset_at"):
    lines = []
    for w in (primary, secondary):
        if not w:
            continue
        secs = w.get(wkey) or 0
        win = "5h" if secs == 18000 else "7日" if secs == 604800 else f"{secs // 60}分"
        lines.append(f"{win} 已用 {pct(w.get(pkey))}（重置 {fmt_ts(w.get(rkey))}）")
    return lines


def codex():
    try:
        auth = json.load(open(HOME / ".codex" / "auth.json", encoding="utf-8"))
        t = auth.get("tokens") or {}
        if not t.get("access_token"):
            return ["⚠ ~/.codex/auth.json 沒有 ChatGPT 登入 token（API key 模式沒有訂閱額度可查）"]
        u = get_json("https://chatgpt.com/backend-api/wham/usage",
                     {"Authorization": "Bearer " + t["access_token"], "ChatGPT-Account-Id": t.get("account_id", "")})
        rl = u.get("rate_limit") or {}
        lines = codex_window_lines(rl.get("primary_window"), rl.get("secondary_window"))
        for extra in u.get("additional_rate_limits") or []:
            erl = extra.get("rate_limit") or {}
            for l in codex_window_lines(erl.get("primary_window"), erl.get("secondary_window")):
                lines.append(f"{extra.get('limit_name')} {l}")
        cr = u.get("credits") or {}
        tail = f"方案 {u.get('plan_type')}｜即時"
        if cr.get("has_credits"):
            tail += f"｜credits {cr.get('balance')}"
        if rl.get("limit_reached"):
            tail = "⛔ 已達上限｜" + tail
        lines.append(tail)
        return lines
    except FileNotFoundError:
        return ["⚠ 找不到 ~/.codex/auth.json，請先 `codex login`"]
    except Exception as e:
        note = f"端點失敗 {type(e).__name__}，退回本機快照"
    return codex_local(note)


def codex_local(note):
    files = sorted(glob.glob(str(HOME / ".codex" / "sessions" / "*" / "*" / "*" / "*.jsonl")),
                   key=os.path.getmtime, reverse=True)[:20]
    best = None
    for f in files:
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if '"rate_limits"' not in line:
                        continue
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    rl = (ev.get("payload") or {}).get("rate_limits")
                    if rl and rl.get("primary"):
                        best = (ev.get("timestamp") or "", rl)
        except Exception:
            continue
        if best:
            break
    if not best:
        return [f"⚠ {note}，本機也沒有任何 session 的 rate_limits 紀錄"]
    ts, rl = best
    for w in (rl.get("primary"), rl.get("secondary")):
        if w and "window_minutes" in w:
            w["limit_window_seconds"] = (w.get("window_minutes") or 0) * 60
    lines = codex_window_lines(rl.get("primary"), rl.get("secondary"), rkey="resets_at")
    age = "?"
    try:
        age = int((datetime.now(timezone.utc) - datetime.fromisoformat(ts.replace("Z", "+00:00"))).total_seconds() / 3600)
    except Exception:
        pass
    lines.append(f"方案 {rl.get('plan_type')}｜⚠ {note}（{age} 小時前，最近一次 codex 對話）")
    return lines


# ---------- Antigravity CLI (agy) ----------
def agy():
    try:
        r = subprocess.run(["agy", "--print", "/quota", "--print-timeout", "1m"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=120,
                           cwd=os.environ.get("TEMP") or os.environ.get("TMPDIR") or ".")
        out = r.stdout.strip()
    except FileNotFoundError:
        return ["⚠ 找不到 agy 指令，請確認 Antigravity CLI 已安裝且在 PATH"]
    except Exception as e:
        return [f"⚠ agy 執行失敗 {type(e).__name__}"]
    lines = []
    for row in out.splitlines():
        parts = [p.strip() for p in row.split("\t")]
        if len(parts) < 4:
            continue
        model, kind, remain, reset = parts[:4]
        model = "Gemini" if model.startswith("Gemini") else "Claude/GPT"
        win = "7日" if "Weekly" in kind else "5h"
        try:
            used = 100 - float(remain.rstrip("%"))
        except Exception:
            used = None
        lines.append(f"{model} {win} 已用 {pct(used)}（重置 {fmt_ts(reset)}）")
    return lines or [f"⚠ agy 回傳無法解析：{out[:120]}"]


# ---------- Telegram ----------
def send_telegram(cfg, text):
    token, chat = cfg.get("TELEGRAM_BOT_TOKEN"), cfg.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        raise SystemExit("缺少 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID，請參考 README 設定 .env")
    for i in range(0, len(text), 4096):
        data = urllib.parse.urlencode({"chat_id": chat, "text": text[i:i + 4096],
                                       "disable_web_page_preview": "true"}).encode()
        with urllib.request.urlopen(urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage", data=data), timeout=20) as r:
            json.load(r)


SOURCES = {"claude": ("🟠 Claude Code", claude), "codex": ("🟢 Codex", codex), "agy": ("🔵 agy (Antigravity)", agy)}


def main(argv):
    only = None
    if "--only" in argv:
        only = argv[argv.index("--only") + 1].split(",")
    now = datetime.now().strftime("%m/%d %H:%M")
    parts = []
    for key, (title, fn) in SOURCES.items():
        if only and key not in only:
            continue
        parts.append(f"\n{title}\n" + "\n".join("  " + l for l in fn()))
    msg = f"📊 AI 額度 {now}\n" + "\n".join(parts)
    print(msg)
    if "--dry-run" in argv:
        return 0
    try:
        send_telegram(load_config(), msg)
        print("TG: sent")
        return 0
    except Exception as e:
        print(f"TG: FAILED {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
