# 视频场景 → 逐句英译 自动化工作流

当 Cursor Automation 被触发（Webhook / GitHub Issue / 定时队列）后，严格按本文档逐步骤执行。**不要跳过或合并任何步骤。**

```
Task Progress:
- [ ] 1. 解析入口，得到视频 url（与可选 date）
- [ ] 2. yt-dlp 下载音频（m4a）+ 封面缩略图 + 视频画面流
- [ ] 3. 安装依赖（ffmpeg + openai-whisper，仅首次）
- [ ] 4. Whisper 转录（带时间戳，--model small）
- [ ] 5. 识别切分关键场景 + 逐句英译 + paraphrase
- [ ] 5.5 生成音频（edge-tts，generate_audio.py）
- [ ] 5.6 场景截图抽帧（extract_frames.py，从场景时间轴抽关键帧）
- [ ] 6. 生成 HTML（Node .mjs，含 Hero 封面 + 场景截图）
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

## Step 2：yt-dlp 下载音频 + 封面 + 画面流

### 2.1 下载音频（用于 Whisper 转录）

```bash
cd ~/Projects/language_paraphrase
yt-dlp -f "bestaudio[ext=m4a]/bestaudio/best" -o "{slug}.%(ext)s" "{url}"
```

- `{slug}`：从标题提取英文/拼音关键词，≤30 字符，不含空格和特殊字符
- 示例：`cafe-order-chat`、`xiaohongshu-airport-vlog`
- 失败最多重试 3 次

同时用 `yt-dlp --print title --print duration_string` 提取标题与时长。

### 2.2 下载封面缩略图（用于 Hero 区 hero.jpg）

```bash
yt-dlp --skip-download --write-thumbnail -o "{slug}-thumb.%(ext)s" "{url}"
```

- 封面独立于视频流，几乎必成功
- 保留产物路径，Step 5.6 会转成 `docs/images/{slug}/hero.jpg`

### 2.3 下载视频画面流（用于场景截图抽帧）

```bash
# B 站：下载低画质 mp4 画面流（仅供抽帧，越小越好）
yt-dlp -f "bv[ext=mp4][height<=480]/bv[ext=mp4]/bv/b" -o "{slug}-video.%(ext)s" "{url}"
```

- 画面流仅用于抽帧，抽完即删（见 Step 10）
- 小红书若画面流失败（下载受限）：**降级策略**——场景图统一复用 `hero.jpg`，在 `index.json` 增加 `"frames_fallback": true` 字段
- 若画面流与音频同一 URL，2.1 与 2.3 的下载可合并执行

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
| `context` | 1–2 句情景说明（谁在哪、要完成什么）+ 语域标注（casual/formal/评测口播等） |

### 5.2 逐句双层对照（表达提示必填）

场景内按句（或自然意群）列出。**每句必须有 3 项**：

1. **中文原文**（贴近转录，可轻微润色口误，ASR 错误必须先行矫正，见 5.5）
2. **英文翻译**（地道口语优先，不是逐字直译）
3. **表达提示**（`<p class="note">` 格式，**必填**）：标注关键词翻译对照和语境说明
   - 格式：`<span>表达提示</span>画质旗舰 → resolution flagship（比 image-quality king 更贴科技评测）`
   - 每句至少 1 条提示，关键句可 2-3 条

### 5.3 Paraphrase（学习重点）

每个关键场景至少提供 **2–4 组可替换说法**，使用 `<details class="paraphrase">` 可折叠结构：

- `<summary>Paraphrase &amp; Chunks <span>N 组表达</span></summary>`
- 每组格式：`<li><p>中文意图 → 英文替换说法</p><div class="chunks">chunk · chunk · chunk</div></li>`
- 同一意图的 2–3 种英文说法（正式 / 日常 / 更短）
- 标注「什么场合用哪个」
- 抽出 3–8 个 **chunk**（如 `I'd like to…` / `Could I get…`）

### 5.4 必须包含的学习模块

1. **场景地图**：全文场景一览（时间轴），每个场景有编号、时间、中英标题
2. **关键场景详解**：逐句对照 + 表达提示 + 可折叠 paraphrase
3. **今日可练**：4 个口头替换练习（给中文意图 + 英文例句）
4. **避坑**：4 个直译腔/中式英语对照（✕ 错误 → ✓ 正确 + 解释）
5. **认知转变**：3 个思维转变（以前思维 → 新思维，箭头分隔）

**不要**做成普通「视频内容总结」；主目标是**学场景式英文表达**。

### 5.5 转录纠错（必做）

Whisper 转录中文内容时常有同音字错误，**必须在生成翻译前人工校对修正**：

- 常见错误类型：同音错字（大本中→大本钟、果将→果酱、沈頓→伦敦、壁路→秘鲁、指条→纸条）
- 中文原文使用修正后的版本
- 英文翻译以修正后的中文语义为准
- 在 HTML 页脚标注「ASR 专有名词已按语境校正」

### 5.6 场景级语音文本（必做）

