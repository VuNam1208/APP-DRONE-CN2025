from pathlib import Path
import json
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'results/reference_refresh_20261018'
SOURCES = {
    'Fevgas2022': '10.3390/s22031235',
    'Kumar2023': '10.1016/j.phycom.2023.102073',
    'PathSurvey2025': '10.3390/drones9040263',
    'Datsko2024': '10.1109/LRA.2024.3358581',
    'Guven2024': '10.1016/j.adhoc.2024.103520',
    'Gao2024': '10.1007/s11768-024-00202-0',
    'AlqefariReview2025': '10.3390/drones9010075',
    'Wang2023': '10.1049/cim2.12090',
    'Luna2024': '10.1002/rob.22342',
    'Li2024': '10.2514/6.2024-2879',
    'AlqefariHybrid2025': '10.3390/s25082502',
    'Zhang2025': '10.1038/s41598-025-89787-3',
    'Barnawi2025': '10.70322/dav.2025.10016',
    'WangReview2024': '10.3390/pr12061272',
    'Jiang2023': '10.1007/s42405-023-00629-w',
}
OUT.mkdir(parents=True, exist_ok=True)
records = {}
for key, doi in SOURCES.items():
    url = 'https://api.crossref.org/works/' + urllib.parse.quote(doi, safe='')
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'ArticleReferenceAudit/1.0'})
            with urllib.request.urlopen(req, timeout=40) as response:
                records[key] = json.load(response)['message']
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)
    print(key, records[key]['title'][0], flush=True)
    (OUT / 'crossref_metadata.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
print('Verified records:', len(records))
