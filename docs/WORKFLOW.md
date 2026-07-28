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
6. 生成响应式 `docs/{slug}-场景英译.html`（**青绿主题**）：逐句中英对照自然换行；每句英文有朗读按钮；每个场景有整体朗读按钮；英文长词和专业难词可点击单独发音  
7. 质量自检（见下）  
8. 更新 `docs/index.json`（含 `platform` / `scenes` / `sentences` / `html` / `speech`）  
9. `git add docs/`（及必要脚手架）→ commit → **`git push origin main`（必须，Pages 才能展示）**  
10. 删除临时音视频/转录文件；若来自队列则更新 `pending-urls.txt`

## HTML 页面约束

- 使用语义化 HTML + 响应式 CSS，不使用固定宽高画布，避免文字遮挡和大面积空白  
- 桌面端充分利用宽度；窄屏自动改为单栏；长文本必须可换行  
- 使用浏览器 Web Speech API（`speechSynthesis`）朗读英文，提供速度选择、停止按钮和不支持时的提示  
- 每句英文必须有独立朗读按钮；每个场景必须有整段朗读按钮  
- 英文中 8 个及以上字母的长词，以及词表中的摄影/技术难词，必须显示为可点击发音；支持鼠标、触屏和键盘操作  
- 主题色：`#0d7377` / `#14919b` 青绿
- 不改 `.gitignore`

## 质量自检清单

- [ ] 场景数 4–12  
- [ ] 含场景地图 / 今日可练 / 避坑 / 认知转变  
- [ ] 逐句有中英对照；ASR 专有名词已按语境校正  
- [ ] 每句英文与每个场景均有朗读按钮，朗读文本非空  
- [ ] 长词/难词可点击且只朗读该词，具备可访问名称与键盘焦点样式  
- [ ] HTML 在桌面和移动宽度下无横向溢出、重叠或大面积无效空白  
- [ ] `index.json` 含 platform、scenes、sentences、html、speech、url、date  
- [ ] 已推送到 `main`
