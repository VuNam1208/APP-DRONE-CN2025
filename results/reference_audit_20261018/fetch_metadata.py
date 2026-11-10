"""Save publisher-deposited Crossref metadata for a reproducible reference audit."""

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def main():
    records = []
    output = Path(__file__).resolve().parent / 'crossref_metadata.json'
    if sys.argv[1:] == ['--retry-failed']:
        records = json.loads(output.read_text(encoding='utf-8'))['records']
        tasks = [(index, item['doi']) for index, item in enumerate(records, 1)
                 if 'error' in item]
    else:
        tasks = list(enumerate(sys.argv[1:], 1))
    for index, doi in tasks:
        url = 'https://api.crossref.org/works/' + urllib.parse.quote(doi, safe='')
        try:
            request = urllib.request.Request(url, headers={
                'User-Agent': 'APP-DRONE-ReferenceAudit/1.0',
                'Accept': 'application/json',
            })
            with urllib.request.urlopen(request, timeout=25) as response:
                metadata = json.load(response)['message']
            record = {'doi': doi, 'source': url, 'metadata': metadata}
            fields = {key: metadata.get(key) for key in (
                'title', 'container-title', 'volume', 'issue', 'page', 'article-number',
                'published-print', 'published-online', 'published', 'editor', 'publisher',
            )}
            fields['authors'] = [
                (author.get('given', '') + ' ' + author.get('family', '')).strip()
                for author in metadata.get('author', [])
            ]
            print(index, doi, json.dumps(fields, ensure_ascii=True), flush=True)
        except Exception as error:
            record = {'doi': doi, 'source': url, 'error': str(error)}
            print(index, doi, 'ERROR', ascii(str(error)), flush=True)
        if index <= len(records):
            records[index - 1] = record
        else:
            records.append(record)
        output.write_text(json.dumps({
            'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
            'records': records,
        }, indent=2, ensure_ascii=False), encoding='utf-8')
    return int(any('error' in record for record in records))


if __name__ == '__main__':
    raise SystemExit(main())
