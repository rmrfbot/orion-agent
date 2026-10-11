/* Runs through page.evaluate with {start, interval_ms}; all waits stay in-page. */
async ({start = false, interval_ms = 350, verify = true} = {}) => {
  const began = performance.now();
  const video = document.querySelector('video');
  const adPlaying = () => !!document.querySelector('.html5-video-player.ad-showing');
  const skipMetrics = () => window.__orionSkipWatcher?.snapshot?.() ||
    {enabled: false, skip_available: false, samples: []};
  if (!video) return {playing: false, state: 'opened', video_present: false,
    ad_playing: adPlaying(), verification_ms: performance.now() - began, skip_metrics: skipMetrics()};
  let reason = null;
  // Never toggle the player. A pending play promise must not block task completion.
  let playTimeout;
  if (start && video.paused && !video.ended && !video.error) {
    try {
      await Promise.race([
        video.play(),
        new Promise((_, reject) => {
          playTimeout = setTimeout(() => reject(new Error('Playback request is still pending')), 500);
        })
      ]);
    } catch (error) { reason = String(error); }
    finally { clearTimeout(playTimeout); }
  }
  const position = video.currentTime;
  const source = video.currentSrc;
  const adBefore = adPlaying();
  const sampledAt = performance.now();
  // A short bounded observation checks progress; paused/error/loading states return immediately.
  if (verify && !video.paused && !video.ended && !video.error && video.readyState >= 2) {
    await new Promise(resolve => setTimeout(resolve, Math.max(200, Math.min(1000, interval_ms))));
  }
  const advance = video.currentTime - position;
  const sameVideo = video.isConnected && video === document.querySelector('video') &&
    video.currentSrc === source && adBefore === adPlaying();
  const advancing = verify && sameVideo && !video.seeking && advance > 0.02;
  let playback;
  if (video.error) playback = 'error';
  else if (video.ended) playback = 'ended';
  else if (video.readyState < 2) playback = 'loading';
  else if (video.paused) playback = 'paused';
  else if (!verify) playback = 'unverified';
  else if (advancing) playback = 'playing';
  else playback = 'buffering';
  const ad = adPlaying();
  return {video_present: true, playing: playback === 'playing',
    state: ad && playback !== 'error' ? 'advertisement' : playback,
    playback_state: playback, ad_playing: ad, paused: video.paused,
    ready_state: video.readyState, current_time: video.currentTime,
    advanced_seconds: advance, progress_verified: advancing,
    observation_ms: performance.now() - sampledAt,
    verification_ms: performance.now() - began,
    skip_metrics: skipMetrics(),
    ...(video.error ? {error: {code: video.error.code, message: video.error.message}} : {}),
    reason};
}