每个场景需要合成一段**完整的英文口播文本**（拼接该场景所有英文句），填入场景卡片的 `data-speak` 属性，用于「朗读整个场景」按钮。文本要求：

- 自然连读：同一说话人的相邻句子用句号或分号连接，避免生硬断开
- 专有名词发音：数字、型号、品牌名写全（61 → sixty-one，F1.4 → F one point four）
- 完整段落：形成一段可以通读的短文

---

## Step 5.5：生成音频（edge-tts 神经网络语音）

在生成 HTML 之前，使用 Python 脚本调用 edge-tts（微软免费神经网络语音）生成高质量 MP3 音频。

### 安装依赖

```bash
pip3 install --break-system-packages edge-tts
```

系统需要 `ffmpeg`（用于合并超长段落音频）。

### 运行脚本

```bash
python3 scripts/generate_audio.py --slug={slug}
```

### 产出文件

| 音频类型 | 语音 | 文件 | 用途 |
|---------|------|------|------|
| 中文讲解旁白 | zh-CN-XiaoxiaoNeural | `docs/audio/{slug}/narration.mp3` | Hero 区域中文语音讲解播放器（2-5 分钟） |
| 场景英文朗读 | en-US-JennyNeural | `docs/audio/{slug}/s{N}.mp3` | 每个场景「朗读整个场景」按钮 |
| 逐句英文朗读 | 同上 | `docs/audio/{slug}/s{N}-{idx:02d}.mp3` | 每个句子「朗读本句」按钮 |
| 练习句朗读 | 同上 | `docs/audio/{slug}/practice-{idx}.mp3` | 今日可练区域「朗读练习句」按钮 |
| 音频清单 | — | `docs/audio/{slug}/manifest.json` | 所有音频文件的索引 |

### 脚本核心逻辑

`scripts/generate_audio.py` 参考 `daily-lyric-learning/scripts/generate_audio.py`：

- `build_narration_script(meta, scenes)` — 组装中文旁白稿（开场白 + 逐场景讲解 + 可练导语 + 结语）
- `synthesize_speech(text, output_path, voice)` — 调用 edge-tts 生成 MP3，超长段落自动分块后用 ffmpeg 合并
- `generate_scene_mp3` / `generate_sentence_mp3` / `generate_practice_mp3` — 分别生成三类英文音频
- `generate_narration` — 生成中文旁白 MP3 + 旁白稿 txt

---

## Step 5.6：场景截图抽帧（关键帧图片）

在生成 HTML 之前，使用 `scripts/extract_frames.py` 按场景时间轴从视频画面流抽取关键帧，作为每个场景卡片的配图。

### 运行

```bash
python3 scripts/extract_frames.py --slug={slug} --video={slug}-video.mp4 --thumb={slug}-thumb.jpg
```

### 产出文件

| 文件 | 说明 |
|------|------|
| `docs/images/{slug}/hero.jpg` | 视频封面（由封面缩略图转换而来），用于 Hero 区 |
| `docs/images/{slug}/s1.jpg` ~ `s{N}.jpg` | 各场景时间轴中点的关键帧（720p 宽 jpg），用于场景卡片 |

### 脚本核心逻辑

`scripts/extract_frames.py` 参考 `scripts/generate_audio.py` 的结构：

- **时间轴来源**（按优先级）：`docs/audio/{slug}/audio-input.json` 的 `scenes[].time` → 不存在则解析 `docs/{slug}-场景英译.html` 中 `<span class="time">` 文本
- **抽帧时机**：每个场景取时间区间中点 `(start+end)//2`，用 `ffmpeg -ss {sec} -i {video} -frames:v 1` 抽取
- `--print-scenes` 模式可仅预览解析出的场景时间轴，便于校验
- 输出缺帧场景清单，失败则 Step 7 自检会拦截

### 降级

- 画面流不可用（如小红书）：不运行本步骤，场景卡片复用 `hero.jpg`，`index.json` 记 `"frames_fallback": true`
- 抽帧为黑帧/广告帧：时间中点可避免首帧广告；个别场景异常可人工换时间点重抽

---

## Step 6：生成 HTML（交互式场景英译学习卡）

在仓库根目录创建 `generate-{slug}.mjs`，**直接生成完整的 HTML 文件**（不再依赖 `svg-auto-height.mjs`）。

### 脚本模板

```javascript
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const DIR = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(DIR, 'docs', '{slug}-场景英译.html');

// CSS（从下方完整 CSS 模板复制，不变）
const CSS = `{完整 CSS 模板}`;

// body 按下方 HTML 结构模板填充
const HTML = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="description" content="{视频标题}视频场景英译学习卡" />
  <title>{视频标题}｜场景英译</title>
  <style>${CSS}</style>
</head>
<body>
  {...填充下方 HTML 结构模板...}
  <script>{填充下方 JS 脚本模板}</script>
</body>
</html>`;

