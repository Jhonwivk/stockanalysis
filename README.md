# stockanalysis

**A 股盘面复盘自动化**：拉公开行情 → **DeepSeek 按本地同款模板写完整复盘** → 发邮箱。  
适合 fork 自用；**不含**私人研报与密钥。

## 与本地 Cursor 的关系

| | Cursor 本地 Agent | GitHub Actions + DeepSeek |
|---|---|---|
| 模板 / 心法 | 同一套 `references/` | 同一套 |
| 主线三行、明日多预案 | ✅ | ✅（强制写入 prompt） |
| 浏览网页 / 多工具 | ✅ | ❌（当前仅行情 JSON） |
| 比特级一字不差 | — | **做不到**；结构与口径对齐 |

## 仓库内容

| 路径 | 说明 |
|---|---|
| `scripts/fetch_market_data.py` | 行情 |
| `scripts/generate_llm_review.py` | **DeepSeek 完整复盘** |
| `scripts/generate_daily_quant_review.py` | 无 Key 时的定量回退 |
| `scripts/send_report_email.py` / `run_daily_email.sh` | 发邮 |
| `references/report-template.md` · `core-xinfa.md` | 与本地技能对齐的模板 |
| `.github/workflows/daily-market-email.yml` | 工作日 20:30（北京） |

## 快速开始

```bash
cp .env.example .env
# 填写 DEEPSEEK_API_KEY、SMTP_*、EMAIL_TO
chmod +x scripts/*.sh scripts/*.py
./scripts/run_daily_email.sh
```

### Actions Secrets（必填）

| Secret | 用途 |
|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `DEEPSEEK_BASE_URL` | 可选，默认 `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | 可选，默认 `deepseek-chat` |
| `SMTP_*` / `EMAIL_*` | 发信（见 `.env.example`） |

Settings → Secrets and variables → **Actions**（不是 Agents / 不是 Runners）。

## 安全

- `.env` 与报告 md/pdf 已 gitignore  
- **永远不要**把 API Key / 邮箱授权码提交进仓库或发在聊天里  

## 免责

仅供研究，不构成投资建议。
