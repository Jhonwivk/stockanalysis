# stockanalysis

开源 **A 股盘面复盘工具包**：拉公开行情 → LLM 按仓库内模板生成复盘 → 转 PDF →（可选）邮件发送。

**不依赖 Cursor / Claude Skill。** fork 后改配置即可自用或二次分发。

## 别人怎么用

1. **Fork** 本仓库  
2. 配 Secrets（本地用 `.env`，定时用 GitHub Actions Secrets）  
3. 跑本地一键脚本，或打开 Actions 手动 / 定时跑  

产出：**PDF 复盘**（中间 Markdown 不邮寄、Actions 也不上传 Markdown）。

## 仓库结构

| 路径 | 作用 |
|---|---|
| `scripts/fetch_market_data.py` | 拉东财等公开行情（JSON） |
| `scripts/generate_llm_review.py` | 按模板调 DeepSeek 写完整复盘 |
| `scripts/generate_daily_quant_review.py` | 无 API Key 时的定量兜底稿 |
| `scripts/md_to_pdf.py` | Markdown → PDF |
| `scripts/send_report_email.py` | 发邮件（附件建议仅 PDF） |
| `scripts/run_daily_email.sh` | 本地一键：拉数→生成→PDF→邮件 |
| `references/report-template.md` | 报告章节结构（可改） |
| `references/core-xinfa.md` | 主线判定与写法口径（可改） |
| `knowledge/` | 方法论文档备查（可改） |
| `.github/workflows/daily-market-email.yml` | 工作日北京 20:30 定时 |

定制盘面口径：直接改 `references/` 与 `knowledge/`，无需安装任何 Agent Skill。

## 本地快速开始

```bash
git clone https://github.com/<你的用户名>/stockanalysis.git
cd stockanalysis
python3 -m pip install -r requirements.txt
# PDF 中文：macOS/Linux 需本机有 Noto/思源等 CJK 字体；GitHub Actions 工作流会自动装字体

cp .env.example .env
# 编辑 .env：至少 DEEPSEEK_API_KEY；要发邮再填 SMTP_* / EMAIL_*

chmod +x scripts/*.sh scripts/*.py
./scripts/run_daily_email.sh              # 今天
./scripts/run_daily_email.sh 20260715     # 指定交易日 YYYYMMDD
```

未配置 `DEEPSEEK_API_KEY` 时会走定量稿，仍可出 PDF。

换模型：`.env` 里改 `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`（OpenAI 兼容接口即可）。

## GitHub Actions（定时邮件）

Settings → Secrets and variables → **Actions** 添加：

| Secret | 必填 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 是* | 完整复盘；缺省则定量兜底 |
| `DEEPSEEK_BASE_URL` | 否 | 默认 `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | 否 | 默认 `deepseek-chat` |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` / `SMTP_SSL` | 发邮时 | 如 163：`smtp.163.com` / `465` / `true` |
| `EMAIL_TO` | 发邮时 | 收件人 |
| `EMAIL_FROM` | 发邮时 | 发件人（常与 SMTP_USER 相同） |
| `EMAIL_FROM_NAME` | 否 | 显示名 |

\* 无 Key 时仍可跑通定量 PDF；完整叙述需要 Key。

Actions → **Daily market email** → Enable workflow → **Run workflow** 先手动验一次。  
默认 cron：UTC `30 12 * * 1-5` ≈ 北京工作日 20:30。

交付：Artifacts / 邮件 **仅 PDF**。

## 与「Cursor 本地写稿」的关系（可选了解）

本仓库是独立流水线。若你本机另有 Agent 手工写稿，可与这里共用同一套 `references/`，但 **用不用 Cursor 都不影响别人跑本项目**。

## 安全

- 勿提交 `.env`、密钥、私人研报  
- 邮箱请用授权码 / App Password，不要用登录密码  
- 密钥曾泄露过请立刻轮换  

## 免责

仅供研究学习，不构成投资建议。
