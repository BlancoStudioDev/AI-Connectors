#!/usr/bin/env python3
"""Genera lo script di uno YouTube Short storico (stile 'Cultura Antica') con DeepSeek.
Temi sempre diversi: lo stato dei temi gia' usati e' in data/state.json.
Output: <outdir>/script.json
"""
import argparse, json, random, sys
from pathlib import Path
import urllib.request

ROOT = Path(__file__).parent
STATE = ROOT / 'data' / 'state.json'

CATEGORIE = [
    "Roma antica", "Grecia antica", "Egitto antico", "Mesopotamia",
    "Vichinghi", "Medioevo europeo", "Rinascimento", "Impero Ottomano",
    "Civiltà precolombiane (Maya, Aztechi, Inca)", "Cina antica",
    "Giappone feudale", "Persia antica", "Cartagine e Fenici",
    "Antico Testamento/epoca biblica", "Grecia ellenistica e Alessandro Magno",
    "Impero Romano d'Oriente/Bisanzio", "Celti e Galli", "Etruschi",
    "Sumeri e Babilonesi", "Mongoli", "Era vichinga e scoperte", "Tartari/Unni",
]
ANGOLI = [
    "un mistero ancora irrisolto", "una battaglia decisiva", "la vita quotidiana sorprendente",
    "un'invenzione in anticipo sui tempi", "una figura storica straordinaria",
    "un luogo spettacolare e la sua storia", "un'usanza strana ma vera",
    "una catastrofe o caduta spettacolare", "una leggenda fondata su fatti reali",
    "un segreto archeologico recente", "una curiosità che pochi conoscono",
    "un tradimento o una cospirazione storica",
]

SYSTEM = """Sei il ghostwriter del canale YouTube 'Cultura Antica', un canale italiano di storia antica con shorts virali.
Scrivi script per YouTube Shorts di massimo 60 secondi che:
- APRONO con un gancio (hook) shock nei primi 2-3 secondi ("Nel 79 d.C. nessuno sapeva che...", "Questo uomo è rimasto sepolto per 2000 anni e...")
- hanno un ritmo veloce, frasi brevi, numeri e dettagli concreti
- raccontano fatti storici VERI e verificabili (niente inventato), con 1-2 dati sorprendenti
- hanno un colpo di scena o rivelazione verso la fine
- CHIUDONO con una domanda provocatoria per i commenti (engagement) + invito a seguire il canale
- sono in ITALIANO, tono colto ma semplice, adatto a voce narrante maschile energica
La narrazione completa deve durare circa 50-55 secondi (circa 125-145 parole)."""


def http_json(url, payload, headers, timeout=120):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json', **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {'used_topics': []}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--outdir', required=True)
    out = Path(ap.parse_args().outdir)
    out.mkdir(parents=True, exist_ok=True)

    cfg = json.load(open(ROOT / 'config.json'))
    state = load_state()
    used = state.get('used_topics', [])[-60:]

    cat = random.choice(CATEGORIE)
    ang = random.choice(ANGOLI)

    user = f"""Scegli UN solo argomento storico nuovo e crea lo script completo dello short.

Vincoli:
- L'argomento DEVE appartenere a questa area: {cat}, con l'angolo: {ang}
- NON usare (o varianti troppo simili di) questi temi già trattati: {json.dumps(used, ensure_ascii=False)}
- Tutto in italiano.

Rispondi SOLO con JSON valido con queste chiavi:
{{
 "topic": "tema in 3-6 parole",
 "era": "epoca/civiltà",
 "hook": "gancio di apertura (la frase esatta con cui parte il video)",
 "scene": [
   {{"testo": "frase/i della narrazione di questa scena", "ricerca": "2-4 parole in INGLESE per cercare immagini storiche, es. 'Attila Hun army'"}}
 ],
 "on_screen_title": "titolo grande da mettere a schermo all'inizio (max 6 parole)",
 "yt_title": "titolo YouTube accattivante, max 90 caratteri, 1 emoji pertinente",
 "yt_description": "descrizione YouTube 2-4 frasi che riassume e incuriosisce, poi a capo elenca 5 hashtag pertinenti iniziando per #Shorts",
 "hashtags": ["#Shorts", "...4 altri hashtag"],
 "cta": "call to action finale detta a voce"
}}

REGOLE per "scene":
- da 5 a 7 scene che insieme formano la narrazione completa (concatenando i "testo" si deve ottenere la narrazione intera, hook iniziale e domanda+CTA finale inclusi)
- ogni scena: 1-2 frasi, 20-25 parole max
- ogni "ricerca" in inglese, precisa e visiva (dipinti, battaglie, monumenti, statue, manufatti)"""

    payload = {
        'model': cfg['deepseek_model'],
        'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': user}],
        'response_format': {'type': 'json_object'},
        'temperature': 1.1,
    }
    data = http_json(cfg['deepseek_base_url'].rstrip('/') + '/chat/completions', payload,
                     {'Authorization': 'Bearer ' + cfg['deepseek_api_key']})
    content = data['choices'][0]['message']['content']
    script = json.loads(content)

    scene = script.get('scene') or []
    if not (4 <= len(scene) <= 9):
        raise RuntimeError(f'scene non valide: {len(scene)}')
    script['narration'] = ' '.join(s['testo'].strip() for s in scene)
    for s in scene:
        if not s.get('ricerca'):
            s['ricerca'] = script['topic']

    words = len(script.get('narration', '').split())
    if words < 80 or not script.get('topic'):
        raise RuntimeError(f'narrazione troppo corta o JSON incompleto ({words} parole)')

    prompt_invideo = f"""Crea un video verticale in formato 9:16, durata 50-55 secondi, in LINGUA ITALIANA, pensato per YouTube Shorts.
Voce narrante: maschile italiana, energica e coinvolgente.
Stile visivo: ricostruzioni cinematiche epiche dell'epoca {script.get('era', 'antica')}, colori caldi e realistici, movimenti di camera dinamici, transizioni rapide, dettagli storici accurati.
Sottotitoli: grandi, bianchi con bordo nero, in italiano, sempre visibili.
Musica: epica/misteriosa a basso volume.
Titolo grande a schermo all'inizio: "{script.get('on_screen_title', '')}".
Testo ESATTO della voce narrante da usare:
"{script['narration']}" """

    script['invideo_prompt'] = prompt_invideo
    script['narration_words'] = words
    (out / 'script.json').write_text(json.dumps(script, ensure_ascii=False, indent=2))
    (out / 'invideo_prompt.txt').write_text(prompt_invideo)

    used.append(script['topic'])
    state['used_topics'] = used
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    print(f'SCRIPT OK: {script["topic"]} ({words} parole) -> {out / "script.json"}')


if __name__ == '__main__':
    main()
