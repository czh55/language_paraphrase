#!/usr/bin/env python3
"""
从场景英译 HTML 提取英文内容，生成高质量 MP3 音频。
使用 edge-tts（微软神经网络语音，免费）。

用法：
  python3 scripts/generate_audio.py --slug=crab-london
  python3 scripts/generate_audio.py --slug=crab-london --print-script
  python3 scripts/generate_audio.py --slug=crab-london --scenes-only
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DOCS = ROOT / "docs"
AUDIO_DIR = DOCS / "audio"
SCRIPTS_DIR = ROOT / "scripts"

ZH_VOICE = "zh-CN-XiaoxiaoNeural"
EN_VOICE_US = "en-US-JennyNeural"
EN_VOICE_GB = "en-GB-SoniaNeural"
MAX_CHUNK_LEN = 2000

# --- Scene data for crab-london ---

META = {
    "slug": "crab-london",
    "title": "蟹 逅 伦 敦！",
    "title_en": "Crab Encounter London — A Movie-Map Travelogue",
    "duration": "7分19秒",
    "scenes": 9,
    "sentences": 51,
}

SCENES = [
    {
        "id": "s1", "title_cn": "开场：帕丁顿熊的比喻",
        "title_en": "Opening: The Paddington Metaphor",
        "time": "00:00–00:51",
        "speak": "There's a famous little bear in London, Paddington Bear. He came all the way from Peru by boat. I feel like I'm a lot like him, I also came from far away, but by plane. Instead of marmalade, I brought a suitcase full of gear. When Paddington arrived in London, he had a tag around his neck that said please look after this bear. As a first-timer in London, I'd like to borrow that line: please look after this crab. Before standing here, my knowledge of London was pretty scattered. Big Ben, unpredictable weather, and streets that felt familiar from movies. So this time I want to be a proper tourist and see what those movie locations actually look like in real life. Welcome to this episode of Encounter Time, London.",
        "sentences": [
            "There's a famous little bear in London, Paddington Bear.",
            "He came all the way from Peru by boat.",
            "I feel like I'm a lot like him, I also came from far away, but by plane.",
            "Instead of marmalade, I brought a suitcase full of gear.",
            "When Paddington arrived in London, he had a tag around his neck that said please look after this bear.",
            "As a first-timer in London, I'd like to borrow that line: please look after this crab.",
            "Before standing here, my knowledge of London was pretty scattered.",
            "Big Ben, unpredictable weather, and streets that felt familiar from movies.",
            "So this time I want to be a proper tourist and see what those movie locations actually look like in real life.",
            "Welcome to this episode of Encounter Time, London.",
        ],
    },
    {
        "id": "s2", "title_cn": "初到伦敦：大本钟与天气",
        "title_en": "First Impressions: Big Ben & Weather",
        "time": "00:55–01:20",
        "speak": "Hey guys, we made it to London. Since it's my first time, I gotta do the obligatory tourist stuff. Big Ben is right behind me. But the weather today is just so typical, so London, drizzly and grey. Apparently London's annual rainfall is actually less than Shanghai's, let that sink in. It's mainly because it's always just a light drizzle. Maybe that's why you often see Londoners not bothering with umbrellas.",
        "sentences": [
            "Hey guys, we made it to London.",
            "Since it's my first time, I gotta do the obligatory tourist stuff. Big Ben is right behind me.",
            "But the weather today is just so typical, so London, drizzly and grey.",
            "Apparently London's annual rainfall is actually less than Shanghai's, let that sink in.",
            "It's mainly because it's always just a light drizzle. Maybe that's why you often see Londoners not bothering with umbrellas.",
        ],
    },
    {
        "id": "s3", "title_cn": "新冠纪念墙",
        "title_en": "COVID Memorial Wall",
        "time": "01:21–01:44",
        "speak": "The wall behind me is covered in hearts. But each heart here represents someone who passed away from COVID.",
        "sentences": [
            "The wall behind me is covered in hearts.",
            "But each heart here represents someone who passed away from COVID.",
        ],
    },
    {
        "id": "s4", "title_cn": "落地第一顿：炸鱼薯条 & 中餐",
        "title_en": "First Meal: Fish & Chips & Chinese",
        "time": "01:44–02:36",
        "speak": "For my first meal in London, fish and chips was a no-brainer. We found a place that's been around since 1988, supposedly one of the best in the UK. Even ran into a local who told us it's the best fish and chips in London. Can't say if it's the best, but at least we got that first-meal-in-London ritual out of the way. Rituals aside, a Chinese stomach is a different story. So we came to this long-standing spot. Check out this Xi'an-style roujiamo, works out to over a hundred yuan each. Chinese food abroad, the price goes up, but the appeal doesn't drop one bit.",
        "sentences": [
            "For my first meal in London, fish and chips was a no-brainer.",
            "We found a place that's been around since 1988, supposedly one of the best in the UK.",
            "Even ran into a local who told us it's the best fish and chips in London.",
            "Can't say if it's the best, but at least we got that first-meal-in-London ritual out of the way.",
            "Rituals aside, a Chinese stomach is a different story. So we came to this long-standing spot.",
            "Check out this Xi'an-style roujiamo, works out to over a hundred yuan each.",
            "Chinese food abroad, the price goes up, but the appeal doesn't drop one bit.",
        ],
    },
    {
        "id": "s5", "title_cn": "酒吧景观位",
        "title_en": "Bar with a View",
        "time": "02:36–02:56",
        "speak": "There's this pretty famous bar in London, but I didn't have a reservation, so I ended up at the counter. But who would've thought, this last-minute seat turned out to be the best view in the whole place. Pretty amazing experience, right? Though the bill was just as impressive.",
        "sentences": [
            "There's this pretty famous bar in London, but I didn't have a reservation, so I ended up at the counter.",
            "But who would've thought, this last-minute seat turned out to be the best view in the whole place.",
            "Pretty amazing experience, right? Though the bill was just as impressive.",
        ],
    },
    {
        "id": "s6", "title_cn": "自然历史博物馆",
        "title_en": "Natural History Museum",
        "time": "02:58–04:23",
        "speak": "Even though it's my first time in London, some of these scenes I've already seen in movies. Like Paddington Station right here, does it look familiar? Today we're using movies as our map to see London beyond the screen. Following Paddington's footsteps, I ended up at the Natural History Museum, the very place where Paddington was almost turned into a stuffed specimen. Wow this place is absolutely stunning, the ceiling is so high, it's like a castle. The main thing to see in this hall is the blue whale skeleton hanging from the ceiling. It's posed mid-dive, like it's swooping down to catch prey. I feel so tiny standing underneath it. The fossils are genuinely impressive, but there are also loads of animal specimens here, every single one looks so lifelike. Getting to see so many rare specimens up close is pretty amazing. Though I don't really know the stories of how they lived. I just hope they ended up here after their lives ran their natural course.",
        "sentences": [
            "Even though it's my first time in London, some of these scenes I've already seen in movies.",
            "Like Paddington Station right here, does it look familiar?",
            "Today we're using movies as our map to see London beyond the screen.",
            "Following Paddington's footsteps, I ended up at the Natural History Museum, the very place where Paddington was almost turned into a stuffed specimen.",
            "Wow this place is absolutely stunning, the ceiling is so high, it's like a castle.",
            "The main thing to see in this hall is the blue whale skeleton hanging from the ceiling.",
            "It's posed mid-dive, like it's swooping down to catch prey. I feel so tiny standing underneath it.",
            "The fossils are genuinely impressive, but there are also loads of animal specimens here, every single one looks so lifelike.",
            "Getting to see so many rare specimens up close is pretty amazing.",
            "Though I don't really know the stories of how they lived. I just hope they ended up here after their lives ran their natural course.",
        ],
    },
    {
        "id": "s7", "title_cn": "诺丁山 & 电影书店",
        "title_en": "Notting Hill & the Bookshop",
        "time": "04:27–05:10",
        "speak": "I wonder how many people watched Notting Hill first and only later found out it's an actual place in London. That tiny travel bookshop in the movie is what made this place stick in so many people's minds. This is number 142, where the leads meet in the film, but it's not actually a bookshop, it's a souvenir store. The real-life inspiration for the bookshop was actually this other bookstore, but funnily enough, they never filmed there either. The crew just built a replica of it on a soundstage. Movies may not be real, but they can definitely turn a street into a place people from all over the world come to check out, that part is very real.",
        "sentences": [
            "I wonder how many people watched Notting Hill first and only later found out it's an actual place in London.",
            "That tiny travel bookshop in the movie is what made this place stick in so many people's minds.",
            "This is number 142, where the leads meet in the film, but it's not actually a bookshop, it's a souvenir store.",
            "The real-life inspiration for the bookshop was actually this other bookstore, but funnily enough, they never filmed there either. The crew just built a replica of it on a soundstage.",
            "Movies may not be real, but they can definitely turn a street into a place people from all over the world come to check out, that part is very real.",
        ],
    },
    {
        "id": "s8", "title_cn": "裁缝街 & Kingsman",
        "title_en": "Savile Row & Kingsman",
        "time": "05:20–06:41",
        "speak": "This is Savile Row, some of these shops have been around for centuries. I heard a bespoke suit here costs a few thousand pounds and takes six weeks. But what really put this street on the map wasn't just the suits, it was a movie called Kingsman. See it says Kingsman right here. This shop first opened in 1849. Apparently the director of Kingsman was here getting fitted when inspiration struck, and that's how the movie was born. Let's take a look at the price of this suit. So expensive, over twenty thousand. After walking in, I noticed a sign saying no filming, but I still snuck in a few shots. They didn't seem to stop me either, so the whole thing felt super sneaky. I took a quiet look, the prices inside are pretty steep, over two thousand pounds a piece. It was just a plain black suit, maybe I just can't tell what makes it special. But this place is seriously famous, loads of British figures like Churchill and Prince William have had suits made here.",
        "sentences": [
            "This is Savile Row, some of these shops have been around for centuries.",
            "I heard a bespoke suit here costs a few thousand pounds and takes six weeks.",
            "But what really put this street on the map wasn't just the suits, it was a movie called Kingsman.",
            "See it says Kingsman right here. This shop first opened in 1849.",
            "Apparently the director of Kingsman was here getting fitted when inspiration struck, and that's how the movie was born.",
            "Let's take a look at the price of this suit. So expensive, over twenty thousand.",
            "After walking in, I noticed a sign saying no filming, but I still snuck in a few shots. They didn't seem to stop me either, so the whole thing felt super sneaky.",
            "I took a quiet look, the prices inside are pretty steep, over two thousand pounds a piece. It was just a plain black suit, maybe I just can't tell what makes it special.",
            "But this place is seriously famous, loads of British figures like Churchill and Prince William have had suits made here.",
        ],
    },
    {
        "id": "s9", "title_cn": "最后一天：晴天伦敦",
        "title_en": "Final Day: Sunny London",
        "time": "06:44–07:19",
        "speak": "The rain barely let up during my days in London, but on the final day, hey, the sun came out. Big Ben is still Big Ben, but when the sun comes out, it feels like a whole different city. As for what London is really like, honestly, I can't quite put my finger on it after just one visit. I managed to find all those movie locations, but the London beyond the movies? Might take a few more trips. And of course, I'd love for you guys to share, what does London look like through your eyes?",
        "sentences": [
            "The rain barely let up during my days in London, but on the final day, hey, the sun came out.",
            "Big Ben is still Big Ben, but when the sun comes out, it feels like a whole different city.",
            "As for what London is really like, honestly, I can't quite put my finger on it after just one visit.",
            "I managed to find all those movie locations, but the London beyond the movies? Might take a few more trips.",
            "And of course, I'd love for you guys to share, what does London look like through your eyes?",
        ],
    },
]

PRACTICE = [
    "We made it to London! I came all the way from China for this.",
    "I ended up at the counter, but it turned out to be the best seat in the house.",
    "That one movie put this tiny street on the map for tourists around the world.",
    "I can't quite put my finger on what makes this city so special, but I love it.",
]


def estimate_duration(char_count: int) -> str:
    minutes = char_count / 280
    low = max(1, int(minutes))
    high = max(low, int(minutes + 0.99))
    if low == high:
        return f"约 {low} 分钟"
    return f"约 {low} 到 {high} 分钟"


def build_narration_script(meta: dict, scenes: list[dict]) -> str:
    parts: list[str] = []
    total = len(scenes)

    # Opening
    parts.append(
        f"欢迎收听场景英译语音讲解。今天我们要学习的视频是「{meta['title']}」，"
        f"英文副标题：{meta['title_en']}。"
        f"视频总长{meta['duration']}，共分为{total}个场景、{meta['sentences']}句核心英文表达。"
        f"好，我们开始。"
    )

    # Scene-by-scene narration
    for i, scene in enumerate(scenes, 1):
        num = i
        cn = scene["title_cn"]
        en = scene["title_en"]
        time = scene["time"]
        parts.append(
            f"第{num}个场景，{cn}，{en}。时间范围{time}。"
            f"请听场景完整英文："
        )
        parts.append(scene["speak"])
        if i < total:
            parts.append("好，进入下一个场景。")

    # Practice section
    parts.append("下面是今日可练环节，请听完中文意图后尝试说出英文。")
    practice_prompts = [
        "第一题：用 made it 和 all the way from 表达「终于到了，从很远的地方来」。",
        "第二题：用 ended up at 和 turned out to be 表达意料之外的结果。",
        "第三题：用 put on the map 表达「让某地出名」。",
        "第四题：用 can't quite put my finger on it 表达「说不清楚、无法准确描述」。",
    ]
    for i, (prompt, english) in enumerate(zip(practice_prompts, PRACTICE)):
        parts.append(prompt)
        parts.append(english)

    parts.append(
        "讲解完毕。建议回到网页查看完整逐句中英对照与表达提示，跟着朗读按钮反复练习。祝学习顺利！"
    )

    return "\n\n".join(p.strip() for p in parts if p.strip())


def split_text(text: str, max_len: int = MAX_CHUNK_LEN) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        if len(para) > max_len:
            if current:
                chunks.append(current.strip())
                current = ""
            for i in range(0, len(para), max_len):
                chunks.append(para[i : i + max_len])
            continue
        candidate = f"{current}\n\n{para}".strip() if current else para
        if len(candidate) <= max_len:
            current = candidate
        else:
            if current:
                chunks.append(current.strip())
            current = para
    if current:
        chunks.append(current.strip())
    return chunks


async def _synthesize_chunk(text: str, output: Path, voice: str) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output))


def _concat_mp3(files: list[Path], output: Path) -> None:
    list_file = output.parent / f".concat_{output.stem}.txt"
    try:
        with open(list_file, "w", encoding="utf-8") as f:
            for p in files:
                f.write(f"file '{p.resolve()}'\n")
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(list_file), "-c", "copy", str(output),
            ],
            check=True,
            capture_output=True,
        )
    finally:
        if list_file.exists():
            list_file.unlink()


async def synthesize_speech(text: str, output_path: Path, voice: str) -> bool:
    chunks = split_text(text)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if len(chunks) == 1:
        await _synthesize_chunk(chunks[0], output_path, voice)
        return output_path.exists()

    temp_files: list[Path] = []
    try:
        for i, chunk in enumerate(chunks):
            tmp = output_path.parent / f".tmp_{output_path.stem}_{i}.mp3"
            await _synthesize_chunk(chunk, tmp, voice)
            temp_files.append(tmp)
        _concat_mp3(temp_files, output_path)
        return output_path.exists()
    finally:
        for f in temp_files:
            if f.exists():
                f.unlink()


async def generate_scene_mp3(scene: dict, slug: str, voice: str) -> bool:
    out = AUDIO_DIR / slug / f"{scene['id']}.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        print(f"  (skip) {out}")
        return True
    ok = await synthesize_speech(scene["speak"], out, voice)
    if ok:
        print(f"  ✓ scene {scene['id']}")
    else:
        print(f"  ✗ FAIL {scene['id']}")
    return ok


async def generate_sentence_mp3(
    scene_id: str, idx: int, text: str, slug: str, voice: str
) -> bool:
    out = AUDIO_DIR / slug / f"{scene_id}-{idx:02d}.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        return True
    ok = await synthesize_speech(text, out, voice)
    return ok


async def generate_practice_mp3(idx: int, text: str, slug: str, voice: str) -> bool:
    out = AUDIO_DIR / slug / f"practice-{idx}.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        print(f"  (skip) practice-{idx}")
        return True
    ok = await synthesize_speech(text, out, voice)
    if ok:
        print(f"  ✓ practice-{idx}")
    return ok


async def generate_all_english(slug: str) -> bool:
    voice = EN_VOICE_US
    scenes = SCENES
    practice = PRACTICE

    # Generate scene-level MP3s
    print(f"\n📢 生成场景英文朗读 ({len(scenes)} 个场景)...")
    results = await asyncio.gather(
        *(generate_scene_mp3(s, slug, voice) for s in scenes)
    )

    # Generate sentence-level MP3s
    total_sents = sum(len(s["sentences"]) for s in scenes)
    print(f"\n📢 生成逐句英文朗读 ({total_sents} 句)...")
    sent_tasks = []
    for scene in scenes:
        for i, text in enumerate(scene["sentences"]):
            sent_tasks.append(
                generate_sentence_mp3(scene["id"], i + 1, text, slug, voice)
            )
    sent_results = await asyncio.gather(*sent_tasks)

    # Generate practice MP3s
    print(f"\n📢 生成练习句朗读 ({len(practice)} 句)...")
    practice_tasks = [
        generate_practice_mp3(i, text, slug, voice)
        for i, text in enumerate(practice)
    ]
    practice_results = await asyncio.gather(*practice_tasks)

    scene_ok = all(results)
    sent_ok = all(sent_results)
    practice_ok = all(practice_results)
    all_ok = scene_ok and sent_ok and practice_ok

    print(
        f"\n{'='*40}"
        f"\n场景: {sum(results)}/{len(results)} ✓"
        f"\n逐句: {sum(sent_results)}/{len(sent_results)} ✓"
        f"\n练习: {sum(practice_results)}/{len(practice_results)} ✓"
        f"\n{'='*40}"
    )
    return all_ok


async def generate_narration(slug: str) -> bool:
    print(f"\n🎙 生成中文讲解旁白...")
    script = build_narration_script(META, SCENES)
    out_mp3 = AUDIO_DIR / slug / "narration.mp3"
    out_txt = AUDIO_DIR / slug / "narration.txt"
    out_mp3.parent.mkdir(parents=True, exist_ok=True)

    if out_mp3.exists():
        print(f"  (skip) narration.mp3")
    else:
        ok = await synthesize_speech(script, out_mp3, ZH_VOICE)
        if not ok:
            print(f"  ✗ FAIL narration.mp3")
            return False
        print(f"  ✓ narration.mp3")

    out_txt.write_text(script, encoding="utf-8")
    print(f"  ✓ narration.txt ({len(script)} 字)")
    return True


def generate_manifest(slug: str, scenes: list[dict]) -> dict:
    return {
        "slug": slug,
        "scenes": len(scenes),
        "sentences": sum(len(s["sentences"]) for s in scenes),
        "scene_audio": [f"audio/{slug}/{s['id']}.mp3" for s in scenes],
        "sentence_audio": {
            f"{s['id']}-{i+1:02d}": f"audio/{slug}/{s['id']}-{i+1:02d}.mp3"
            for s in scenes
            for i in range(len(s["sentences"]))
        },
        "practice_audio": [
            f"audio/{slug}/practice-{i}.mp3" for i in range(len(PRACTICE))
        ],
        "narration": f"audio/{slug}/narration.mp3",
    }


def main() -> None:
    from argparse import ArgumentParser

    parser = ArgumentParser(description="生成场景英译语音讲解")
    parser.add_argument("--slug", type=str, required=True, help="视频 slug")
    parser.add_argument("--print-script", action="store_true", help="只打印旁白稿")
    parser.add_argument("--scenes-only", action="store_true", help="仅生成英文场景/逐句/练习 MP3")
    args = parser.parse_args()

    slug = args.slug
    out_dir = AUDIO_DIR / slug

    if args.print_script:
        script = build_narration_script(META, SCENES)
        print(script)
        return

    ok_english = asyncio.run(generate_all_english(slug))

    if args.scenes_only:
        sys.exit(0 if ok_english else 1)

    ok_narration = asyncio.run(generate_narration(slug))

    if ok_narration:
        manifest = generate_manifest(slug, SCENES)
        manifest_path = out_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"  ✓ manifest.json")

    all_ok = ok_english and ok_narration
    print(f"\n✓ 完成！音频目录: docs/audio/{slug}/")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
