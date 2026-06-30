from __future__ import annotations
import csv, io, json, os, shutil, sqlite3, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from nb_ems_gateway.config.models import StorageConfig

class SQLiteStore:
    def __init__(self, config: StorageConfig) -> None:
        self.config=config
        self.path=Path(config.path)
        self.skipped_write_count=0
        self.last_skip_reason: str | None=None
        self.last_snapshot_write_ts=0.0
        h=self.health()
        if not h['can_write'] and config.fail_if_mount_missing:
            raise RuntimeError('Storage is not writable: ' + '; '.join(h['reasons']))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn=sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory=sqlite3.Row
        self._init_schema()
        if config.cleanup_on_startup:
            self.cleanup(retention_days=config.retention_days, vacuum=False)

    def _init_schema(self) -> None:
        self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS telemetry_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT,timestamp_utc TEXT NOT NULL,asset_id TEXT,payload_json TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON telemetry_snapshots(timestamp_utc);
        CREATE INDEX IF NOT EXISTS idx_snapshots_asset ON telemetry_snapshots(asset_id);
        CREATE TABLE IF NOT EXISTS telemetry_points (id INTEGER PRIMARY KEY AUTOINCREMENT,timestamp_utc TEXT NOT NULL,asset_id TEXT NOT NULL,signal_name TEXT NOT NULL,category TEXT,value REAL,unit TEXT,quality TEXT,payload_json TEXT);
        CREATE INDEX IF NOT EXISTS idx_points_lookup ON telemetry_points(asset_id, signal_name, timestamp_utc);
        CREATE INDEX IF NOT EXISTS idx_points_category ON telemetry_points(category, timestamp_utc);
        CREATE TABLE IF NOT EXISTS gateway_events (id INTEGER PRIMARY KEY AUTOINCREMENT,timestamp_utc TEXT NOT NULL,severity TEXT NOT NULL,event_type TEXT NOT NULL,source TEXT,asset_id TEXT,message TEXT NOT NULL,payload_json TEXT);
        CREATE INDEX IF NOT EXISTS idx_events_ts ON gateway_events(timestamp_utc);
        CREATE INDEX IF NOT EXISTS idx_events_filters ON gateway_events(severity,event_type,source,asset_id,timestamp_utc);
        ''')
        self.conn.commit()

    def db_size_bytes(self) -> int:
        total=0
        for p in [self.path, Path(str(self.path)+'-wal'), Path(str(self.path)+'-shm')]:
            if p.exists(): total += p.stat().st_size
        return total

    def health(self) -> dict[str,Any]:
        reasons=[]; mount_ok=True; free_mb=None; total_mb=None; used_pct=None
        mount_path=self.config.required_mount_path
        if mount_path:
            mount_ok=os.path.ismount(mount_path)
            if not mount_ok: reasons.append(f'required mount path not mounted: {mount_path}')
            try:
                du=shutil.disk_usage(mount_path if Path(mount_path).exists() else '/')
                free_mb=du.free//(1024*1024); total_mb=du.total//(1024*1024); used_pct=round((du.used/du.total)*100,2)
                if free_mb < self.config.min_free_space_mb: reasons.append(f'free space below minimum: {free_mb} MB < {self.config.min_free_space_mb} MB')
            except Exception as exc:
                reasons.append(f'disk usage check failed: {exc}')
        db_mb=self.db_size_bytes()//(1024*1024)
        if db_mb > self.config.max_db_size_mb: reasons.append(f'database above max size: {db_mb} MB > {self.config.max_db_size_mb} MB')
        return {'enabled':True,'type':'sqlite','path':str(self.path),'required_mount_path':mount_path,'mount_ok':mount_ok,'can_write':len(reasons)==0,'reasons':reasons,'free_space_mb':free_mb,'total_space_mb':total_mb,'used_percent':used_pct,'db_size_mb':db_mb,'min_free_space_mb':self.config.min_free_space_mb,'max_db_size_mb':self.config.max_db_size_mb,'store_mode':self.config.store_mode,'snapshot_interval_sec':self.config.snapshot_interval_sec,'retention_days':self.config.retention_days,'skipped_write_count':self.skipped_write_count,'last_skip_reason':self.last_skip_reason}

    def status(self) -> dict[str,Any]:
        h=self.health(); tables={}; table_errors={}
        if hasattr(self,'conn'):
            for t in ['telemetry_snapshots','telemetry_points','gateway_events']:
                try:
                    row=self.conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()
                    tables[t]=int(row[0]) if row and row[0] is not None else 0
                except Exception as exc:
                    tables[t]=None
                    table_errors[t]=str(exc)
        h['tables']=tables
        if table_errors:
            h['table_errors']=table_errors
        return h

    def _can_write(self) -> bool:
        h=self.health()
        if h['can_write']: return True
        self.skipped_write_count+=1; self.last_skip_reason='; '.join(h['reasons'])
        return False

    def insert_snapshot(self, asset_id: str, payload: dict[str,Any]) -> bool:
        now=time.time()
        if now - self.last_snapshot_write_ts < self.config.snapshot_interval_sec: return False
        if not self._can_write(): return False
        ts=datetime.now(timezone.utc).isoformat()
        signals=payload.get('signals',{}) if self.config.store_mode=='full_snapshot' else payload.get('key_signals',{})
        stored={k:v for k,v in payload.items() if k!='signals'}; stored['signals']=signals
        self.conn.execute('INSERT INTO telemetry_snapshots(timestamp_utc,asset_id,payload_json) VALUES (?,?,?)',(ts,asset_id,json.dumps(stored,separators=(',',':'))))
        for name,sig in signals.items():
            self.conn.execute('INSERT INTO telemetry_points(timestamp_utc,asset_id,signal_name,category,value,unit,quality,payload_json) VALUES (?,?,?,?,?,?,?,?)',(ts,asset_id,name,sig.get('category'),sig.get('value') if isinstance(sig.get('value'),(int,float)) else None,sig.get('unit'),sig.get('quality','good'),json.dumps(sig,separators=(',',':'))))
        self.conn.commit(); self.last_snapshot_write_ts=now; return True

    def insert_event(self,severity:str,event_type:str,message:str,payload:dict[str,Any]|None=None,*,source:str|None=None,asset_id:str|None=None) -> int | None:
        if not self._can_write(): return None
        ts=datetime.now(timezone.utc).isoformat()
        cur=self.conn.execute('INSERT INTO gateway_events(timestamp_utc,severity,event_type,source,asset_id,message,payload_json) VALUES (?,?,?,?,?,?,?)',(ts,severity.lower(),event_type,source,asset_id,message,json.dumps(payload or {},separators=(',',':'))))
        self.conn.commit(); return int(cur.lastrowid)

    def cleanup(self, retention_days: int | None=None, vacuum: bool | None=None) -> dict[str,Any]:
        if not self._can_write(): return {'ok':False,'reason':self.last_skip_reason}
        days=retention_days or self.config.retention_days
        cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
        deleted={}
        for table in ['telemetry_snapshots','telemetry_points','gateway_events']:
            cur=self.conn.execute(f'DELETE FROM {table} WHERE timestamp_utc < ?',(cutoff,)); deleted[table]=int(cur.rowcount)
        self.conn.commit()
        do_vacuum = self.config.vacuum_after_cleanup if vacuum is None else vacuum
        if do_vacuum:
            self.vacuum()
        return {'ok':True,'retention_days':days,'cutoff_utc':cutoff,'deleted':deleted,'health':self.health()}

    def vacuum(self) -> dict[str,Any]:
        before=self.db_size_bytes(); self.conn.execute('VACUUM'); self.conn.commit(); after=self.db_size_bytes()
        return {'ok':True,'before_bytes':before,'after_bytes':after,'saved_bytes':before-after}

    def query_events(self, **kw: Any) -> dict[str,Any]:
        severity=kw.get('severity'); event_type=kw.get('event_type'); source=kw.get('source'); asset_id=kw.get('asset_id'); from_time=kw.get('from_time'); to_time=kw.get('to_time'); search=kw.get('search'); limit=int(kw.get('limit',200)); offset=int(kw.get('offset',0)); order=kw.get('order','desc')
        where=[]; args=[]
        for col,val in [('severity',severity.lower() if severity else None),('event_type',event_type),('source',source),('asset_id',asset_id)]:
            if val: where.append(f'{col}=?'); args.append(val)
        if from_time: where.append('timestamp_utc>=?'); args.append(from_time)
        if to_time: where.append('timestamp_utc<=?'); args.append(to_time)
        if search: where.append('(message LIKE ? OR event_type LIKE ? OR payload_json LIKE ?)'); args += [f'%{search}%']*3
        clause=' WHERE '+' AND '.join(where) if where else ''
        total=self.conn.execute('SELECT COUNT(*) FROM gateway_events'+clause,args).fetchone()[0]
        direction='ASC' if str(order).lower()=='asc' else 'DESC'
        rows=self.conn.execute(f'SELECT * FROM gateway_events{clause} ORDER BY timestamp_utc {direction} LIMIT ? OFFSET ?',args+[limit,offset]).fetchall()
        return {'total':total,'limit':limit,'offset':offset,'items':[self._event(r) for r in rows]}

    def event_summary(self, from_time: str|None=None, to_time: str|None=None) -> dict[str,Any]:
        where=[]; args=[]
        if from_time: where.append('timestamp_utc>=?'); args.append(from_time)
        if to_time: where.append('timestamp_utc<=?'); args.append(to_time)
        clause=' WHERE '+' AND '.join(where) if where else ''
        def grouped(col): return {r[0] or 'unknown':r[1] for r in self.conn.execute(f'SELECT {col},COUNT(*) FROM gateway_events{clause} GROUP BY {col}',args)}
        recent=self.conn.execute(f'SELECT * FROM gateway_events{clause} ORDER BY timestamp_utc DESC LIMIT 10',args).fetchall()
        return {'total':self.conn.execute('SELECT COUNT(*) FROM gateway_events'+clause,args).fetchone()[0],'by_severity':grouped('severity'),'by_event_type':grouped('event_type'),'by_source':grouped('source'),'by_asset_id':grouped('asset_id'),'recent':[self._event(r) for r in recent]}

    def log_filter_options(self) -> dict[str,list[str]]:
        def vals(c): return [r[0] for r in self.conn.execute(f"SELECT DISTINCT {c} FROM gateway_events WHERE {c} IS NOT NULL AND {c} != '' ORDER BY {c}")]
        return {'severities':vals('severity'),'event_types':vals('event_type'),'sources':vals('source'),'asset_ids':vals('asset_id')}

    def export_events_csv(self, **kw: Any) -> str:
        res=self.query_events(**kw); out=io.StringIO(); fields=['id','timestamp_utc','severity','event_type','source','asset_id','message','payload_json']; w=csv.DictWriter(out,fieldnames=fields); w.writeheader()
        for item in res['items']:
            w.writerow({**{k:item.get(k) for k in fields if k!='payload_json'},'payload_json':json.dumps(item.get('payload',{}),separators=(',',':'))})
        return out.getvalue()

    def query_snapshots(self, asset_id: str|None=None, limit: int=100) -> list[dict[str,Any]]:
        if asset_id: rows=self.conn.execute('SELECT * FROM telemetry_snapshots WHERE asset_id=? ORDER BY timestamp_utc DESC LIMIT ?',(asset_id,limit)).fetchall()
        else: rows=self.conn.execute('SELECT * FROM telemetry_snapshots ORDER BY timestamp_utc DESC LIMIT ?',(limit,)).fetchall()
        return [{'id':r['id'],'timestamp_utc':r['timestamp_utc'],'asset_id':r['asset_id'],'payload':json.loads(r['payload_json'])} for r in rows]

    def query_points(self, asset_id: str, signal_name: str, limit: int=100) -> list[dict[str,Any]]:
        rows=self.conn.execute('SELECT * FROM telemetry_points WHERE asset_id=? AND signal_name=? ORDER BY timestamp_utc DESC LIMIT ?',(asset_id,signal_name,limit)).fetchall()
        return [{'timestamp_utc':r['timestamp_utc'],'asset_id':r['asset_id'],'signal_name':r['signal_name'],'value':r['value'],'unit':r['unit'],'quality':r['quality'],'category':r['category']} for r in rows]

    def _event(self,row:sqlite3.Row)->dict[str,Any]:
        try: payload=json.loads(row['payload_json'] or '{}')
        except Exception: payload={'raw':row['payload_json']}
        return {'id':row['id'],'timestamp_utc':row['timestamp_utc'],'severity':row['severity'],'event_type':row['event_type'],'source':row['source'],'asset_id':row['asset_id'],'message':row['message'],'payload':payload}
    def close(self)->None: self.conn.close()