fs.writeFileSync(OUT, HTML, 'utf8');
console.log('Generated:', OUT);
```

### HTML 必须包含的 8 个固定区域

#### (a) Hero 头部区域

```html
<header class="hero">
  <div class="hero-inner">
    <div class="hero-flex">
      <img class="hero-cover" src="images/{slug}/hero.jpg" alt="{视频标题} 封面" loading="lazy">
      <div class="hero-text">
        <p class="eyebrow">Scene English · {视频主题分类，如"伦敦旅行Vlog"}</p>
        <h1>{视频标题}</h1>
        <p class="hero-en">{英文副标题}</p>
        <div class="hero-meta">
          <span class="chip">YYYY-MM-DD</span>
          <span class="chip">{B站|小红书}</span>
          <span class="chip">{时长}</span>
          <span class="chip">{N} 个场景</span>
          <span class="chip">点下划线单词听发音</span>
          <a class="source-link" href="{原视频链接}" target="_blank" rel="noopener">查看原视频 ↗</a>
        </div>
      </div>
    </div>
    <div class="toolbar">
      <label for="speech-rate">朗读速度</label>
      <select id="speech-rate">
        <option value="0.85">慢速 0.85×</option>
        <option value="1" selected>正常 1×</option>
        <option value="1.15">快速 1.15×</option>
      </select>
      <button id="stop-speech" class="stop-btn" type="button">■ 停止朗读</button>
      <span id="speech-status" class="speech-status" role="status" aria-live="polite"></span>
    </div>
    <div class="narration-player">
      <p class="audio-label">🎧 语音讲解</p>
      <!-- 禁止使用 <audio> 元素：静态 audio 在部分托管环境会触发整文件预加载，
           导致页面加载卡死。统一使用 data-audio 按钮，通过 JS new Audio() 按需加载 -->
      <button class="speak-btn" type="button"
        data-audio="audio/{slug}/narration.mp3" aria-label="播放语音讲解">
        <span aria-hidden="true">▶</span><span>播放语音讲解</span>
      </button>
    </div>
  </div>
</header>
```

#### (b) 侧边栏场景地图

```html
<main class="page">
  <aside class="sidebar" aria-label="场景地图">
    <div class="sidebar-box">
      <h2>场景地图 · SCENE MAP</h2>
      <nav class="map-nav">
        <a class="map-link" href="#s1">
          <span class="map-id">S1</span>
          <span><b>{中文场景标题}</b><small>00:00–00:31 · {English Scene Title}</small></span>
        </a>
        <!-- 每个场景一个 link -->
      </nav>
    </div>
  </aside>
  <div class="content">
```

#### (c) 场景卡片

```html
    <section class="scene-card" id="s1" data-scene>
      <div class="scene-topline">
        <div><span class="scene-id">S1</span><span class="time">00:00–00:31</span></div>
        <button class="speak-btn scene-speak" type="button"
          data-audio="audio/{slug}/s1.mp3"
          aria-label="朗读整个场景">
          <span aria-hidden="true">▶</span><span>朗读整个场景</span>
        </button>
      </div>
      <img class="scene-frame" src="images/{slug}/s1.jpg" alt="{中文场景标题} 场景截图" loading="lazy">
      <h2>{中文场景标题}</h2>
      <p class="scene-title-en">{English Scene Title}</p>
      <p class="context"><b>情境</b>{情景说明}。语域：{casual/formal/评测口播等}</p>
      <div class="sentence-list">
        <article class="sentence">
          <div class="sentence-no">01</div>
          <div class="bilingual">
            <div class="lang-block zh-block">
              <span class="lang-tag">中文</span>
              <p>{中文原文（ASR 已校正）}</p>
            </div>
            <div class="lang-block en-block">
              <div class="en-head">
                <span class="lang-tag">EN</span>
                <button class="speak-btn compact" type="button"
                  data-audio="audio/{slug}/s1-01.mp3"
                  aria-label="朗读本句">
                  <span aria-hidden="true">▶</span><span>朗读本句</span>
                </button>
              </div>
              <p class="english">{该句英文翻译}</p>
            </div>
          </div>
          <p class="note"><span>表达提示</span>{关键词 → 英文对照（语境说明）}</p>
        </article>
        <!-- 每句一个 article.sentence -->
      </div>
      <details class="paraphrase">
        <summary>Paraphrase &amp; Chunks <span>N 组表达</span></summary>
        <ol>
          <li>
            <p>{中文意图 → 英文替换说法}</p>
            <div class="chunks">chunk · chunk · chunk</div>
          </li>
          <!-- 2-4 组 -->
        </ol>
      </details>
    </section>
    <!-- 每个场景一个 section.scene-card -->
```

#### (d) 今日可练

```html
    <section class="study-section" id="practice">
      <h2 class="section-heading">今日可练 <small>PRACTICE TODAY</small></h2>
      <div class="study-grid">
        <article>
          <p>{中文练习意图}</p>
          <div class="practice-en">
            {英文例句}
            <button class="speak-btn icon-only" type="button"
              data-audio="audio/{slug}/practice-0.mp3" aria-label="朗读练习句">
              <span aria-hidden="true">▶</span><span>朗读练习句</span>
            </button>
          </div>
        </article>
        <!-- 共 4 个 article，2x2 grid -->
      </div>
    </section>
