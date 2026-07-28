# 视频场景 → 逐句英译 自动化工作流

当 Cursor Automation 被触发（Webhook / GitHub Issue / 定时队列）后，严格按本文档逐步骤执行。**不要跳过或合并任何步骤。**

```
Task Progress:
- [ ] 1. 解析入口，得到视频 url（与可选 date）
- [ ] 2. yt-dlp 下载音频（m4a）
- [ ] 3. 安装依赖（ffmpeg + openai-whisper，仅首次）
- [ ] 4. Whisper 转录（带时间戳，--model small）
- [ ] 5. 识别切分关键场景 + 逐句英译 + paraphrase
- [ ] 6. 生成 SVG（Node .mjs + svg-auto-height.mjs）
- [ ] 7. 质量自检
- [ ] 8. 更新 docs/index.json
- [ ] 9. Git 提交并推送到 main（**必须**，Pages 才能展示）
- [ ] 10. 清理临时文件 / 更新 pending 队列
```

---

## 入口（三种触发统一到同一 payload）

最终都要得到：

```json
{
  "url": "https://www.bilibili.com/video/BVxxx",
  "date": "2026-07-28"
}
```

| 触发 | 如何取 url |
|------|-----------|
| **Webhook** | payload 的 `url`；`date` 可选 |
| **GitHub Issue** | Issue 标题或正文中的第一个 B 站 / 小红书链接；`date` 用当天 |
| **定时 cron** | 读取 `docs/pending-urls.txt` 第一行非空 URL；处理后从文件删除该行；无待处理则结束 |

| 字段 | 必填 | 说明 |
|------|------|------|
| `url` | 是 | B 站（bilibili.com / b23.tv）或小红书（xiaohongshu.com / xhslink.com） |
| `date` | 否 | 前端展示日期 `YYYY-MM-DD`；未提供用当天 |

若 url 缺失或不是上述站点，记录错误并结束。

每个 URL 只处理一次（检查 `docs/index.json` 是否已有相同 `url`）。

---

## Step 1：解析入口

按上表从触发源提取 `url` / `date`。若 cron 队列为空，输出「无待处理 URL」并正常结束（不算失败）。

---

## Step 2：yt-dlp 下载音频

```bash
cd ~/Projects/language_paraphrase
yt-dlp -f "bestaudio[ext=m4a]/bestaudio/best" -o "{slug}.%(ext)s" "{url}"
```

- `{slug}`：从标题提取英文/拼音关键词，≤30 字符，不含空格和特殊字符
- 示例：`cafe-order-chat`、`xiaohongshu-airport-vlog`
- 失败最多重试 3 次

同时用 `yt-dlp --print title --print duration_string` 提取标题与时长。

小红书若需 cookies，优先使用本机已配置的 `yt-dlp` cookies 方案；仍失败则写入 `index.json` 失败项并结束。

---

## Step 3：安装依赖

仅首次：

```bash
which ffmpeg || brew install ffmpeg
python3 -c "import whisper" 2>/dev/null || pip3 install --user openai-whisper
export PATH="$PATH:/Users/chenzhiheng/Library/Python/3.9/bin:/opt/homebrew/bin"
```

---

## Step 4：Whisper 转录

```bash
export PATH="$PATH:/Users/chenzhiheng/Library/Python/3.9/bin:/opt/homebrew/bin"
cd ~/Projects/language_paraphrase
whisper {slug}.m4a --model small --language Chinese --output_dir .
```

必须保留带时间戳产物（至少 `{slug}.srt` / `{slug}.json`），后续场景切分依赖时间轴。

语言：视频以中文为主时用 `--language Chinese`；明显英文口播可用 `English` 或自动检测。

---

## Step 5：场景切分 + 逐句英译（核心）

读取转录稿（优先 `.json` 段落时间戳，其次 `.srt`），按以下规则处理。

### 5.1 识别并切分场景

将内容切成 **4–12 个关键场景**（过碎合并、过长再拆）：

- 地点/活动切换（进店、点餐、结账、登机、面试开场…）
- 对话轮次主题变化
- 旁白段落的叙事节点

每个场景必须有：

| 字段 | 说明 |
|------|------|
| `scene_id` | S1, S2… |
| `time_range` | 如 `00:12–00:48` |
| `scene_title` | 中英短标题，如「点单｜Ordering」 |
| `context` | 1–2 句情景说明（谁在哪、要完成什么） |

### 5.2 逐句中英对照

场景内按句（或自然意群）列出：

1. **中文原文**（尽量贴近转录，可轻微润色口误）
2. **英文翻译**（地道口语优先，不是逐字直译）
3. **表达批注**（可选）：语域（casual/polite）、语气、易错点

### 5.3 Paraphrase（学习重点）

每个关键场景至少提供 **2–4 组可替换说法**：

