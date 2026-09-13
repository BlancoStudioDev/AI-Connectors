#!/usr/bin/env python3
"""Crea lo Short con ffmpeg: TTS italiano + immagini Wikimedia (Ken Burns)
+ sottotitoli sincronizzati colorati + musica CC.
Input:  <outdir>/script.json   Output: <outdir>/video.mp4
"""
import argparse, asyncio, json, math, random, re, shutil, subprocess, sys, time
import urllib.parse, urllib.request
from pathlib import Path

import edge_tts

ROOT = Path(__file__).parent
FFMPEG = Path.home() / 'agent-scripts' / 'bin' / 'ffmpeg'
FFPROBE = Path.home() / 'agent-scripts' / 'bin' / 'ffprobe'
MUSIC = ROOT / 'assets' / 'music'
CACHE = ROOT / 'data' / 'imgcache'
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
W, H, FPS = 1080, 1920, 30
UA = {'User-Agent': 'ShortsHistoryBot/1.0 (https://blancostudio.dev; contact: tommasogiorgio.bianco@gmail.com)'}


def http_get(url, timeout=60, tries=3):
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=timeout).read()
        except urllib.error.HTTPError as e:
            if e.code == 429 and a < tries - 1:
                time.sleep(3 * (a + 1))
                continue
            raise
    raise RuntimeError('http_get fallito')
VOICE = 'it-IT-DiegoNeural'


def log(m):
    print(f'[video {time.strftime("%H:%M:%S")}] {m}', flush=True)


def sh(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f'cmd fallito: {" ".join(map(str, cmd[:8]))}...\n{r.stderr[-600:]}')