```

#### (e) 避坑

```html
    <section class="study-section pitfalls" id="pitfalls">
      <h2 class="section-heading">避坑 <small>PITFALLS</small></h2>
      <div class="study-grid">
        <article>
          <div class="wrong">✕ {错误说法（直译腔/中式英语）}</div>
          <div class="right">✓ {正确说法}</div>
          <p>{为什么错，怎么才对}</p>
        </article>
        <!-- 共 4 个 article -->
      </div>
    </section>
```

#### (f) 认知转变

```html
    <section class="study-section shifts" id="mindset">
      <h2 class="section-heading">认知转变 <small>MINDSET SHIFTS</small></h2>
      <div class="study-grid">
        <article>
          <span>{以前的思维/做法}</span>
          <b aria-hidden="true">→</b>
          <strong>{新的思维/做法}</strong>
        </article>
        <!-- 共 3 个 article，三列布局 -->
      </div>
    </section>
```

#### (g) 页脚

```html
    <footer>ASR 专有名词已按语境校正 · 场景/句子朗读使用 edge-tts 神经网络语音 · 单词发音使用浏览器 Web Speech API</footer>
  </div><!-- .content -->
</main><!-- .page -->
```

#### (h) JavaScript 语音朗读（必须包含完整脚本）

MP3 优先方案：场景/句子/练习朗读使用 edge-tts 生成的 MP3 音频，单词点击发音使用 Web Speech API fallback。

```javascript
(() => {
  let activeAudio = null;
  let activeBtn = null;
  const status = document.getElementById('speech-status');
  const stopBtn = document.getElementById('stop-speech');
  const rateSel = document.getElementById('speech-rate');

  // 停止当前播放
  const reset = () => {
    if (activeAudio) { activeAudio.pause(); activeAudio = null; }
    activeBtn?.classList.remove('playing');
    activeBtn = null;
    stopBtn.classList.remove('visible');
    status.textContent = '';
  };

  // === MP3 播放：场景/句子/练习朗读 ===
  const playAudio = (url, btn) => {
    reset();
    const audio = new Audio(url);
    audio.playbackRate = Number(rateSel.value);
    activeAudio = audio;
    activeBtn = btn;
    btn.classList.add('playing');
    stopBtn.classList.add('visible');
    status.textContent = btn.classList.contains('scene-speak')
      ? '正在朗读整个场景…'
      : '正在朗读…';

    audio.onended = () => {
      if (activeAudio === audio) reset();
    };
    audio.onerror = () => {
      status.textContent = '音频加载失败，请检查网络。';
      if (activeAudio === audio) reset();
    };
    audio.play().catch(() => {
      status.textContent = '播放失败，请检查浏览器音频设置。';
      if (activeAudio === audio) reset();
    });
  };

  document.addEventListener('click', e => {
    const btn = e.target.closest('[data-audio]');
    if (!btn) return;
    e.preventDefault();
    if (btn === activeBtn && activeAudio) {
      reset();
      return;
    }
    playAudio(btn.dataset.audio, btn);
  });

  stopBtn.addEventListener('click', reset);

  // === Web Speech API：单词发音 ===
  const synth = window.speechSynthesis;
  const getEnglishVoice = () => {
    const voices = synth.getVoices();
    return voices.find(v => /^en-(US|GB)/i.test(v.lang))
        || voices.find(v => /^en/i.test(v.lang)) || null;
  };

  // ★ 硬词表：根据视频主题定制，≥20 个
  const difficultWords = new Set([
    // 示例：'portrait', 'bokeh', 'aperture', ...
  ]);

  const shouldPronounce = word => {
    const n = word.toLowerCase().replace(/^[^a-z]+|[^a-z]+$/g, '');
    return n.replace(/[^a-z]/g, '').length >= 8 || difficultWords.has(n);
  };

  const markPronounceableWords = root => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(node => {
      if (node.parentElement?.closest('button, script, style')) return;
      const text = node.nodeValue;
      let m, last = 0, changed = false;
      const frag = document.createDocumentFragment();
      const re = /[A-Za-z]+(?:[-'\\u2019][A-Za-z]+)*/g;
      while ((m = re.exec(text))) {
        if (!shouldPronounce(m[0])) continue;
        changed = true;
        frag.append(text.slice(last, m.index));
        const wb = document.createElement('button');
        wb.type = 'button'; wb.className = 'pronounce-word';
        wb.dataset.speak = m[0];
        wb.setAttribute('aria-label', '\\u6717\\u8bfb\\u5355\\u8bcd ' + m[0]);
        wb.title = '\\u70b9\\u51fb\\u542c ' + m[0] + ' \\u53d1\\u97f3';
        wb.textContent = m[0];
        frag.append(wb);
        last = m.index + m[0].length;
      }
      if (!changed) return;
      frag.append(text.slice(last));
      node.replaceWith(frag);
    });
  };

  document.querySelectorAll(
    '.english, .scene-title-en, .paraphrase li p, .chunks, .practice-en, .wrong, .right'
  ).forEach(markPronounceableWords);

  document.addEventListener('click', e => {
    const wb = e.target.closest('.pronounce-word');
    if (!wb) return;
    e.preventDefault();
    if (!synth) return;
    synth.cancel();
    if (activeAudio) { activeAudio.pause(); activeAudio = null; }
    activeBtn?.classList.remove('playing');
    activeBtn = wb;
    wb.classList.add('playing');
    const u = new SpeechSynthesisUtterance(wb.dataset.speak);
    u.lang = 'en-US';
    u.rate = 0.88;
    const v = getEnglishVoice();
    if (v) u.voice = v;
    u.onend = () => { activeBtn?.classList.remove('playing'); activeBtn = null; };
    u.onerror = () => { activeBtn?.classList.remove('playing'); activeBtn = null; };
    synth.speak(u);
  });
})();
```

### 完整 CSS 模板（固定不变，直接复制使用）

```css
:root {
  --teal-950:#073f42; --teal-800:#0d686c; --teal-700:#0f7c80; --teal-600:#14919b;
  --mint-100:#dff4ec; --mint-50:#f0faf6; --ink:#183536; --muted:#607879;
  --line:#d7e8e2; --paper:#fff; --amber:#a85d08; --shadow:0 12px 32px rgba(7,63,66,.08);
}
* { box-sizing:border-box; }
html { scroll-behavior:smooth; scroll-padding-top:24px; }
body { margin:0; color:var(--ink); background:#edf7f2; font-family:Inter,"PingFang SC","Noto Sans SC","Microsoft YaHei",system-ui,sans-serif; line-height:1.65; }
button, select { font:inherit; }
a { color:inherit; }
.hero { color:#fff; background:radial-gradient(circle at 85% 10%,rgba(129,230,196,.24),transparent 30%),linear-gradient(125deg,#073f42,#0d7377 56%,#14919b); }
.hero-inner { width:min(1440px,100%); margin:auto; padding:48px clamp(20px,5vw,72px) 42px; }
.hero-flex { display:flex; gap:clamp(18px,3vw,40px); align-items:flex-start; }
.hero-cover { width:min(240px,42vw); aspect-ratio:16/10; object-fit:cover; border-radius:16px; border:1px solid rgba(255,255,255,.28); box-shadow:0 18px 44px rgba(0,0,0,.32); flex-shrink:0; }
.hero-text { min-width:0; flex:1; }
.eyebrow { margin:0 0 12px; font-size:.78rem; font-weight:800; letter-spacing:.14em; text-transform:uppercase; opacity:.8; }
h1 { max-width:1020px; margin:0; font-size:clamp(2rem,4.2vw,4rem); line-height:1.13; letter-spacing:-.04em; }
.hero-en { margin:12px 0 24px; font-size:clamp(1rem,2vw,1.3rem); opacity:.82; }
.hero-meta { display:flex; flex-wrap:wrap; gap:9px; align-items:center; }
.chip { border:1px solid rgba(255,255,255,.28); border-radius:99px; padding:5px 11px; font-size:.82rem; background:rgba(255,255,255,.08); }
.source-link { font-weight:750; text-decoration:none; border-bottom:1px solid rgba(255,255,255,.5); }
.toolbar { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-top:24px; }
.toolbar label { font-size:.82rem; opacity:.82; }
.toolbar select { color:#fff; background:#0a5d61; border:1px solid rgba(255,255,255,.3); border-radius:8px; padding:7px 9px; }
.stop-btn { display:none; color:#fff; background:#8c3b2a; border:0; border-radius:8px; padding:8px 12px; cursor:pointer; }
.stop-btn.visible { display:inline-flex; }
.speech-status { min-height:1.4em; font-size:.82rem; opacity:.88; }
.page { width:min(1440px,100%); margin:auto; padding:28px clamp(16px,3vw,44px) 64px; display:grid; grid-template-columns:minmax(230px,280px) minmax(0,1fr); gap:30px; align-items:start; }
.sidebar { position:sticky; top:20px; min-width:0; }
.sidebar-box { background:rgba(255,255,255,.8); border:1px solid var(--line); border-radius:16px; padding:17px; box-shadow:var(--shadow); backdrop-filter:blur(12px); }
.sidebar h2 { margin:0 0 13px; font-size:.9rem; letter-spacing:.08em; color:var(--teal-800); }
.map-link { display:grid; grid-template-columns:34px minmax(0,1fr); gap:9px; padding:10px 6px; text-decoration:none; border-top:1px solid var(--line); }
.map-link:hover b { color:var(--teal-700); }
.map-id { width:30px; height:30px; display:grid; place-items:center; border-radius:9px; color:#fff; background:var(--teal-700); font-size:.72rem; font-weight:800; }
.map-link b { display:block; font-size:.78rem; line-height:1.4; }
.map-link small { display:block; color:var(--muted); font-size:.67rem; line-height:1.4; margin-top:2px; overflow-wrap:anywhere; }
.content { min-width:0; }
.scene-card { background:var(--paper); border:1px solid var(--line); border-radius:20px; padding:clamp(20px,3vw,34px); margin-bottom:24px; box-shadow:var(--shadow); overflow:hidden; }
.scene-frame { display:block; width:100%; max-height:320px; object-fit:cover; border-radius:14px; margin:16px 0 4px; border:1px solid var(--line); box-shadow:0 10px 28px rgba(7,63,66,.1); }
.scene-topline { display:flex; justify-content:space-between; gap:16px; align-items:center; }
.scene-id { display:inline-grid; place-items:center; min-width:42px; height:30px; padding:0 10px; color:#fff; background:var(--teal-700); border-radius:8px; font-size:.78rem; font-weight:850; }
.time { margin-left:10px; color:var(--muted); font-size:.82rem; font-variant-numeric:tabular-nums; }
.scene-card h2 { margin:18px 0 2px; font-size:clamp(1.35rem,2.4vw,2rem); line-height:1.25; color:var(--teal-950); }
.scene-title-en { margin:0 0 18px; color:var(--teal-600); font-weight:700; font-size:.98rem; }
.context { margin:0 0 20px; padding:12px 15px; color:#496566; background:var(--mint-50); border-left:3px solid var(--teal-600); border-radius:0 10px 10px 0; font-size:.88rem; }
.context b { margin-right:10px; color:var(--teal-800); }
.sentence-list { display:grid; gap:12px; }
.sentence { position:relative; display:grid; grid-template-columns:38px minmax(0,1fr); gap:12px; padding:16px; border:1px solid #e2ece8; border-radius:14px; background:#fcfefd; min-width:0; }
.sentence-no { color:var(--teal-600); font-size:.76rem; font-weight:850; font-variant-numeric:tabular-nums; padding-top:4px; }
.bilingual { min-width:0; display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:clamp(14px,2vw,28px); }
.lang-block { min-width:0; }
.lang-block p { margin:5px 0 0; overflow-wrap:anywhere; }
.en-block { padding-left:clamp(14px,2vw,28px); border-left:1px solid var(--line); }
.en-block p { color:#0b5c60; font-weight:650; }
.lang-tag { display:inline-block; color:var(--muted); font-size:.66rem; font-weight:850; letter-spacing:.12em; }
.en-head { display:flex; justify-content:space-between; gap:10px; align-items:center; min-height:30px; }
.note { grid-column:2; margin:1px 0 0; color:#708182; font-size:.78rem; }
.note span { margin-right:7px; color:var(--amber); font-weight:750; }
.speak-btn { display:inline-flex; align-items:center; gap:7px; border:1px solid #b8d9d1; border-radius:9px; padding:7px 11px; color:var(--teal-800); background:#f5fbf8; cursor:pointer; white-space:nowrap; font-size:.78rem; font-weight:750; transition:.15s ease; }
.speak-btn:hover { color:#fff; background:var(--teal-700); border-color:var(--teal-700); transform:translateY(-1px); }
.speak-btn.playing { color:#fff; background:var(--teal-700); border-color:var(--teal-700); }
.speak-btn.compact { padding:4px 8px; font-size:.7rem; }
.speak-btn.icon-only { padding:3px 7px; margin-left:6px; }
.speak-btn.icon-only span:last-child { display:none; }
.pronounce-word { display:inline; margin:0; padding:0 2px; color:inherit; background:rgba(20,145,155,.08); border:0; border-bottom:1px dashed var(--teal-600); border-radius:3px; font:inherit; font-weight:inherit; line-height:inherit; cursor:pointer; }
.pronounce-word:hover, .pronounce-word:focus { color:var(--teal-950); background:#cceee4; border-bottom-style:solid; outline:3px solid rgba(20,145,155,.42); outline-offset:2px; }
.pronounce-word.playing { color:#fff; background:var(--teal-700); border-bottom-color:var(--teal-700); }
.paraphrase { margin-top:18px; border-top:1px solid var(--line); }
.paraphrase summary { padding:16px 0 3px; color:var(--teal-800); cursor:pointer; font-weight:800; }
.paraphrase summary span { color:var(--muted); font-size:.75rem; font-weight:500; margin-left:8px; }
.paraphrase ol { margin:12px 0 0; padding-left:22px; }
.paraphrase li { padding:7px 0 9px 5px; }
.paraphrase li p { margin:0; font-size:.9rem; font-weight:650; }
.chunks { margin-top:4px; color:var(--teal-700); font-size:.78rem; }
.study-section { margin:38px 0 0; }
.section-heading { display:flex; align-items:baseline; gap:10px; margin:0 0 15px; color:var(--teal-950); font-size:1.35rem; }
.section-heading small { color:var(--teal-600); font-size:.78rem; letter-spacing:.05em; }
.study-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }
.study-grid article { padding:17px; background:#fff; border:1px solid var(--line); border-radius:14px; box-shadow:0 6px 18px rgba(7,63,66,.05); min-width:0; }
.study-grid p { margin:0; }
.practice-en { margin-top:9px; color:var(--teal-700); font-weight:650; overflow-wrap:anywhere; }
.wrong { color:#a24831; text-decoration:line-through; overflow-wrap:anywhere; }
.right { color:var(--teal-700); font-weight:750; margin:5px 0; overflow-wrap:anywhere; }
.pitfalls p { color:var(--muted); font-size:.82rem; }
.shifts article { display:grid; grid-template-columns:minmax(0,1fr) auto minmax(0,1.5fr); gap:12px; align-items:center; }
.shifts b { color:var(--teal-600); font-size:1.2rem; }
.shifts strong { color:var(--teal-800); }
footer { margin-top:38px; color:var(--muted); font-size:.78rem; text-align:center; }
@media (max-width:900px) {
  .page { grid-template-columns:1fr; }
  .sidebar { position:static; }
  .sidebar-box { overflow-x:auto; padding:12px; }
  .sidebar h2 { padding-left:5px; }
  .map-nav { display:flex; width:max-content; gap:8px; }
  .map-link { width:220px; border:1px solid var(--line); border-radius:10px; padding:8px; }
  .bilingual { grid-template-columns:1fr; }
  .en-block { padding:12px 0 0; border-left:0; border-top:1px dashed var(--line); }
}
@media (max-width:620px) {
  .hero-inner { padding-top:32px; }
  .hero-flex { flex-direction:column; align-items:center; }
  .hero-cover { width:100%; max-width:360px; }
  .hero-text { text-align:center; }
  .page { padding-inline:10px; gap:18px; }
  .scene-card { border-radius:14px; padding:17px 13px; }
  .scene-topline { align-items:flex-start; }
  .scene-speak span:last-child { display:none; }
  .sentence { grid-template-columns:26px minmax(0,1fr); padding:13px 10px; gap:6px; }
  .note { grid-column:2; }
  .study-grid { grid-template-columns:1fr; }
  .shifts article { grid-template-columns:1fr; gap:5px; }
  .shifts b { transform:rotate(90deg); justify-self:start; }
}
@media (prefers-reduced-motion:reduce) { html { scroll-behavior:auto; } .speak-btn { transition:none; } }
.narration-player { margin-top:18px; }
.audio-label { color:rgba(255,255,255,.88); font-size:.82rem; margin:0 0 8px; }
.narration-player audio { width:100%; max-width:480px; border-radius:8px; }
.playback-speed { display:flex; align-items:center; gap:6px; margin-top:6px; }
.speed-label { color:rgba(255,255,255,.7); font-size:.72rem; }
.speed-btn { color:#fff; background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.2); border-radius:6px; padding:3px 8px; font-size:.7rem; cursor:pointer; }
.speed-btn.active { background:rgba(255,255,255,.28); border-color:rgba(255,255,255,.5); }
.narration-player .speak-btn { color:#fff; background:rgba(255,255,255,.14); border-color:rgba(255,255,255,.35); }
```

### 运行

```bash
node generate-{slug}.mjs
```

优先 Node：`/Applications/Cursor.app/Contents/Resources/app/resources/helpers/node`。

模板中的图片引用（`images/{slug}/hero.jpg`、`images/{slug}/s{N}.jpg`）必须与 Step 5.6 实际产出一致；若该期降级（`frames_fallback`），场景卡片复用 `hero.jpg`。

---

## Step 7：质量自检

- [ ] 产出为 HTML 文件（非 SVG），可在浏览器中正常渲染并支持语音朗读
- [ ] 场景数在 4–12，且有时间范围
- [ ] 每个关键场景有逐句中英对照表
- [ ] **每个句子有表达提示**（`<p class="note">`，含关键词对译 + 语境说明）
- [ ] 每个场景有场景级朗读音频（`data-audio` 指向 `audio/{slug}/s{N}.mp3`）
- [ ] 每个句子有逐句朗读音频（`data-audio` 指向 `audio/{slug}/s{N}-{idx:02d}.mp3`）
- [ ] 每个关键场景有 paraphrase（≥2 种说法），使用 `<details>` 可折叠结构，含 chunks
- [ ] Paraphrase 每组含中文意图 → 英文替换说法 + chunks 标注
- [ ] 避坑使用 wrong/right 对照格式（删除线红 ✕ + 加粗绿 ✓），4 组
- [ ] 认知转变使用三列对照格式（以前思维 → 新思维），3 组
- [ ] 今日可练使用卡片 grid 布局，4 个练习卡，每卡含中文意图 + 英文例句 + 朗读按钮（`data-audio` 指向练习 MP3）
- [ ] 硬词表覆盖视频主题领域词（≥20 个），按视频主题定制
- [ ] mark 函数中正则定义在循环外（`const re = ...`），禁止在 `while` 条件内联正则字面量（会导致无限循环卡死浏览器）
- [ ] Hero 头部含 narration 中文语音播放按钮（`data-audio` 指向 narration.mp3，禁止使用静态 `<audio>` 元素，避免预加载卡死浏览器）
- [ ] 侧边栏场景地图可点击跳转，含编号徽章 + 中英标题 + 时间
- [ ] Hero 头部含封面图 `images/{slug}/hero.jpg`（`<img class="hero-cover">`）
- [ ] 每个场景卡片含场景截图 `images/{slug}/s{N}.jpg`（`<img class="scene-frame" loading="lazy">`）
- [ ] 图片文件齐全：`hero.jpg` + 每个场景 `s{N}.jpg`，数量与场景数一致（降级期场景图复用 hero.jpg）
- [ ] 页脚标注「场景/句子朗读使用 edge-tts 神经网络语音 · 单词发音使用浏览器 Web Speech API」
- [ ] 音频文件齐全：narration.mp3 + 每个场景 s{N}.mp3 + 每句 s{N}-idx.mp3 + 练习 practice-idx.mp3
- [ ] 不是「内容总结文」，而是「可开口练的情景英语」
- [ ] HTML 单文件，CSS/JS 内嵌<br><br>音频通过 `data-audio` 按钮 + JS `new Audio()` 按需加载外部 MP3（edge-tts 生成），**禁止静态 `<audio>` 元素**

---

## Step 8：更新 index.json

将新条目追加到 `docs/index.json` 数组开头：

```json
{
  "slug": "crab-london",
  "date": "YYYY-MM-DD",
  "title": "视频标题",
  "title_en": "English Title",
  "platform": "bilibili",
  "url": "原始短链接",
  "webpage_url": "解析后的完整 URL",
  "duration_sec": 439,
  "scenes": 9,
  "sentences": 52,
  "html": "slug-场景英译.html",
  "cover": "images/slug/hero.jpg",
  "speech": true
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `slug` | 是 | 英文/拼音 slug，与 HTML 文件名一致 |
| `date` | 是 | 展示日期 `YYYY-MM-DD` |
| `title` | 是 | 视频中文标题 |
| `title_en` | 是 | 英文副标题 |
| `platform` | 是 | `bilibili` 或 `xiaohongshu` |
| `url` | 是 | 原始短链接（如 `https://b23.tv/xxx`） |
| `webpage_url` | 是 | 解析后的完整 URL |
| `duration_sec` | 是 | 视频时长（秒） |
| `scenes` | 是 | 场景数 |
| `sentences` | 是 | 总句数 |
| `html` | 是 | HTML 文件名 `{slug}-场景英译.html` |
| `cover` | 是 | Hero 封面路径 `images/{slug}/hero.jpg` |
| `speech` | 是 | 是否支持语音朗读（HTML 格式始终为 `true`） |
| `frames_fallback` | 否 | 画面流不可用时置 `true`（场景图复用 hero.jpg） |

失败项加 `"error": true` 与 `error_message`。**不再使用** `svg_height` 字段。

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
# 删除临时画面流与封面（图片已落盘 docs/images/{slug}/）
rm {slug}-video.* {slug}-thumb.*
# 可选：rm {slug}.m4a
```

若来自 cron 队列，从 `docs/pending-urls.txt` 删除已处理 URL；文件空则保留空文件或删除均可。

---

## 产出清单

| 文件 | 说明 |
|------|------|
| `{slug}.m4a` | 原始音频（可选保留） |
| `{slug}.json` / `.srt` | 转录产物（可选保留） |
| `docs/{slug}-场景英译.html` | **交互式场景英译学习卡片**（主产出，CSS/JS 内嵌，音频通过 `data-audio` + JS `new Audio()` 按需加载 MP3） |
| `docs/audio/{slug}/` | **音频目录**：narration.mp3（中文讲解）+ 场景/逐句/练习英文 MP3（edge-tts 生成） |
| `docs/images/{slug}/` | **图片目录**：hero.jpg（视频封面）+ 各场景关键帧 s1.jpg~s{N}.jpg |

---

## 约束

- 仅处理 B 站 / 小红书链接
- 不修改非 `docs/` 文件（`generate-{slug}.mjs` 除外，用完删除）
- 不修改 `.gitignore`
- 同 URL 不重复处理
- **所有视频处理产出必须为 HTML 格式**，不再使用 SVG
- 音频使用 edge-tts 预生成 MP3（Python 脚本 `scripts/generate_audio.py`）
- 场景截图使用 ffmpeg 从视频画面流抽帧（Python 脚本 `scripts/extract_frames.py`），图片存 `docs/images/{slug}/`
- 播放器加载 MP3 文件，不是运行时合成语音
- 不依赖 `svg-auto-height.mjs`
- 硬词表根据视频主题定制（非固定模板）
- **必须 push 到 main**，否则 Pages 不更新
- 主目标是情景英语，不是视频内容摘要
