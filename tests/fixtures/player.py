"""Local player with real HTMLVideoElement audio playback and controlled ad DOM."""
import base64
import io
import wave
from functools import lru_cache


@lru_cache(maxsize=1)
def player_html():
    audio = io.BytesIO()
    with wave.open(audio, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b'\0\0' * 8000 * 60)
    encoded = base64.b64encode(audio.getvalue()).decode('ascii')
    return '''<!doctype html><html><head><title>Local YouTube fixture</title>
      <style>.fixture-hidden { display:none }</style></head><body>
      <input type="search" placeholder="Search">
      <a id="video-title" href="/watch?v=abcdefghijk" title="Fixture video">Fixture video</a>
      <div id="movie_player" class="html5-video-player">
        <video muted autoplay loop src="data:audio/wav;base64,''' + encoded + '''"></video>
        <div id="controls"></div>
      </div>
      <script>
      window.runSkipTrial = ({mode = 'enable', delay = 10}) => new Promise(resolve => {
        const player = document.querySelector('#movie_player');
        player.classList.add('ad-showing');
        const button = document.createElement('button');
        button.className = 'ytp-ad-skip-button';
        button.dataset.trial = String(window.trialCounter = (window.trialCounter || 0) + 1);
        button.textContent = 'Skip Ad';
        if (mode === 'enable') button.disabled = true;
        if (mode === 'aria') button.setAttribute('aria-disabled', 'true');
        if (mode === 'stylesheet') button.classList.add('fixture-hidden');
        let readyAt, clickedAt, early = false;
        const createdAt = performance.now();
        button.onclick = () => {
          clickedAt = performance.now();
          early = readyAt === undefined;
          setTimeout(() => {
            button.remove();
            player.classList.remove('ad-showing');
            resolve({ready_at_ms: readyAt, clicked_at_ms: clickedAt, early,
              eligibility_wait_ms: readyAt - createdAt,
              eligible_to_click_ms: clickedAt - readyAt,
              confirmation_ms: performance.now() - clickedAt});
          }, 5);
        };
        if (mode !== 'insert') document.querySelector('#controls').append(button);
        setTimeout(() => {
          readyAt = performance.now();
          if (mode === 'insert') document.querySelector('#controls').append(button);
          if (mode === 'enable') button.disabled = false;
          if (mode === 'aria') button.setAttribute('aria-disabled', 'false');
          if (mode === 'stylesheet') {
            // CSSOM update: intentionally produces no observed DOM mutation.
            document.styleSheets[0].insertRule('.fixture-hidden[data-trial="' + button.dataset.trial + '"] { display:block }',
              document.styleSheets[0].cssRules.length);
          }
        }, delay);
      });
      </script></body></html>'''


def fulfill_player(route):
    route.fulfill(content_type='text/html', body=player_html())
