# 场景英译 · 三种触发说明

Automation 名称建议：`Language Paraphrase 场景英译`。  
完整执行逻辑以 `docs/WORKFLOW.md` 为准（编辑器 prompt 可只写一行：读取并严格执行该文件）。

---

## 触发 A：Webhook（主路径）

保存 Automation 后，把下方 `{webhook-url}` / `{token}` 换成控制台生成的值（本机私有版见 `TRIGGER.local.md`，勿 push）。

```bash
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
curl -sS -w "\nHTTP_CODE:%{http_code}\n" -X POST \
  "{webhook-url}" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {token}" \
  -d '{"url":"{视频链接}","date":"{YYYY-MM-DD}"}'
```

支持：
- `https://www.bilibili.com/video/BVxxx` / `https://b23.tv/...`
- `https://www.xiaohongshu.com/explore/...` / `https://xhslink.com/...`

成功：`{"success":true,"backgroundComposerId":"bc-..."}`

---

## 触发 B：GitHub Issue

在仓库 `czh55/language_paraphrase` 新建 Issue：

- 标题或正文里放**一个**视频链接即可
- Automation（Git 事件：Issue opened）会抽取链接并走同一套 WORKFLOW

示例标题：`场景英译 https://www.bilibili.com/video/BVxxx`

---

## 触发 C：定时 cron + 队列文件

1. 把待处理链接（每行一个）写入 `docs/pending-urls.txt` 并 push 到 `main`
2. 每日定时（默认 `0 8 * * *`）Automation 读取**第一行**非空 URL 处理
3. 处理成功后从该文件删除对应行并提交

适合：先囤一批链接，早上自动消化一条。

```text
https://www.bilibili.com/video/BVxxx
https://www.xiaohongshu.com/explore/xxxx
```

---

## 可粘贴 Prompt（Webhook）

```text
请帮我触发 Cursor Automation「Language Paraphrase 场景英译」。

1. 先 unset 代理，再 POST：
   URL: {webhook-url}
   Header: Content-Type: application/json
   Authorization: Bearer {token}
   Body: {"url":"{视频链接}","date":"{YYYY-MM-DD}"}

2. 解读响应：success → 报告 backgroundComposerId；disabled → 提醒打开开关；401 → Token 失效。

3. 只触发 Webhook，不要本地下载/转录。

本次链接：{视频链接}
日期：{YYYY-MM-DD}
```

---

## Payload

| 字段 | 必填 | 说明 |
|------|------|------|
| `url` | 是 | B 站或小红书链接 |
| `date` | 否 | 展示日期 YYYY-MM-DD |
