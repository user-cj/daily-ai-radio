"""Exercise the real automatic pipeline in an isolated, unpublished directory."""
import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path

from auto_news import BJT, ROOT, collect, edit
from build_radio import build


def site_hashes():
    return {
        path.relative_to(ROOT / 'site').as_posix(): hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()
        for path in (ROOT / 'site').rglob('*') if path.is_file()
    }


def main():
    start = time.monotonic()
    original = site_hashes()
    day = datetime.now(BJT).date()
    target = ROOT / 'work' / 'cloud-check'
    target.mkdir(parents=True, exist_ok=True)
    sources = collect(day, target / 'sources.json')
    print(f'Cloud check: {len(sources)} dated primary sources collected', flush=True)
    edition = edit(sources, day, os.environ.get('RADIO_MODEL', 'qwen2.5:7b'))
    draft = target / 'edition.json'
    draft.write_text(json.dumps(edition, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Cloud check: five stories passed evidence and text-consistency checks', flush=True)
    # Start with no cached audio to verify the actual cloud TTS connection.
    build(draft, target / 'site')
    result = json.loads((target / 'site' / 'episodes.json').read_text(encoding='utf-8'))[0]
    assert len(result['items']) == 5
    assert result['duration_seconds'] >= 30
    assert result['voice'] in ('zh-CN-YunyangNeural', 'zh-CN-YunxiNeural')
    assert original == site_hashes(), 'Cloud check changed the public edition'
    summary = {
        'ok': True, 'checked_at': datetime.now(BJT).isoformat(),
        'source_count': len(sources), 'stories': len(result['items']),
        'voice': result['voice'], 'audio_seconds': result['duration_seconds'],
        'elapsed_seconds': round(time.monotonic() - start),
        'public_edition_unchanged': True,
    }
    (target / 'result.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