def dur(f):
    r = subprocess.run([str(FFPROBE), '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'csv=p=0', str(f)], capture_output=True, text=True)
    return float(r.stdout.strip())


# ---------------------------------------------------------------- TTS
async def tts_scene(text, out_mp3, rate):
    tts = edge_tts.Communicate(text, VOICE, rate=rate, boundary='WordBoundary')
    audio, words = b'', []
    async for chunk in tts.stream():
        if chunk['type'] == 'WordBoundary':
            words.append({'w': chunk['text'], 't': chunk['offset'] / 1e7,
                          'd': chunk['duration'] / 1e7})
        elif chunk['type'] == 'audio':
            audio += chunk['data']
    Path(out_mp3).write_bytes(audio)
    return words


# ---------------------------------------------------------------- immagini
def commons_images(query, n):
    params = {'action': 'query', 'format': 'json', 'generator': 'search',
              'gsrsearch': query, 'gsrnamespace': '6', 'gsrlimit': '12',
              'prop': 'imageinfo', 'iiprop': 'url|size|mime', 'iiurlwidth': '1400'}
    url = 'https://commons.wikimedia.org/w/api.php?' + urllib.parse.urlencode(params)
    try:
        data = json.loads(http_get(url, timeout=40))
        time.sleep(1.5)
    except Exception as e:
        log(f'commons err ({query}): {e}')
        return []
    out = []
    for p in (data.get('query', {}).get('pages', {}) or {}).values():
        ii = (p.get('imageinfo') or [{}])[0]
        if ii.get('mime') in ('image/jpeg', 'image/png') and ii.get('width', 0) >= 900:
            out.append({'title': p['title'], 'url': ii.get('thumburl') or ii.get('url')})
    random.shuffle(out)
    return out[:n]


def img_ok(path):
    """Scarta immagini con fascia bianca/grigia uniforme in alto e in basso
    (oggetti su sfondo bianco: male in formato verticale)."""
    try:
        from PIL import Image
        im = Image.open(path).convert('L')
        w, h = im.size
        strip_h = max(int(h * 0.08), 8)
        top = im.crop((0, 0, w, strip_h))
        bot = im.crop((0, h - strip_h, w, h))
        import PIL.ImageStat as S
        mt, mb = S.Stat(top).mean[0], S.Stat(bot).mean[0]
        return not (mt > 225 and mb > 225)
    except Exception:
        return True


def dl_image(url, dest):
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 30000:
        return dest
    try:
        data = http_get(url, timeout=60)
        time.sleep(1)
        dest.write_bytes(data)
        return dest
    except Exception as e:
        log(f'img err: {e}')
        return None


# ---------------------------------------------------------------- ken burns
def ken_burns(img, out_mp4, duration, zoom_in=True):
    frames = max(int(duration * FPS), 2)
    zexpr = 'min(1.0+0.0011*on/1.0,1.5)' if zoom_in else 'max(1.25-0.0011*on/1.0,1.0)'
    vf = (f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,"
          f"crop={W*2}:{H*2},"
          f"zoompan=z='{zexpr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
          f":d={frames}:s={W}x{H}:fps={FPS},"
          f"eq=saturation=1.12:contrast=1.04")
    sh([str(FFMPEG), '-y', '-loop', '1', '-i', str(img), '-vf', vf,
        '-t', f'{duration:.3f}', '-r', str(FPS), '-pix_fmt', 'yuv420p',
        '-preset', 'veryfast', '-c:v', 'libx264', str(out_mp4)])


def concat_with_xfade(clips, out_mp4, fade=0.5):
    """Concatena clip con dissolvenza incrociata."""
    if len(clips) == 1:
        shutil.copy(clips[0], out_mp4)
        return
    inputs, durs = [], []
    for c in clips:
        inputs += ['-i', str(c)]
        durs.append(dur(c))
    fc, offset, prev = [], 0.0, '[0:v]'
    for i in range(len(clips) - 1):
        outv = f'[vx{i}]' if i < len(clips) - 2 else '[vout]'
        offset += durs[i] - fade
        fc.append(f"{prev}[{i+1}:v]xfade=transition=fade:duration={fade}:offset={offset:.3f}{outv}")
        prev = f'[vx{i}]'
    sh([str(FFMPEG), '-y', *inputs, '-filter_complex', ';'.join(fc),
        '-map', '[vout]', '-r', str(FPS), '-pix_fmt', 'yuv420p',
        '-preset', 'veryfast', '-c:v', 'libx264', str(out_mp4)])


# ---------------------------------------------------------------- sottotitoli
def esc(t):
    return t.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')


def ts(t):
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f'{h}:{m:02d}:{s:05.2f}'


def build_ass(chunks, path):
    hdr = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,DejaVu Sans,74,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,1,0,1,5,2,2,60,60,620,1
Style: Gold,DejaVu Sans,78,&H0000D7FF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,1,0,1,5,2,2,60,60,620,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    prev_end = 0.0
    for c in chunks:
        st = max(c['start'], prev_end + 0.03)
        en = max(c['end'] + 0.12, st + 0.5)
        prev_end = en
        style = 'Gold' if c['hook'] else 'Base'
        lines.append(f"Dialogue: 0,{ts(st)},{ts(en)},{style},,0,0,0,,{esc(c['text'])}")
    Path(path).write_text(hdr + '\n'.join(lines) + '\n')


def chunk_words(words, scene_start, n_hook_chunks=1):
    """Raggruppa parole in sottotitoli da ~2-3 parole."""
    chunks, cur, idx = [], [], 0
    for w in words:
        cur.append(w)
        text = ' '.join(x['w'] for x in cur)
        gap = False
        idx += 1
        if len(cur) >= 3 or len(text) >= 20:
            gap = True
        if gap:
            chunks.append({'words': cur})
            cur = []
    if cur:
        chunks.append({'words': cur})
    out = []
    for i, c in enumerate(chunks):
        t0 = scene_start + c['words'][0]['t']
        t1 = scene_start + c['words'][-1]['t'] + c['words'][-1]['d']
        out.append({'text': ' '.join(x['w'] for x in c['words']),
                    'start': t0, 'end': t1, 'hook': i < n_hook_chunks})
    return out


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--outdir', required=True)
    args = ap.parse_args()
    outdir = Path(args.outdir)
    s = json.load(open(outdir / 'script.json'))
    scenes = s['scene']
    tmp = outdir / 'build'
    tmp.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)

    # 1. TTS per scena (rate adattivo per stare sotto i 58s totali)
    log('TTS...')
    gap_dur = 0.25
    tail = 0.7
    scene_d, scene_words, total = [], [], 0.0
    for rate in ('+8%', '+16%', '+25%'):
        scene_d, scene_words = [], []
        total = 0.0
        for i, sc in enumerate(scenes):
            words = asyncio.run(tts_scene(sc['testo'], tmp / f'v{i}.mp3', rate))
            d = dur(tmp / f'v{i}.mp3')
            scene_d.append(d)
            scene_words.append(words)
            total += d + (gap_dur if i < len(scenes) - 1 else tail)
        if total <= 57.5:
            break
        log(f'totale {total:.1f}s, riprovo a {rate}')
    log(f'durata totale: {total:.1f}s (rate {rate})')

    # 2. audio completo (voce + pause)
    for i in range(len(scenes)):
        sh([str(FFMPEG), '-y', '-i', str(tmp / f'v{i}.mp3'), '-af',
            f'apad=pad_dur={gap_dur if i < len(scenes)-1 else tail}', str(tmp / f'v{i}.wav')])
    starts, t = [], 0.0
    for i in range(len(scenes)):
        starts.append(t)
        t += scene_d[i] + (gap_dur if i < len(scenes) - 1 else tail)
    total = t
    log(f'durata totale: {total:.1f}s')
    concat_list = tmp / 'audio_list.txt'
    concat_list.write_text(''.join(f"file 'v{i}.wav'\n" for i in range(len(scenes))))
    sh([str(FFMPEG), '-y', '-f', 'concat', '-safe', '0', '-i', str(concat_list),
        '-c:a', 'pcm_s16le', str(tmp / 'voice.wav')])

    # 3. immagini: 2-3 per scena, con pool di riserva
    log('immagini...')
    shots = []
    pool = []  # immagini avanzate da altre scene

    def pick(n):
        got = []
        while pool and len(got) < n:
            got.append(pool.pop(0))
        return got

    for i, sc in enumerate(scenes):
        sd = scene_d[i] + (gap_dur if i < len(scenes) - 1 else tail)
        found = commons_images(sc['ricerca'], 6)
        if len(found) < 2:
            found += commons_images(' '.join(sc['ricerca'].split()[:2]), 6)
        chosen = found[:min(3, len(found))]
        if len(chosen) < 2:
            chosen += pick(2 - len(chosen))
        scene_shots = []
        tried = 0
        while len(scene_shots) < 2 and tried < len(chosen) + 3:
            if tried >= len(chosen):
                extra = pick(1)
                if not extra:
                    break
                chosen.append(extra[0])
            im = chosen[tried]
            tried += 1
            img = dl_image(im['url'], CACHE / (re.sub(r'\W+', '_', im['title'])[:80] + '.jpg'))
            if img and img_ok(img):
                scene_shots.append(img)
            elif img:
                log('img scartata (sfondo bianco o corrotta)')
        if not scene_shots:
            raise RuntimeError(f'nessuna immagine utilizzabile per la scena {i}')
        per = sd / len(scene_shots)
        for img in scene_shots:
            shots.append((img, per))
        pool += found[min(3, len(found)):]  # avanzate nel pool
    log(f'{len(shots)} immagini')

    # 4. ken burns + concat
    log('ken burns...')
    for idx, (img, d) in enumerate(shots):
        ken_burns(img, tmp / f'kb{idx:03d}.mp4', d + 0.5, zoom_in=(idx % 2 == 0))
    log('concat con dissolvenze...')
    clips = [tmp / f'kb{i:03d}.mp4' for i in range(len(shots))]
    concat_with_xfade(clips, tmp / 'visual.mp4', fade=0.5)

    # 5. sottotitoli
    log('sottotitoli...')
    chunks = []
    for i in range(len(scenes)):
        chunks += chunk_words(scene_words[i], starts[i], n_hook_chunks=1)
    build_ass(chunks, tmp / 'subs.ass')

    # 6. montaggio finale: sottotitoli + voce + musica
    log('montaggio finale...')
    track = random.choice([p for p in MUSIC.glob('*.mp3')])
    music_credit = track.stem
    fade_st = max(total - 2.5, 0)
    af = (f"[1:a]volume=1.06[voice];"
          f"[2:a]volume=0.14,afade=t=out:st={fade_st:.2f}:d=2.5[mus];"
          f"[voice][mus]amix=inputs=2:duration=first:dropout_transition=3,"
          f"alimiter=limit=0.95[a]")
    sh([str(FFMPEG), '-y', '-i', str(tmp / 'visual.mp4'),
        '-i', str(tmp / 'voice.wav'), '-stream_loop', '-1', '-i', str(track),
        '-filter_complex', af, '-map', '0:v', '-map', '[a]',
        '-vf', f"subtitles={tmp}/subs.ass",
        '-t', f'{total:.2f}', '-c:v', 'libx264', '-preset', 'veryfast',
        '-crf', '21', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k',
        str(outdir / 'video.mp4')], cwd=str(tmp))
    # ffmpeg subs path con cartelle: usa cwd per il path relativo
    (outdir / 'video.mp4').exists() or (_ for _ in ()).throw(RuntimeError('video non creato'))
    log(f'OK: {outdir}/video.mp4 ({(outdir / "video.mp4").stat().st_size // 1024} KB)')
    s['music_credit'] = music_credit
    (outdir / 'script.json').write_text(json.dumps(s, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