- 同一意图的 2–3 种英文说法（正式 / 日常 / 更短）
- 标注「什么场合用哪个」
- 抽出 3–8 个 **chunk**（如 `I'd like to…` / `Could I get…`）

### 5.4 必须包含的学习模块

1. **场景地图**：全文场景一览（时间轴）
2. **关键场景详解**：对照 + paraphrase
3. **今日可练**：3–5 个口头替换练习（给中文意图，写出/说出英文）
4. **避坑**：直译腔、中式英语、礼貌层级用错
5. **认知转变**：以前只会说 X，现在场景里可以说 Y/Z

**不要**做成普通「视频内容总结」；主目标是**学场景式英文表达**。

---

## Step 6：生成 SVG

在仓库根目录创建 `generate-{slug}.mjs`，**必须**使用 `svg-auto-height.mjs` 的 `buildSvg`。

### 脚本模板

```javascript
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { buildSvg } from './svg-auto-height.mjs';

const DIR = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(DIR, 'docs', '{slug}-场景英译.svg');

const CSS = `/* 见下方完整 CSS */`;
const body = `<!-- 见下方 body 区模板 -->`;

const { svg, height } = await buildSvg({ css: CSS, body, width: 1320 });
fs.writeFileSync(OUT, svg, 'utf8');
console.log('Generated:', OUT, 'height:', height, 'px');
```

### body 区模板

```html
<div class="container">

<h1>{视频标题}</h1>
<div class="meta">
  <span class="tag tag-blue">{B站|小红书}</span>
  <span class="tag tag-green">场景英译</span>
  <span class="tag tag-orange">{时长}</span>
  <span class="tag tag-purple">{场景数} scenes</span>
</div>
<div class="summary-line">{一句话：学到哪类情景表达}</div>

<div class="timeline">
  <h3>场景地图</h3>
  <div class="timeline-item">
    <span class="timeline-time">00:12</span>
    <span class="timeline-text">S1 点单｜Ordering</span>
  </div>
</div>

<div class="section">
  <h2 class="sec-title">S1 点单｜Ordering <span class="tag tag-gray">00:12–00:48</span></h2>
  <div class="card">
    <p class="context">情景：在咖啡店柜台点饮品</p>
    <table>
      <tr><th>中文</th><th>English</th></tr>
      <tr><td>你好，我想要一杯拿铁</td><td>Hi, I'd like a latte, please.</td></tr>
    </table>
    <div class="highlight">
      <strong>Paraphrase</strong>
      <ul>
        <li>Could I get a latte?</li>
        <li>Can I have a latte, please?</li>
      </ul>
    </div>
    <div class="action">Chunks：I'd like… / Could I get… / for here or to go</div>
  </div>
</div>

<div class="conclusion">
  <h2>今日可练 & 认知转变</h2>
  <h3>口头练习</h3>
  <ol>...</ol>
  <h3>避坑</h3>
  <ul>...</ul>
  <h3>认知转变</h3>
  <p>以前只会说…… 现在在这个场景可以说……</p>
</div>

</div>
```

### 完整 CSS（必须使用）

