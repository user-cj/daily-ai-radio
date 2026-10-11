(() => {
  const audio = document.getElementById('radio');
  document.getElementById('speed').addEventListener('change', e => { audio.playbackRate = Number(e.target.value); });
  const day = document.getElementById('episode-date').textContent.trim();
  const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date());
  const state = document.getElementById('freshness');
  if (day !== today) state.textContent = `本期是 ${day}，尚未更新至今天。`;
  else state.textContent = '本期日期为今天（北京时间）';
  fetch('status.json', { cache: 'no-store' }).then(r => r.ok ? r.json() : null).then(s => {
    if (s && !s.ok) state.textContent = `最近一次更新未完成，继续收听 ${day}。`;
  }).catch(() => {});
  if ('mediaSession' in navigator) {
    navigator.mediaSession.metadata = new MediaMetadata({ title: `${day} · AI财经广播`, artist: '硬件学长', album: '每日五条' });
    for (const [action, handler] of Object.entries({ play: () => audio.play(), pause: () => audio.pause(), seekbackward: () => { audio.currentTime = Math.max(0, audio.currentTime - 15); }, seekforward: () => { if (Number.isFinite(audio.duration)) audio.currentTime = Math.min(audio.duration, audio.currentTime + 15); } })) {
      try { navigator.mediaSession.setActionHandler(action, handler); } catch (_) {}
    }
  }
})();
