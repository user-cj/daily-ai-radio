"""Validated five-story edition -> Mandarin male MP3 -> atomic static website."""
import argparse
import asyncio
from datetime import date, datetime, timedelta, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlparse

BJT = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parent
FIELDS = ('title', 'category', 'published', 'facts', 'analysis', 'chain', 'risk', 'sources')


def validate(edition):
    day = date.fromisoformat(edition['date'])
    if day > datetime.now(BJT).date():
        raise ValueError('不能发布未来日期节目')
    if len(edition['items']) != 5:
        raise ValueError('节目必须恰好包含五条')
    seen = set()
    for item in edition['items']:
        if any(not item.get(key) for key in FIELDS):
            raise ValueError('每条必须有事实、分析、关联、风险、日期与来源')
        age = (day - date.fromisoformat(item['published'])).days
        if not 0 <= age <= 7:
            raise ValueError('来源日期不能在节目之后或早于七天')
        if item['title'] in seen:
            raise ValueError('重复选题')
        seen.add(item['title'])
        for source in item['sources']:
            parsed = urlparse(source['url'])
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username:
                raise ValueError('来源必须为有效 HTTPS 原文链接')
    return edition


def script(edition):
    pieces = [edition['intro']]
    for i, item in enumerate(edition['items'], 1):
        source_day = date.fromisoformat(item['published'])
        pieces.extend([f"第{i}条，{item['title']}。消息日期，{source_day.year}年{source_day.month}月{source_day.day}日。来源，{item['sources'][0]['name']}。", '事实。' + item['facts'], item['analysis'], item['chain'], item['risk']])
    return '\n\n'.join(pieces + ['资料覆盖说明。' + edition['coverage'], edition['outro']])


def transcript(edition):
    parts = [f"# 硬件学长 · AI财经广播｜{edition['date']}", edition['review'], edition['intro']]
    for i, item in enumerate(edition['items'], 1):
        parts += [f"## {i}. {item['title']}", f"消息日期：{item['published']}｜{item['category']}"]
        parts += [f"**{label}**：{item[key]}" for label, key in [('事实', 'facts'), ('分析', 'analysis'), ('产业关联', 'chain'), ('风险', 'risk')]]
        parts += [f"来源：[{s['name']}]({s['url']})" for s in item['sources']]
    return '\n\n'.join(parts + ['## 资料覆盖', edition['coverage'], edition['outro']]) + '\n'


async def synthesize(text, output):
    import edge_tts
    error = None
    for voice in ('zh-CN-YunyangNeural', 'zh-CN-YunxiNeural'):
        for attempt in range(2):
            try:
                await asyncio.wait_for(edge_tts.Communicate(text, voice, rate='-5%').save(str(output)), timeout=240)
                from mutagen.mp3 import MP3
                if output.stat().st_size < 10000 or MP3(output).info.length < 30:
                    raise ValueError('音频为空或过短')
                return voice
            except Exception as exc:
                error = exc
                if output.exists():
                    output.unlink()
                await asyncio.sleep(2 + attempt * 2)
    raise RuntimeError(f'男声语音生成失败：{type(error).__name__}') from error


def render(edition, history, duration):
    esc = html.escape
    cards = []
    for i, item in enumerate(edition['items'], 1):
        sources = ''.join(f'<a href="{esc(s["url"], quote=True)}" target="_blank" rel="noopener noreferrer">{esc(s["name"])} ↗</a>' for s in item['sources'])
        details = ''.join(f'<p><b>{label}</b>{esc(item[key])}</p>' for label, key in [('事实', 'facts'), ('分析', 'analysis'), ('产业关联', 'chain'), ('风险', 'risk')])
        cards.append(f'<article><div class="eyebrow"><span>{i:02d} / {esc(item["category"])}</span><time>{esc(item["published"])}</time></div><h2>{esc(item["title"])}</h2>{details}<div class="sources">{sources}</div></article>')
    old = ''.join(f'<li><a href="{esc(e["page"], quote=True)}">{esc(e["date"])} · {esc(e["edition"])}</a></li>' for e in history)
    template = (ROOT / 'web/template.html').read_text(encoding='utf-8')
    values = {'DATE': esc(edition['date']), 'EDITION': esc(edition['edition']), 'REVIEW': esc(edition['review']), 'AUDIO': esc(edition['audio']), 'TEXT': esc(edition['transcript']), 'INTRO': esc(edition['intro']), 'CARDS': ''.join(cards), 'COVERAGE': esc(edition['coverage']), 'OUTRO': esc(edition['outro']), 'HISTORY': old, 'DURATION': f'{int(duration // 60)}分{int(duration % 60):02d}秒'}
    for key, value in values.items():
        template = template.replace('{{' + key + '}}', value)
    return template


