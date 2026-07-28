# language_paraphrase

B 站 / 小红书视频 → Whisper 转录 → 场景切分 → 逐句英译 → SVG 长图 → GitHub Pages。

面向**场景式英文表达**学习：按真实情景拆分对话/旁白，给出中英对照、可替换说法（paraphrase）与练习提示。

## 结构

```
language_paraphrase/
├── svg-auto-height.mjs   # SVG 自动测高
├── docs/
│   ├── WORKFLOW.md       # Automation 执行规范（权威）
│   ├── TRIGGER-PROMPT.md # 三种触发方式说明
│   ├── index.html        # GitHub Pages 首页
│   ├── index.json        # 条目索引
│   └── *-场景英译.svg    # 产出长图
└── .gitignore
```

## 三种触发

| 方式 | 说明 |
|------|------|
| **Webhook** | `POST` 视频链接（主路径） |
| **GitHub Issue** | 新建 Issue，标题或正文含视频 URL |
| **定时 cron** | 处理 `docs/pending-urls.txt` 队列（有则处理 1 条） |

详见 `docs/TRIGGER-PROMPT.md` 与 `docs/WORKFLOW.md`。

## Webhook 示例

```bash
curl -X POST "<webhook-url>" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"url":"https://www.bilibili.com/video/BVxxx","date":"2026-07-28"}'
```

小红书同样传 `url` 字段，例如 `https://www.xiaohongshu.com/explore/...`。

## 依赖

- `yt-dlp`
- `ffmpeg`
- `openai-whisper`
- Node.js（运行 `generate-*.mjs`）

## GitHub Pages

Settings → Pages → Source：`main` 分支，`/docs` 目录。
