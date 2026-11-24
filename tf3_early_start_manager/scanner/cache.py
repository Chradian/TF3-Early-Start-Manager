"""Persistent content-scan cache infrastructure."""
from __future__ import annotations
import json, logging, shutil
from pathlib import Path
from tf3_early_start_manager.models import Installation, Resource
LOGGER=logging.getLogger('tf3_early_start_manager')
SCAN_CACHE_SCHEMA_VERSION=25

class ScanCache:
    def __init__(self, app_root: Path, language: str, installation: Installation|None):
        self.app_root=Path(app_root); self.language=language; self.installation=installation
    @property
    def path(self)->Path:
        d=self.app_root/'cache'/'scan'; d.mkdir(parents=True,exist_ok=True); return d/f'content_scan_{self.language}.json'
    def migrate_legacy(self)->None:
        target=self.path; d=target.parent
        files=sorted({*d.glob('content_scan_v*.json'),*d.glob('content_scan_schema*.json')},key=lambda p:p.stat().st_mtime_ns if p.exists() else 0,reverse=True)
        if not target.is_file():
            for legacy in files:
                try:data=json.loads(legacy.read_text(encoding='utf-8'))
                except (OSError,json.JSONDecodeError):continue
                if data.get('version')==SCAN_CACHE_SCHEMA_VERSION and (not self.installation or data.get('tf3Root')==str(self.installation.root)):
                    shutil.copy2(legacy,target); LOGGER.info('CACHE migrated %s -> %s',legacy.name,target.name); break
        for legacy in files:
            try: legacy.unlink()
            except OSError: LOGGER.warning('CACHE could not remove legacy file %s',legacy)
    def load(self)->dict:
        p=self.path
        if not p.is_file(): return {}
        try:data=json.loads(p.read_text(encoding='utf-8'))
        except (OSError,json.JSONDecodeError,UnicodeError): return {}
        if data.get('version')!=SCAN_CACHE_SCHEMA_VERSION or data.get('contentLanguage')!=self.language or (self.installation and data.get('tf3Root')!=str(self.installation.root)): return {}
        return data
    def save(self,data:dict)->None:
        self.path.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    def clear(self)->None:
        p=self.path
        if p.is_file(): p.unlink()
        for pattern in ('content_scan_v*.json','content_scan_schema*.json'):
            for legacy in p.parent.glob(pattern):
                try: legacy.unlink()
                except OSError: LOGGER.warning('CACHE could not remove legacy file %s',legacy)
    @staticmethod
    def resource_to_dict(r:Resource)->dict:
        return {'name':r.name,'resourceId':r.resource_id,'domain':r.domain,'category':r.category,'extension':r.extension,'modifier':r.modifier,'confidence':r.confidence,'zipPath':str(r.zip_path),'internalPath':r.internal_path,'yearFrom':r.year_from,'yearTo':r.year_to,'metadataCar':r.metadata_car,'carrier':r.carrier,'locked':r.locked,'groupKey':r.group_key,'primaryFile':r.primary_file,'relatedFiles':list(r.related_files),'previewFile':r.preview_file,'internal':r.internal,'templateTimeline':[list(x) for x in r.template_timeline],'templateBased':r.template_based,'sourceType':r.source_type,'sourceName':r.source_name,'sourceId':r.source_id,'vehicleRole':r.vehicle_role,'powerType':r.power_type,'modDescription':r.mod_description,'sourceNamespace':r.source_namespace}
    @staticmethod
    def resources_from_rows(rows, early_construction:dict, early_car:dict)->list[Resource]:
        result=[]
        for item in rows if isinstance(rows,list) else []:
            try:
                r=Resource(str(item['name']),str(item['resourceId']),str(item['domain']),str(item['category']),str(item['extension']),item.get('modifier'),str(item.get('confidence','')),Path(str(item['zipPath'])),str(item['internalPath']),int(item.get('yearFrom',0)),int(item.get('yearTo',0)),int(item.get('yearFrom',0)),int(item.get('yearTo',0)),bool(item.get('metadataCar',False)),str(item.get('carrier','')),bool(item.get('locked',False)),str(item.get('groupKey','')),str(item.get('primaryFile','')),tuple(item.get('relatedFiles',[])),item.get('previewFile'),bool(item.get('internal',False)),tuple((int(x[0]),int(x[1])) for x in item.get('templateTimeline',[]) if isinstance(x,(list,tuple)) and len(x)==2),bool(item.get('templateBased',False)),str(item.get('sourceType','vanilla')),str(item.get('sourceName','Vanilla')),str(item.get('sourceId','')),str(item.get('vehicleRole','')),str(item.get('powerType','')),str(item.get('modDescription','')),str(item.get('sourceNamespace','')))
            except (KeyError,TypeError,ValueError): continue
            if r.locked:
                vid=Path(r.internal_path).stem.split('.')[0]; r.new_year_from=early_construction.get(r.resource_id,early_car.get(vid,r.year_from))
            result.append(r)
        return result
