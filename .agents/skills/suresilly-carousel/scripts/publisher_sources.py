"""Public, publisher-hosted book excerpts selected by a person, never a model.

The catalogue still proves the book and its subject. This transport adds a
public excerpt when a lending archive cannot supply text. Reviews retain short
exact passages, their original URL and the fetched document hash.
"""
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.parse
import requests

REGISTRY = Path(__file__).resolve().parents[1] / 'references/publisher_sources.json'
VERSION = 'publisher-excerpt-control-1'


def entries():
    return json.loads(REGISTRY.read_text())['sources']


def identity(entry, book):
    return all(entry['book'][key] == book[key] for key in ('work_key', 'author', 'title', 'year'))


def excerpt(document):
    class Extract(HTMLParser):
        def __init__(self):
            super().__init__(); self.depth=0; self.done=False; self.parts=[]
        def handle_starttag(self,tag,attrs):
            if self.done: return
            if tag=='div':
                if self.depth: self.depth+=1
                elif 'book-detail-excerpt' in dict(attrs).get('class','').split(): self.depth=1
        def handle_endtag(self,tag):
            if tag=='div' and self.depth:
                self.depth-=1
                if not self.depth: self.done=True
        def handle_data(self,data):
            if self.depth: self.parts.append(data)
    parser=Extract();parser.feed(document)
    if not parser.done: raise ValueError('Publisher excerpt is missing or incomplete')
    return re.sub(r'\s+', ' ', ' '.join(parser.parts)).strip()


def fetch(source_id, book):
    entry=entries()[source_id]
    if not identity(entry,book): raise ValueError('Publisher source belongs to another book')
    url=entry['url'];parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or parsed.netloc!='penguinrandomhousehighereducation.com' or parsed.path!='/book/' or parsed.query!='isbn='+entry['isbn']:
        raise ValueError('Publisher source URL is not allowed')
    response=requests.get(url,timeout=(5,25),allow_redirects=False)
    if response.status_code!=200: raise ValueError(f'Publisher excerpt returned HTTP {response.status_code}')
    if len(response.content)>2000000: raise ValueError('Publisher excerpt is too large')
    import bibliography
    heading=re.search(r'<h1\b[^>]*>(.*?)</h1>',response.text,re.I|re.S)
    title=bibliography._norm(html.unescape(re.sub('<[^>]+>',' ',heading.group(1)))) if heading else ''
    if bibliography._norm(book['title']) not in title or entry['isbn'] not in response.text:
        raise ValueError('Publisher page has a different book or edition')
    text=excerpt(response.text)
    # Only bounded exact quotations go into the permanent evidence record.
    if sum(len(p.split()) for p in entry['passages'])>25: raise ValueError('Source quote budget exceeded')
    if any(p not in text for p in entry['passages']): raise ValueError('Publisher passage changed or is absent')
    return {'kind':'publisher_excerpt','source_id':source_id,'work_key':book['work_key'],
            'document_sha256':hashlib.sha256(response.content).hexdigest(),
            'registry_sha256':hashlib.sha256(json.dumps(entry,sort_keys=True).encode()).hexdigest(),
            'passages':[{'text':p,'url':url,'locator':'Publisher excerpt'} for p in entry['passages']]}


def validate(source,book):
    entry=entries()[source['source_id']]
    if source.get('kind')!='publisher_excerpt' or not 1<=len(entry['passages'])<=4 or sum(len(p.split()) for p in entry['passages'])>25:
        raise ValueError('Invalid publisher evidence')
    if not identity(entry,book) or source['work_key']!=book['work_key']: raise ValueError('Publisher book identity changed')
    if source['registry_sha256']!=hashlib.sha256(json.dumps(entry,sort_keys=True).encode()).hexdigest(): raise ValueError('Publisher source definition changed')
    if not re.fullmatch('[0-9a-f]{64}',source['document_sha256']): raise ValueError('Missing fetched document hash')
    expected=[{'text':p,'url':entry['url'],'locator':'Publisher excerpt'} for p in entry['passages']]
    if source['passages']!=expected: raise ValueError('Publisher passages changed')