def build(input_path, site):
    edition = validate(json.loads(Path(input_path).read_text(encoding='utf-8-sig')))
    text = script(edition)
    digest = hashlib.sha256(text.encode()).hexdigest()[:10]
    base = f"{edition['date']}-{digest}"
    site = Path(site)
    site.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='radio-', dir=site.parent) as temp:
        stage = Path(temp) / 'site'
        if site.exists():
            shutil.copytree(site, stage)
        else:
            stage.mkdir()
        (stage / 'audio').mkdir(exist_ok=True)
        (stage / 'transcripts').mkdir(exist_ok=True)
        (stage / 'editions').mkdir(exist_ok=True)
        mp3 = stage / 'audio' / f'{base}.mp3'
        if not mp3.exists():
            edition['voice'] = asyncio.run(synthesize(text, mp3))
        else:
            cached = stage / 'episodes.json'
            previous = json.loads(cached.read_text(encoding='utf-8')) if cached.exists() else []
            matching = next((e for e in previous if e.get('audio') == f'audio/{base}.mp3'), None)
            edition['voice'] = matching.get('voice', 'unknown') if matching else 'unknown'
        from mutagen.mp3 import MP3
        duration = MP3(mp3).info.length
        edition.update(audio=f'audio/{base}.mp3', transcript=f'transcripts/{base}.md', page=f'editions/{base}.html', duration_seconds=round(duration, 1))
        (stage / edition['transcript']).write_text(transcript(edition), encoding='utf-8')
        history_path = stage / 'episodes.json'
        history = json.loads(history_path.read_text(encoding='utf-8')) if history_path.exists() else []
        history = [edition] + [e for e in history if e['date'] != edition['date']]
        history.sort(key=lambda e: e['date'], reverse=True)
        history = history[:14]
        markup = render(edition, history, duration)
        (stage / 'index.html').write_text(markup, encoding='utf-8')
        # Old pages must list the current retained window as well, so their
        # archive navigation never points to editions that were pruned.
        for entry in history:
            archived = render(entry, history, entry['duration_seconds'])
            (stage / entry['page']).write_text(archived.replace('<head>', '<head><base href="../">', 1), encoding='utf-8')
        (stage / 'episodes.json').write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')
        (stage / 'status.json').write_text(json.dumps({'ok': True, 'attempted_at': datetime.now(BJT).isoformat(), 'latest_date': edition['date']}, ensure_ascii=False), encoding='utf-8')
        (stage / '.nojekyll').touch()
        for name in ('style.css', 'player.js', 'icon.svg', 'manifest.webmanifest'):
            shutil.copyfile(ROOT / 'web' / name, stage / name)
        keep = {e[k] for e in history for k in ('audio', 'transcript', 'page')}
        for folder in ('audio', 'transcripts', 'editions'):
            for asset in (stage / folder).iterdir():
                if asset.relative_to(stage).as_posix() not in keep:
                    asset.unlink()
        # Every asset and audio is validated before touching the published directory.
        assets = [a for a in stage.rglob('*') if a.is_file()]
        assets.sort(key=lambda a: (a.name == 'index.html', a.name in ('episodes.json', 'status.json')))
        for asset in assets:
            target = site / asset.relative_to(stage)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + '.tmp')
            shutil.copyfile(asset, temporary)
            os.replace(temporary, target)
        for folder in ('audio', 'transcripts', 'editions'):
            for asset in (site / folder).iterdir():
                if asset.relative_to(site).as_posix() not in keep:
                    asset.unlink()
    print(json.dumps({'date': edition['date'], 'seconds': round(duration), 'voice': edition['voice'], 'audio': edition['audio']}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--site', default=str(ROOT / 'site'))
    args = parser.parse_args()
    build(args.input, args.site)
