# stockanalysis

A 股盘面复盘工具包：拉公开行情 → 按仓库模板用 LLM 生成复盘 → 转 PDF →（可选）邮件发送。

fork 后改配置即可自用；**不依赖 Cursor / Claude Skill**。

## 快速开始

```bash
git clone https://github.com/Jhonwivk/stockanalysis.git
cd stockanalysis
python3 -m pip install -r requirements.txt
# PDF 中文需本机 CJK 字体（如 Noto Sans CJK）；GitHub Actions 会自动安装

cp .env.example .env
# 编辑 .env：完整复盘需 DEEPSEEK_API_KEY；发邮再填 SMTP_* / EMAIL_*

chmod +x scripts/*.sh
./scripts/run_daily.sh              # 今天（上海时区）
./scripts/run_daily.sh 20260715     # 指定交易日 YYYYMMDD
```

无 `DEEPSEEK_API_KEY` 时走定量兜底稿，仍可出 PDF。产出在 `output/`（中间 Markdown 生成后删除，只保留 PDF）。

换模型：改 `.env` 里 `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`（OpenAI 兼容接口即可）。

## 目录

| 路径 | 作用 |
|---|---|
| `scripts/fetch_market_data.py` | 拉东财等公开行情 |
| `scripts/generate_llm_review.py` | 按模板调 LLM 写完整复盘 |
| `scripts/generate_quant_review.py` | 无 API Key 时的定量稿 |
| `scripts/md_to_pdf.py` | Markdown → PDF |
| `scripts/send_email.py` | 发邮件（流水线只附 PDF） |
| `scripts/run_daily.sh` | 本地一键：拉数→生成→PDF→邮件 |
| `scripts/install_local_schedule.sh` | macOS launchd：工作日约 08:30 跑 `run_daily.sh` |
| `prompts/report-template.md` | 报告章节结构 |
| `prompts/writing-rules.md` | 主线判定与写法口径 |
| `docs/` | 方法论文档（可选阅读） |
| `output/` | 生成物（已 gitignore） |
| `.github/workflows/daily.yml` | 工作日北京 20:30 定时 |

改盘面口径：编辑 `prompts/` 即可。

**本地定时（Mac）**：`./scripts/install_local_schedule.sh` → 每天 08:30（本机时区）launchd；日志 `~/Library/Logs/stockanalysis-daily-review.log`；停用：`./scripts/install_local_schedule.sh uninstall`。

## GitHub Actions

Settings → Secrets and variables → **Actions**：

| Secret | 说明 |
|---|---|
| `DEEPSEEK_API_KEY` | 完整复盘；缺省则定量兜底 |
| `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` | 可选 |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` / `SMTP_SSL` | 发邮时必填 |
| `EMAIL_TO` / `EMAIL_FROM` | 发邮时必填 |
| `EMAIL_FROM_NAME` | 可选 |

Actions → **Daily market review** → **Run workflow** 先手动验一次。  
cron：`30 12 * * 1-5`（UTC）≈ 北京工作日 20:30。  
Artifacts / 邮件 **仅 PDF**。

## 安全与免责

- 勿提交 `.env`、密钥、私人研报  
- 邮箱用授权码，勿用登录密码  
- 仅供研究学习，不构成投资建议  
