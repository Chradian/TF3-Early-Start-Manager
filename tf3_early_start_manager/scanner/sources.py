"""Read-only helpers for installed TF3 content sources."""
from __future__ import annotations
import json
from pathlib import Path

def mod_namespace(mod_root:Path)->str:
    p=mod_root/'mod.json'
    if not p.is_file(): return ''
    try:data=json.loads(p.read_text(encoding='utf-8'))
    except (OSError,json.JSONDecodeError,UnicodeError): return ''
    v=data.get('modId'); return v.strip() if isinstance(v,str) else ''

def metadata_candidates(mod_root:Path):
    return (mod_root/'_metadata'/'modinfo.json',mod_root/'modinfo.json',mod_root/'mod.json')
