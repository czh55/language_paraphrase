# 场景英译工作流（WORKFLOW）

主目标：**情景英语表达学习**（场景英译 + paraphrase），不是内容总结。

## 入口

统一得到 `{"url":"...","date":"YYYY-MM-DD"}`：

1. **Webhook**：`payload.url`；`date` 可选  
2. **GitHub Issue**：标题或正文中第一个 B 站/小红书链接；`date` 用当天  
3. **定时 cron**：读 `docs/pending-urls.txt` 第一行非空 URL；处理后删除该行；无待处理则正常结束

仅处理：`bilibili.com` / `b23.tv` / `xiaohongshu.com` / `xhslink.com`（含 `xhslink.cn` 短链，解析到小红书后继续）。  
同 `url` 已在 `docs/index.json` 则跳过。

## 步骤（不可跳过/合并）

1. 解析入口 → url + date；生成 `slug`（建议 `YYYY-MM-DD-短名`）  
2. `yt-dlp -f "bestaudio[ext=m4a]/bestaudio/best" -o "{slug}.%(ext)s" "{url}"`（可 `--extract-audio --audio-format m4a`）  
3. 安装依赖（仅首次）：`ffmpeg` + `openai-whisper`  
4. `whisper {slug}.m4a --model small --language Chinese --output_dir .`  
5. 切 4–12 个关键场景；逐句中文｜地道英文｜可选语域批注；每场景 2–4 组 paraphrase + chunks；必须含：**场景地图、今日可练、避坑、认知转变**  
6. 写 `generate-{slug}.mjs`，用根目录 `./svg-auto-height.mjs` 的 `buildSvg`，输出 `docs/{slug}-场景英译.svg`（**青绿主题**）  
7. 质量自检（见下）  
8. 更新 `docs/index.json`（含 `platform` / `scenes` / `svg_height`）  
9. `git add docs/`（及必要脚手架）→ commit → **`git push origin main`（必须，Pages 才能展示）**  
10. 删除 `generate-*.mjs` 与临时音视频/转录文件；若来自队列则更新 `pending-urls.txt`

## SVG 约束

- 使用 `svg-auto-height.mjs` 计算高度；**禁止** `rsvg-convert` / Inkscape  
- 主题色：`#0d7377` / `#14919b` 青绿  
- 不改 `.gitignore`

## 质量自检清单

- [ ] 场景数 4–12  
- [ ] 含场景地图 / 今日可练 / 避坑 / 认知转变  
- [ ] 逐句有中英对照；ASR 专有名词已按语境校正  
- [ ] SVG 可打开，`viewBox` 高度与 `index.json.svg_height` 一致  
- [ ] `index.json` 含 platform、scenes、svg、url、date  
- [ ] 已推送到 `main`
