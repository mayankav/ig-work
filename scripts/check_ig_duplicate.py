#!/usr/bin/env python3
import os, requests, sys
tok = os.getenv('IG_ACCESS_TOKEN','')
uid = os.getenv('IG_USER_ID','')
h1 = os.getenv('H1','')
if not tok or not uid or not h1:
    print("IG duplicate check skipped: missing env")
    sys.exit(0)
base = 'https://graph.instagram.com/v21.0' if tok.startswith('IGAAP') else 'https://graph.facebook.com/v20.0'
try:
    r = requests.get(f'{base}/{uid}/media', params={'access_token': tok, 'fields': 'caption', 'limit': 10}, timeout=15)
    if r.status_code == 200:
        for item in r.json().get('data', []):
            if h1.strip('"')[:30] in (item.get('caption') or ''):
                print('Duplicate caption found on IG recent media — aborting')
                sys.exit(1)
except SystemExit:
    raise
except Exception as e:
    print(f'IG duplicate check skipped: {e}')
    sys.exit(0)
