#!/usr/bin/env python3
"""YouTube Studio: login (sessione persistente) + upload del video come Short.
Input:  <outdir>/video.mp4 + <outdir>/script.json
"""
import argparse, json, os, re, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent
PROFILE = ROOT / 'sessions' / 'youtube'
SHOTS = ROOT / 'data' / 'logs' / 'shots' / 'youtube'
SHOTS.mkdir(parents=True, exist_ok=True)


def log(m):
    print(f'[youtube {time.strftime("%H:%M:%S")}] {m}', flush=True)


def shot(page, name):
    try:
        page.screenshot(path=str(SHOTS / f'{name}.png'))
    except Exception:
        pass


def click_first(page, selectors, timeout=6000):
    for sel in selectors:
        try:
            loc = page.locator(sel)
            for i in range(loc.count()):
                el = loc.nth(i)
                try:
                    if el.is_visible(timeout=timeout // max(loc.count(), 1)):
                        el.click(timeout=timeout)
                        log(f'click: {sel}[{i}]')
                        return True
                except Exception:
                    continue
        except Exception:
            continue
    return False


def google_login(page, cfg):
    log('login Google...')
    shot(page, 'yt_login_0')
    page.fill('#identifierId', cfg['youtube_email'])
    page.keyboard.press('Enter')
    time.sleep(6)
    page.wait_for_selector('input[type="password"]:visible', timeout=30000)
    page.fill('input[type="password"]', cfg['youtube_password'])
    page.keyboard.press('Enter')
    # eventuale 2FA: attende max 10 min
    log('attesa eventuale 2FA (max 10 min)...')
    for _ in range(150):
        time.sleep(4)
        try:
            u = page.url
        except Exception:
            break
        if 'accounts.google' not in u or 'myaccount' in u:
            break


def ensure_studio(page, cfg):
    page.goto('https://studio.youtube.com/', wait_until='domcontentloaded', timeout=60000)
    time.sleep(6)
    # cookie consent
    click_first(page, [
        'button:has-text("Accetta tutto")', 'button:has-text("Accept all")',
        'button[aria-label*="Accetta"]',
    ], timeout=5000)
    for _ in range(3):
        if 'studio.youtube.com' in page.url:
            break
        if 'accounts.google.com' in page.url:
            google_login(page, cfg)
            page.goto('https://studio.youtube.com/', wait_until='domcontentloaded',
                      timeout=60000)
            time.sleep(10)
        else:
            time.sleep(6)
    if 'studio.youtube.com' not in page.url:
        shot(page, 'yt_studio_fail')
        raise RuntimeError('impossibile raggiungere YouTube Studio')
    log('dentro YouTube Studio')


def set_text(page, root_sel, text):
    loc = page.locator(root_sel).first
    loc.click()
    time.sleep(1)
    page.keyboard.press('Control+A')
    page.keyboard.press('Delete')
    page.keyboard.insert_text(text)
    time.sleep(1)


def upload(page, outdir, private=False):
    outdir = Path(outdir)
    video = outdir / 'video.mp4'
    s = json.load(open(outdir / 'script.json'))
    title = ('[TEST] ' if private else '') + s['yt_title'][:88]
    tags = ' '.join(s.get('hashtags', ['#Shorts'])[:5])
    desc = s['yt_description'].strip()
    if '#Shorts' not in desc and tags:
        desc = desc + '\n\n' + tags
    credit = (f"\n\n🎬 Immagini: Wikimedia Commons\n🎵 Musica: "
              f"\"{s.get('music_credit', '')}\" — Kevin MacLeod (incompetech.com), CC BY 4.0")
    desc = desc + credit
    log(f'upload: {title!r}')

    if not click_first(page, [
        '#create-icon', 'button[aria-label*="Crea"]', 'button[aria-label*="Create"]',
    ], timeout=20000):
        shot(page, 'no_create_btn')
        raise RuntimeError('bottone Crea non trovato')
    time.sleep(2)
    shot(page, 'menu_create')
    if not click_first(page, [
        'tp-yt-paper-item:has-text("Carica video")',
        'tp-yt-paper-item:has-text("Upload videos")',
    ], timeout=10000):
        raise RuntimeError('voce Carica video non trovata')
    time.sleep(3)
    page.set_input_files('input[type="file"]', str(video))
    log('file in upload')
    time.sleep(10)
    shot(page, 'upload_dialog')
    # id dal campo "Link video" del dialogo
    vid = 'sconosciuto'
    try:
        link_txt = page.locator(
            'text=/youtube\\.com\\/(shorts\\/|watch\\?v=)[\\w-]+/').first.inner_text(timeout=8000)
        m = re.search(r'(?:shorts/|watch\?v=)([\w-]{6,})', link_txt)
        if m:
            vid = m.group(1)
            log(f'id video: {vid}')
    except Exception:
        pass

    # dettagli: titolo + descrizione
    for sel in ['#title-textarea #textbox', 'ytcp-social-suggestions-textbox#title #textbox',
                'input[aria-label*="Titolo"]', 'input[aria-label*="Title"]']:
        try:
            if page.locator(sel).first.is_visible(timeout=5000):
                set_text(page, sel, title)
                break
        except Exception:
            continue
    for sel in ['#description-textarea #textbox', 'ytcp-video-description #textbox',
                '#description-wrapper #textbox']:
        try:
            if page.locator(sel).first.is_visible(timeout=5000):
                set_text(page, sel, desc)
                break
        except Exception:
            continue
    shot(page, 'dettagli')

    # pubblico target: no, non fatto per bambini
    click_first(page, [
        'tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]',
    ], timeout=10000)

    # 3 volte Avanti
    for i in range(3):
        time.sleep(2)
        if not click_first(page, ['ytcp-button#next-button'], timeout=12000):
            shot(page, f'next_fallito_{i}')
            break
    time.sleep(3)
    shot(page, 'visibilita')
    # visibilità: privata (test) o pubblica
    if private:
        click_first(page, ['tp-yt-paper-radio-button[name="PRIVATE"]'], timeout=10000)
    else:
        click_first(page, ['tp-yt-paper-radio-button[name="PUBLIC"]'], timeout=10000)
    time.sleep(2)
    # potrebbero esserci controlli (copyright/AdSuitability): vai avanti se serve
    click_first(page, ['ytcp-button#next-button'], timeout=3000)
    if not click_first(page, ['ytcp-button#done-button'], timeout=12000):
        shot(page, 'publish_fallito')
        raise RuntimeError('bottone Pubblica/Salva non trovato')
    log('pubblicazione avviata')
    # attesa chiusura dialogo di upload (il titolo contiene #Shorts: non usarlo come match)
    for _ in range(60):
        time.sleep(4)
        try:
            if page.locator('ytcp-video-upload-dialog').count() == 0:
                break
        except Exception:
            break
    shot(page, 'pubblicato')
    if vid == 'sconosciuto':
        # fallback: cerca il video nell'elenco contenuti
        try:
            page.goto('https://studio.youtube.com/channel/UC/videos',
                      wait_until='domcontentloaded', timeout=60000)
            time.sleep(10)
            rows = page.locator('ytcp-video-row')
            for i in range(rows.count()):
                r = rows.nth(i)
                txt = r.inner_text(timeout=1500)
                if title[:20] in txt:
                    a = r.locator('a').first
                    href = a.get_attribute('href') if a.count() else ''
                    m = re.search(r'(?:video_id=|shorts/|v=)([\w-]{6,})', href or '')
                    if m:
                        vid = m.group(1)
                    break
        except Exception as e:
            log('recupero id err: ' + str(e)[:100])
    log(f'pubblicato OK (id: {vid})')
    return vid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--outdir', required=True)
    ap.add_argument('--private', action='store_true',
                    help='upload in visibilità privata (per test)')
    args = ap.parse_args()
    if not os.environ.get('DISPLAY'):
        os.environ['DISPLAY'] = ':99'
    cfg = json.load(open(ROOT / 'config.json'))
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE), headless=False, locale='it-IT',
            viewport={'width': 1366, 'height': 850},
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox',
                  '--disable-dev-shm-usage'])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(30000)
        ensure_studio(page, cfg)
        vid = upload(page, args.outdir, private=args.private)
        ctx.close()
        print(f'UPLOAD OK https://youtube.com/shorts/{vid}')


if __name__ == '__main__':
    main()
