"""Checks for financially material publication safeguards, with no network."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import sys
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import auto_news
import build_radio


class PublicationSafeguards(unittest.TestCase):
    def setUp(self):
        self.edition = json.loads((ROOT / 'episodes/2026-10-11.json').read_text(encoding='utf-8'))

    def test_not_five_stories_rejected(self):
        self.edition['items'].pop()
        with self.assertRaises(ValueError):
            build_radio.validate(self.edition)

    def test_future_source_rejected(self):
        self.edition['items'][0]['published'] = '2026-10-12'
        with self.assertRaises(ValueError):
            build_radio.validate(self.edition)

    def test_stale_source_rejected(self):
        self.edition['items'][0]['published'] = '2026-10-01'
        with self.assertRaises(ValueError):
            build_radio.validate(self.edition)

    def test_unsafe_source_rejected(self):
        self.edition['items'][0]['sources'][0]['url'] = 'javascript:alert(1)'
        with self.assertRaises(ValueError):
            build_radio.validate(self.edition)

    def test_repeated_story_rejected(self):
        self.edition['items'][1]['title'] = self.edition['items'][0]['title']
        with self.assertRaises(ValueError):
            build_radio.validate(self.edition)

    def test_repeated_risk_cannot_pad_a_publishable_story(self):
        source = {'id': 'S01', 'title': '公开征求意见', 'body': '正式文本与实施日期仍需公告确认。', 'publisher': '中国证监会', 'bucket': 'A股与政策', 'published': '2026-10-09'}
        item = deepcopy(self.edition['items'][0])
        item.update(source_id='S01', evidence=['正式文本与实施日期仍需公告确认。'], risk='正式文本与实施日期仍需公告确认。' * 4)
        with self.assertRaisesRegex(ValueError, '重复句子'):
            auto_news.evidence_validate({'items': [item]}, [source], date(2026,10,11), complete=False)

    def test_guidance_does_not_imply_segment_competitiveness(self):
        item = {'facts': '公司发布合并业绩预告。微软宣布产品的通用', 'analysis': '可能表明半导体市场竞争力强劲', 'chain': '半导体', 'risk': '正式文本与实施日期仍需公告确认'}
        source = {'title': 'Samsung Electronics Announces Earnings Guidance', 'bucket': '芯片与硬件'}
        reviewed = auto_news.apply_editorial_notes(item, source)
        self.assertEqual(reviewed['facts'], '公司发布合并业绩预告。')
        self.assertIn('无法单独证明', reviewed['analysis'])
        self.assertNotIn('正式文本', reviewed['risk'])

    def test_source_body_cannot_execute_html(self):
        self.edition['items'][0]['facts'] = '<script>alert(1)</script>'
        self.edition.update(audio='audio/test.mp3', transcript='transcripts/test.md', page='editions/test.html')
        markup=build_radio.render(self.edition, [self.edition], 60)
        self.assertNotIn('<script>alert(1)</script>', markup)
        self.assertIn('&lt;script&gt;', markup)

    def test_long_quotes_shortened_without_inventing_evidence(self):
        excerpt=' '.join(f'word{i}' for i in range(45))
        shortened=auto_news.shorten_quotes([excerpt])
        self.assertIn(shortened[0], excerpt)
        self.assertLessEqual(len(auto_news.re.findall('[A-Za-z]+', shortened[0])),25)

    def test_failed_voice_keeps_previous_site_and_date(self):
        with tempfile.TemporaryDirectory() as root:
            site = Path(root)/'site'
            site.mkdir()
            (site/'index.html').write_text('previous edition: 2026-10-10')
            (site/'latest.mp3').write_bytes(b'previous audio')
            edition_path = Path(root)/'edition.json'
            edition_path.write_text(json.dumps(self.edition,ensure_ascii=False),encoding='utf-8')
            async def fail_voice(*args):
                raise RuntimeError('simulated voice outage')
            with patch.object(build_radio, 'synthesize', fail_voice):
                with self.assertRaises(RuntimeError):
                    build_radio.build(edition_path, site)
            self.assertEqual((site/'index.html').read_text(),'previous edition: 2026-10-10')
            self.assertEqual((site/'latest.mp3').read_bytes(), b'previous audio')
            self.assertEqual(sorted(p.name for p in site.iterdir()),['index.html', 'latest.mp3'])

    def test_automation_audio_follows_new_edition_and_keeps_archive(self):
        async def fake_voice(text, output):
            output.write_bytes(text.encode('utf-8'))
            return 'zh-CN-YunyangNeural'

        def fake_speed(source, output):
            output.write_bytes(b'1.3x ' + source.read_bytes())
            return 46.2

        with tempfile.TemporaryDirectory() as root:
            site = Path(root) / 'site'
            edition_path = Path(root) / 'edition.json'
            older = deepcopy(self.edition)
            older['date'] = '2026-10-10'
            older['intro'] = '上一期的开场。'
            edition_path.write_text(json.dumps(older), encoding='utf-8')
            metadata = SimpleNamespace(info=SimpleNamespace(length=60))
            with patch.object(build_radio, 'synthesize', fake_voice), patch('mutagen.mp3.MP3', return_value=metadata), patch.object(build_radio, 'speed_audio', fake_speed):
                build_radio.build(edition_path, site)
                previous_audio = json.loads((site / 'episodes.json').read_text(encoding='utf-8'))[0]['audio']
                previous_audio = (site / previous_audio).read_bytes()
                edition_path.write_text(json.dumps(self.edition), encoding='utf-8')
                build_radio.build(edition_path, site)
            history = json.loads((site / 'episodes.json').read_text(encoding='utf-8'))
            self.assertEqual(history[0]['date'], '2026-10-11')
            self.assertEqual((site / 'latest.mp3').read_bytes(), b'1.3x ' + (site / history[0]['audio']).read_bytes())
            self.assertNotEqual((site / 'latest.mp3').read_bytes(), b'1.3x ' + previous_audio)
            self.assertEqual((site / history[1]['audio']).read_bytes(), previous_audio)
            automation = json.loads((site / 'automation.json').read_text(encoding='utf-8'))
            self.assertEqual(automation['date'], history[0]['date'])
            self.assertEqual(automation['speed'], 1.3)
            import feedparser
            feed = feedparser.parse((site / 'podcast.xml').read_bytes())
            self.assertFalse(feed.bozo)
            self.assertEqual(len(feed.entries), 2)
            self.assertIn('2026-10-11', feed.entries[0].title)
            self.assertNotEqual(feed.entries[0].id, feed.entries[1].id)
            self.assertNotEqual(feed.entries[0].enclosures[0].href, feed.entries[1].enclosures[0].href)
            for entry, episode in zip(feed.entries, history):
                enclosure = entry.enclosures[0]
                self.assertEqual(enclosure.href, build_radio.SITE_URL + episode['audio'])
                self.assertEqual(entry.itunes_duration, str(round(episode['duration_seconds'])))
                self.assertIn('1倍原速', entry.title)
                self.assertEqual(int(enclosure.length), (site / episode['podcast_audio']).stat().st_size)
            with patch('mutagen.mp3.MP3', return_value=metadata), patch.object(build_radio, 'speed_audio', fake_speed):
                build_radio.build(edition_path, site)
            rebuilt = feedparser.parse((site / 'podcast.xml').read_bytes())
            self.assertEqual([(e.id, e.published, e.enclosures[0].href) for e in rebuilt.entries],
                             [(e.id, e.published, e.enclosures[0].href) for e in feed.entries])
            self.assertTrue((site / 'shortcuts.html').exists())

    def test_actual_audio_is_complete_at_1_3_speed(self):
        import imageio_ffmpeg
        from mutagen.mp3 import MP3
        with tempfile.TemporaryDirectory() as root:
            source, output = Path(root) / 'source.mp3', Path(root) / 'fast.mp3'
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-loglevel', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=6', '-c:a', 'libmp3lame', str(source)], check=True, capture_output=True)
            seconds = build_radio.speed_audio(source, output)
            self.assertAlmostEqual(seconds, MP3(source).info.length / 1.3, delta=0.12)

    def test_failed_speed_conversion_keeps_previous_automation(self):
        with tempfile.TemporaryDirectory() as root:
            site, edition_path = Path(root) / 'site', Path(root) / 'edition.json'
            site.mkdir()
            (site / 'latest.mp3').write_bytes(b'previous fast audio')
            (site / 'index.html').write_text('previous page')
            (site / 'podcast.xml').write_text('previous feed')
            edition_path.write_text(json.dumps(self.edition), encoding='utf-8')
            async def fake_voice(text, output):
                output.write_bytes(b'new audio')
                return 'zh-CN-YunyangNeural'
            metadata = SimpleNamespace(info=SimpleNamespace(length=60))
            with patch.object(build_radio, 'synthesize', fake_voice), patch('mutagen.mp3.MP3', return_value=metadata), patch.object(build_radio, 'speed_audio', side_effect=RuntimeError('conversion failed')):
                with self.assertRaises(RuntimeError):
                    build_radio.build(edition_path, site)
            self.assertEqual((site / 'latest.mp3').read_bytes(), b'previous fast audio')
            self.assertEqual((site / 'index.html').read_text(), 'previous page')
            self.assertEqual((site / 'podcast.xml').read_text(), 'previous feed')

    def make_evidence_fixture(self, number='195'):
        sources, items = [], []
        buckets=['A股与政策','A股与公司公告','芯片与硬件','芯片与硬件','AI与科技前沿']
        for i, bucket in enumerate(buckets):
            sources.append({'id':str(i),'title':'业绩披露','body':'Company revenue is 195 trillion Korean won. Operating profit estimate is 107.40 trillion Korean won. Compact desktops arrive in November 2026.','publisher':str(i),'published':'2026-10-08','bucket':bucket,'url':'https://www.csrc.gov.cn/example'})
            items.append({'source_id':str(i),'title':'测试公告'+str(i),'facts':f'公司于10月8日披露估计销售额为{number}万亿韩元，合并营业利润约107.40万亿韩元，同时计划11月发售相关产品，仍需后续公告确认具体安排。','analysis':'分析：若经营计划落地，可能改变供应链产能分配，但具体订单金额和交付节奏需要后续公司披露进一步核实。','chain':'相关产业环节以公司实际披露为准。','risk':'风险：正式业绩和交付时间仍有不确定性，需跟踪后续公告，不能单凭估计数字确认现金流或个股投资价值。','evidence':['Company revenue is 195 trillion Korean won.']})
        return sources, {'items':items,'intro':'本期导语','coverage':'资料边界','outro':'继续核实'}

    def test_exact_numeric_value_not_substring(self):
        sources,draft=self.make_evidence_fixture('19')
        with self.assertRaisesRegex(ValueError,'numeric fact unsupported'):
            auto_news.evidence_validate(draft,sources,date(2026,10,11))

    def test_original_publication_date_and_english_month_translation(self):
        sources,draft=self.make_evidence_fixture()
        validated=auto_news.evidence_validate(draft,sources,date(2026,10,11))
        self.assertEqual(validated['items'][0]['published'],'2026-10-08')

    def test_invented_evidence_rejected(self):
        sources=[]
        draft={'items':[],'intro':'导语','coverage':'覆盖','outro':'结尾'}
        for i, bucket in enumerate(['A股与政策','A股与公司公告','芯片与硬件','AI与科技前沿','AI与科技前沿']):
            sources.append({'id':str(i),'title':'测试','body':'已读取的官方原文证据内容，未包含任何虚构的公司数据。','publisher':str(i),'published':'2026-10-10','bucket':bucket,'url':'https://www.csrc.gov.cn/example'})
            draft['items'].append({'source_id':str(i),'title':'测试'+str(i),'facts':'这是对应官方原文的事实概括。'*8,'analysis':'分析需要区分商业模式和实际订单。'*5,'chain':'相关产业链应当通过公司公告核实。','risk':'风险来自商业落地的不确定性，需要继续核对。'*4,'evidence':['这段证据没有出现在官方原文正文里。']})
        with self.assertRaisesRegex(ValueError, 'evidence'):
            auto_news.evidence_validate(draft, sources, date(2026,10,11))


if __name__ == '__main__':
    unittest.main()
