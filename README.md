# 硬件学长 · AI财经广播

面向 iPhone Safari 的中文普通话男声电台。每日恰好五条，围绕 A股、芯片/电路/硬件和 AI 前沿；每条包含事实、分析、产业关联、风险、日期与原文。

本项目使用公开 GitHub 仓库、GitHub Actions、GitHub Pages、开放模型 Qwen2.5 7B 和 Edge TTS。无需付费模型 API 密钥。网页和音频公开可访问；“个人电台”不代表访问受限。

## 当前实现

- `episodes/2026-10-11.json`：首期人工编排的五条原文简报。
- `build_radio.py`：校验稿件，生成普通话男声 MP3，生成手机网页、文字稿和最近14期。
- `auto_news.py`：从证监会、工信部、巨潮资讯、英伟达、三星读取官方原文；RSS仅用于发现链接，无法读取正文则拒绝该条。文章日期不超过7日，稿中显示原日期。
- 暂时连接失败时有限重试；`source-cache.json`仅保留近期链接、标题和原始日期。即使目录站点暂时不可用，也会重新读取这些链接的正文；无法读到的原文仍不采用。
- 开放模型在 GitHub 运行机器内逐条编写中文稿；检查对应原文片段、各段数字、日期、重复句子、栏目覆盖，再次对照原文阅读事实和分析。再次阅读由同一个模型完成，**不等于独立交叉核验**，中文翻译和分析仍可能错误。自动稿标注“待人工复核”。
- 只保留完整事实句；业绩指引的分析使用合并与分部口径的保守编辑说明，不推断细分产品竞争力。硬件和AI风险段避免套用政策实施日期话术；风险观察项不是已发生事实。
- 若数据/模型/编辑校验/语音失败，保留上一期音频和真实日期，网页显示更新状态；流程返回失败，便于通过 GitHub 原生通知获知。
- 近期节目和状态提交到仓库保存；网页展示最近14期，超出展示窗口的节目仍可能存在于公开 Git 历史中。

## 上线

1. 将完整项目上传到公开仓库根目录，含 `.github/workflows/daily-radio.yml`。不要只上传ZIP。
2. GitHub 仓库 Settings → Pages → Source 选择 **GitHub Actions**。
3. Actions → **Daily AI radio** → Run workflow，检查 `build`、`deploy`、`update-result` 均成功。
4. 当前已上线并通过公开访问检查：[打开电台](https://user-cj.github.io/daily-ai-radio/)。
5. 首次打开点击播放；Safari 分享 → 添加到主屏幕。iPhone锁屏音频需要用户在真机验证，网页不自动播放。

随交付包提供 `publish.ps1`（双击 `Publish.cmd`），优先使用本机登录状态；缺少账号连接时启动 GitHub 官方登录。脚本核对目标仓库权限、同步主分支、完整上传、启用 Pages、手动运行并检查首次部署。不会强制覆盖远程分支，不索取或保存密码到项目。

手动运行时可勾选 `verify_automatic`，另外检查云端采集、自动编写五条、逐条复读和全新男声生成。检查节目保存在短期运行附件，公开页面保留当前编辑稿。队列中的发布任务从最新主分支开始，避免连续运行对旧版本状态产生冲突。

## 定时与通知

主任务 UTC 23:00（北京时间次日07:00）启动采集和编辑，为07:30左右节目做好准备；UTC 23:50（北京时间次日07:50）重试。当天已完成节目时不重复编写。免费运行机器排队、模型速度和语音网络都可能使发布时间晚于07:30。

GitHub公开仓库长期无活动可能停止定时运行，定时事件也可能延迟/丢弃。查看 Actions 是否启用；若停用，重新启用并手动运行。失败通知通过 GitHub Settings → Notifications → Actions，打开失败工作流通知。网站显示旧日期和失败状态，不虚构今日五条。

GitHub Pages在中国大陆网络的可用性需要实际测试。完整网页、稿件与MP3可下载后离线保存。没有免费稳定性或永久免费承诺。

## 本地运行

需要 Python 3.12 和联网。

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python build_radio.py --input episodes/2026-10-11.json
python -m http.server 8000 --directory site --bind 127.0.0.1
```

电脑访问 `http://127.0.0.1:8000/`。

自动采集可单独检查，不需要模型：

```powershell
python auto_news.py --collect-only --report work/source-report.json
```

自动编辑需要本机 Ollama 和 `qwen2.5:7b`。这是独立开放模型，无需使用任何聊天订阅的API额度。原文、模型结果、语音均可能出错，不能替代专业核查。默认使用免费的第三方 Edge TTS 接口，服务失效时自动尝试另一种男声，两者失败则保留旧节目。

## 编辑要求与资料边界

事实必须来自原文；计划、预告、征求意见、正式实施不能混为一谈。政策与下行风险优先，不推算未经披露的资金流、机构预测、订单、客户关系和目标价。海外厂商业绩不能直接说明A股公司获益。资金净买入和全市场资金流必须分开。

自动采集对部分公告站点的防护、PDF格式和页面变动可能失败。默认不提供完整的A股行情、机构一致预期或所有公司公告覆盖；缺少的数据在稿件里明确列出，宁可留缺。当前版本是有原文证据的自动简报与首期编辑稿，不宣称全自动专业事实核验已经完成。

参考官方资料：
- https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- https://github.com/ollama/ollama
- https://docs.ollama.com/capabilities/structured-outputs
- https://github.com/rany2/edge-tts

原仓库的启动说明保留在 `README.original.md`。