```css
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"PingFang SC","Microsoft YaHei",sans-serif;background:linear-gradient(135deg,#f8fafc,#e2e8f0);padding:48px 60px;color:#1e293b}
.container{max-width:1200px;margin:0 auto}
h1{font-size:36px;font-weight:900;background:linear-gradient(135deg,#0f766e,#14b8a6);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:8px}
h2{font-size:26px;font-weight:700;color:#0f766e;margin:32px 0 16px;padding-bottom:8px;border-bottom:2px solid #e2e8f0}
h3{font-size:20px;font-weight:700;color:#334155;margin-bottom:12px}
p{font-size:16px;line-height:1.8;color:#475569;margin-bottom:10px}
ul,ol{padding-left:24px;margin:8px 0}
li{font-size:15px;line-height:1.8;color:#475569;margin-bottom:6px}
.tag{display:inline-block;padding:4px 14px;border-radius:20px;font-size:13px;font-weight:600;margin-right:8px}
.tag-blue{background:#dbeafe;color:#1e40af}
.tag-green{background:#d1fae5;color:#065f46}
.tag-orange{background:#ffedd5;color:#9a3412}
.tag-purple{background:#ede9fe;color:#6b21a8}
.tag-red{background:#fee2e2;color:#991b1b}
.tag-gray{background:#f1f5f9;color:#64748b}
.meta{margin:12px 0 20px}
.summary-line{font-size:18px;line-height:1.7;color:#334155;padding:20px 24px;background:#fff;border-radius:12px;border-left:4px solid #14b8a6;margin-bottom:20px;box-shadow:0 2px 12px rgba(0,0,0,0.04)}
.timeline{background:#fff;border-radius:16px;padding:24px 28px;margin-bottom:24px;box-shadow:0 2px 12px rgba(0,0,0,0.04)}
.timeline h3{color:#0f766e;margin-bottom:12px}
.timeline-item{display:flex;align-items:baseline;padding:8px 0;border-bottom:1px solid #f1f5f9}
.timeline-time{font-size:14px;font-weight:700;color:#0d9488;min-width:70px;font-variant-numeric:tabular-nums}
.timeline-text{font-size:15px;color:#475569}
.section{margin-bottom:32px}
.sec-title{font-size:22px;font-weight:700;color:#0f766e;margin-bottom:16px;padding-left:16px;border-left:4px solid #14b8a6}
.card{background:#fff;border-radius:16px;padding:32px;margin-bottom:20px;box-shadow:0 4px 24px rgba(0,0,0,0.06);border-left:5px solid #14b8a6}
.card .context{font-size:15px;color:#64748b;margin-bottom:16px;padding:12px 16px;background:#f0fdfa;border-radius:10px}
.card .highlight{background:#fef3c7;padding:12px 16px;border-radius:10px;margin:12px 0;font-size:15px;color:#92400e;border-left:4px solid #f59e0b}
.card .action{background:#ecfdf5;padding:12px 16px;border-radius:10px;margin:12px 0;font-size:15px;color:#065f46;border-left:4px solid #10b981}
table{width:100%;border-collapse:collapse;margin:16px 0;font-size:15px}
th{background:#f0fdfa;padding:12px 16px;text-align:left;font-weight:700;color:#0f766e;border-bottom:2px solid #99f6e4}
td{padding:12px 16px;border-bottom:1px solid #e2e8f0;color:#475569;vertical-align:top}
tr:nth-child(even) td{background:#fafbfc}
.conclusion{background:linear-gradient(135deg,#0f766e,#14b8a6);color:#fff;border-radius:20px;padding:36px;margin-top:32px}
.conclusion h2{font-size:26px;font-weight:800;margin-top:0;margin-bottom:16px;padding-bottom:8px;border-bottom:1px solid rgba(255,255,255,0.2);color:#fff}
.conclusion h3{font-size:18px;font-weight:700;color:rgba(255,255,255,0.9);margin:20px 0 10px}
.conclusion p,.conclusion li{color:rgba(255,255,255,0.9);font-size:15px}
```

### 运行

```bash
node generate-{slug}.mjs
```

优先 Node：`/Applications/Cursor.app/Contents/Resources/app/resources/helpers/node`。

### XML 避坑

- HTML 注释禁止连续 `--`
- 裸 `<` 转义为 `&lt;`
- `buildSvg` 已修复 `&` 与 `<br/>`

---

## Step 7：质量自检

- [ ] 场景数在 4–12，且有时间范围
- [ ] 每个关键场景有中英对照表
- [ ] 每个关键场景有 paraphrase（≥2 种说法）
- [ ] 有 chunks / 今日可练 / 避坑
- [ ] 不是「内容总结文」，而是「可开口练的情景英语」
- [ ] SVG 高度正常、XML 无错配标签

---

## Step 8：更新 index.json

将新条目追加到 `docs/index.json` 数组开头：

```json
{
  "date": "YYYY-MM-DD",
  "filename": "slug-场景英译.svg",
  "title": "视频标题",
  "summary": "一句话：学到的情景类型与核心表达，≤120字",
  "tags": ["点餐", "口语", "小红书"],
  "url": "https://...",
  "duration": "3分20秒",
  "scenes": 6,
  "platform": "bilibili",
  "svg_height": 9560
}
```

`platform`：`bilibili` 或 `xiaohongshu`。失败项加 `"error": true` 与 `error_message`。

---

## Step 9：Git 提交与推送到 main（**必须**）

> GitHub Pages 从 `main` 的 `docs/` 部署。

```bash
git add docs/
git commit -m "lang: scene English from {视频标题}"
git checkout main
git pull origin main
git push -u origin main
```

最终变更必须在 `origin/main`。冲突则 `git pull --rebase origin main` 再 push。

---

## Step 10：清理

```bash
rm generate-{slug}.mjs
# 可选：rm {slug}.m4a
```

若来自 cron 队列，从 `docs/pending-urls.txt` 删除已处理 URL；文件空则保留空文件或删除均可。

---

## 产出清单

| 文件 | 说明 |
|------|------|
| `{slug}.m4a` | 原始音频 |
| `{slug}.txt` / `.srt` / `.json` | 转录 |
| `docs/{slug}-场景英译.svg` | 场景英译长图 |

---

## 约束

- 仅处理 B 站 / 小红书链接
- 不修改非 `docs/` 文件（`generate-{slug}.mjs` 除外，用完删除）
- 不修改 `.gitignore`
- 同 URL 不重复处理
- 严禁 `rsvg-convert` / Inkscape
- **必须 push 到 main**，否则 Pages 不更新
- 主目标是情景英语，不是视频内容摘要
