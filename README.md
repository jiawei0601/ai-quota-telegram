# ai-quota-telegram

把 **Claude Code**、**Codex CLI**、**Antigravity CLI（agy）** 三個訂閱制 AI 工具目前的額度用量與重置時間，定時推送到你的 Telegram。

```
📊 AI 額度 09/12 21:24

🟠 Claude Code
  5h 已用 39%（重置 09/13 01:40）
  7日 已用 24%（重置 09/19 10:00）

🟢 Codex
  7日 已用 17%（重置 09/19 16:36）
  GPT-5.3-Codex-Spark 5h 已用 0%（重置 09/13 02:24）
  GPT-5.3-Codex-Spark 7日 已用 0%（重置 09/19 21:24）
  方案 prolite｜即時

🔵 agy (Antigravity)
  Gemini 7日 已用 61%（重置 09/18 10:47）
  Gemini 5h 已用 1%（重置 09/13 02:13）
  Claude/GPT 7日 已用 0%（重置 09/19 03:37）
  Claude/GPT 5h 已用 0%（重置 09/13 02:24）
```

## 特點

- **不消耗模型額度**：三個來源都是各家的用量端點或 CLI 內建指令，不會發出任何模型請求。
- **憑證不離開你的電腦**：直接讀取各 CLI 登入後留在本機的 token，只送往各家官方端點。本工具不需要你另外申請 API key，也不會把 token 寫到別處。
- **單一檔案、零相依**：只用 Python 標準函式庫。
- **有退路**：Claude token 過期時退回 statusline 落地檔，Codex 端點失敗時退回本機 session 快照，訊息會明確標註資料來源與新舊。

## 前置條件

| 項目 | 說明 |
|---|---|
| Python 3.8+ | `python --version` 能跑即可 |
| Claude Code | 已在本機以 claude.ai 帳號登入（Pro / Max）。會讀 `~/.claude/.credentials.json` |
| Codex CLI | 已 `codex login` 用 ChatGPT 帳號登入（API key 模式沒有訂閱額度可查）。會讀 `~/.codex/auth.json` |
| Antigravity CLI | `agy` 在 PATH 且已登入 Google 帳號。會執行 `agy --print "/quota"` |
| Telegram | 一個 Bot 與你的 chat id（下一節說明） |

三個工具不必全裝；沒裝的那一段會顯示提示，其餘照常。或用 `--only claude,codex` 只查有裝的。

## 設定 Telegram 串接

### 1. 建立 Bot、取得 Bot Token

1. 在 Telegram 搜尋 **@BotFather**，開始對話。
2. 送出 `/newbot`，依序回答 Bot 的顯示名稱與使用者名稱（使用者名稱必須以 `bot` 結尾，例如 `my_quota_bot`）。
3. BotFather 會回一段類似 `123456789:AAH-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` 的字串，這就是 **Bot Token**。妥善保存，任何人拿到它都能用你的 Bot 發訊息。

### 2. 取得你的 Chat ID

Bot 只能主動傳訊給「曾經跟它說過話」的人，所以要先開啟對話：

1. 在 Telegram 搜尋你剛建立的 Bot（用步驟 1 取的使用者名稱），點 **Start** 或隨便送一句話。
2. 在瀏覽器開啟下面網址（把 `<TOKEN>` 換成你的 Bot Token）：

   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```

3. 回傳的 JSON 裡找 `"chat":{"id":123456789, ...}`，那個數字就是 **Chat ID**。若回傳是空的 `result: []`，回 Telegram 再送一句話給 Bot 後重新整理。

   如果想推到群組：把 Bot 加進群組並在群組裡說一句話，同樣方法取得群組的 id，會是負數（例如 `-1001234567890`）。

### 3. 寫入設定檔

在本專案目錄把 `.env.example` 複製成 `.env`，填入兩個值：

```
TELEGRAM_BOT_TOKEN=123456789:AAH-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_CHAT_ID=123456789
```

`.env` 已在 `.gitignore` 內，不會被提交。也可以改放在家目錄 `~/.ai-quota-telegram.env`，或直接用同名環境變數（優先序：環境變數 > 專案 `.env` > 家目錄檔）。

### 4. 測試

```bash
python ai_quota_report.py --dry-run     # 只印在終端，確認三段資料都抓得到
python ai_quota_report.py               # 真的推一則到 Telegram，末行會印 TG: sent
```

推送失敗時末行會印 `TG: FAILED ...` 並回傳非零結束碼。常見原因：

| 訊息 | 原因 |
|---|---|
| `HTTP Error 401` | Bot Token 打錯 |
| `HTTP Error 400 chat not found` | Chat ID 打錯，或你還沒跟 Bot 說過話 |
| `HTTP Error 403 bot was blocked` | 你把 Bot 封鎖了 |

## 定時推送

### Windows（工作排程器）

```powershell
.\install-task.ps1
```

預設每天 08:00 起每 3 小時查一次、持續 14 小時（08、11、14、17、20 點），以隱藏視窗執行不會跳黑窗，錯過的時段會在開機登入後補跑一次。可以調整：

```powershell
.\install-task.ps1 -StartAt 09:00 -IntervalHours 2 -DurationHours 12
.\install-task.ps1 -Remove
```

注意：排程以你的帳號在「登入時執行」，電腦關機、睡眠或停在登入畫面時不會送；額度只在你使用電腦時才會變動，所以影響不大。

### macOS / Linux（cron）

```
0 8-22/3 * * * /usr/bin/python3 /path/to/ai_quota_report.py >> /tmp/ai-quota.log 2>&1
```

Claude 與 Codex 的憑證路徑在三個平台相同（`~/.claude`、`~/.codex`）；agy 需可在該機器的 PATH 找到並已登入。

## 各來源的細節與限制

### Claude Code

- 端點：`GET https://api.anthropic.com/api/oauth/usage`，帶本機 OAuth access token。
- access token 只活幾小時，由 Claude Code 自己刷新。若你長時間沒開 Claude Code，token 會過期，此時退回 `~/.claude/rate-limits.json`（終端 claude 的狀態列落地檔，不一定存在）並在訊息標「⚠ token 已過期」。開一次終端 `claude` 即可刷新。
- 「5h」是滾動 5 小時窗，「7日」是週額度。

### Codex CLI

- 端點：`GET https://chatgpt.com/backend-api/wham/usage`，帶 `~/.codex/auth.json` 的 access token 與帳號 id。
- 回傳的 `primary_window` / `secondary_window` 對應 5 小時與 7 日窗（不同方案的窗口組合不同，腳本依 `limit_window_seconds` 判斷）。`additional_rate_limits` 是額外模型（例如 Spark）的獨立額度，會另列。
- 端點失敗（例如 token 失效）時退回 `~/.codex/sessions` 內最新一次對話記錄的 `rate_limits`，訊息會標「快照 N 小時前」。

### Antigravity CLI（agy）

- 執行 `agy --print "/quota"`，這是 CLI 內建的 slash command，不會呼叫模型。回傳為四行 TSV：Gemini 與 Claude/GPT 兩組各有週與 5h 窗，值是「剩餘 %」，腳本轉成「已用 %」以和另外兩家一致。
- 在 Git Bash 下手動執行 `agy --print "/quota"` 時，MSYS 會把 `/quota` 轉成路徑而失效，請用 PowerShell 或 cmd；腳本內以 subprocess 陣列呼叫不受影響。
- 未啟動的窗口其重置時間會隨每次查詢往後推，這是端點行為不是錯誤。

## 安全性

- 三家 token 都只從本機檔案讀取、只送往該家官方端點，且不寫入任何其他檔案或日誌。
- `.env` 內的 Bot Token 等同 Bot 的密碼，不要提交或分享；外洩時到 @BotFather 用 `/revoke` 重發。
- 不建議把本工具連同三個 CLI 的登入態放到對外開放的伺服器上跑：那等於把三個個人帳號的長效 refresh token 放到攻擊面更大的機器上。放在自己的電腦上、電腦開著才推送，是刻意的取捨。

## 為什麼不用 API key

三個工具的額度都綁在訂閱帳號的 OAuth 登入態上，API key 走的是另一套按量計費，查不到訂閱額度。因此本工具只讀各 CLI 自己保存的登入 token。這些端點都是各 CLI 本身在用的內部端點，非公開文件化 API，未來可能變動；變動時訊息會退回本機快照並標註，不會靜默給錯數字。

## 授權

MIT
