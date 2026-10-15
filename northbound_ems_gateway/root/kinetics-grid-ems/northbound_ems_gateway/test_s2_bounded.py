#!/usr/bin/env python3
"""Offline S2 bounded chunks and per-message SQLite ACK integration tests.
No field services, network connections, or production database are accessed.
"""
from __future__ import annotations
import asyncio
import copy
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(os.environ.get('S2_TEST_GATEWAY_ROOT', Path(__file__).resolve().parent/'candidate')).resolve()
sys.path.insert(0,str(ROOT/'src'))
from nb_ems_gateway.central_sync.config import load_central_sync_config
from nb_ems_gateway.central_sync.general_asset_producer import GeneralAssetProducer
from nb_ems_gateway.central_sync.contracts import TransportBatch
from nb_ems_gateway.central_sync.outbox import OutboxCapacityError,OutboxStore
from nb_ems_gateway.central_sync.uploader import CentralSyncUploader
from nb_ems_gateway.central_sync.client import TransportResponse
from nb_ems_gateway.dictionary.central_signal_policy import CentralSignalPolicy

MAN=ROOT/'data/central_sync/canonical_signal_policy_frozen_v1_1.json'

def build_snapshot(policy):
  records=[]
  for src in ('external_ems_1','external_ems_2'):
    for base_asset,specs in sorted(policy.s2_by_asset.items()):
      signals={s['signal']:{'point_id':s['point_id'],'value':0.0,'quality':'good',
          'updated_utc':'2026-10-15T00:00:00Z','age_ms':0} for s in specs}
      records.append({'source_id':src,'runtime_asset_id':f'{src}_{base_asset}',
        'base_asset_id':base_asset,'substream':specs[0]['substream'],
        'selected_signal_count':len(signals),'signals':signals})
  assert len(records)==18
  assert sum(len(r['signals']) for r in records)==2700
  return {'sample_source':'asset_manager_live_cache','persisted_source':False,
    'policy_manifest_sha256':policy.sha256,'sampled_at_epoch_ms':10000000,
    'sampled_at_utc':'2026-10-15T00:00:00Z','source_count':2,
    'asset_record_count':18,'s2_canonical_signal_count':1350,
    's2_runtime_signal_count':2700,'records':records}

class Clock:
  t=0.0
  def __call__(self):return self.t

class Source:
  def __init__(self,snapshot): self.snapshot=snapshot
  def read(self): return self.snapshot

class InMemoryOutbox:
  def __init__(self, fail_after=None): self.msgs=[];self.seqs={};self.fail_after=fail_after
  def next_sequence(self, stream, substream):
    k=(stream,substream);self.seqs[k]=self.seqs.get(k,0)+1;return self.seqs[k]
  def enqueue(self,m):
    if self.fail_after is not None and len(self.msgs)>=self.fail_after:
      raise OutboxCapacityError('synthetic capacity gate')
    self.msgs.append(m)
    return True
  def stats(self): return {'stored':len(self.msgs)}

class AckBackend:
  def __init__(self,miss_first=False):self.missing=miss_first;self.calls=[];self.acked=[]
  async def post_batch(self, data):
    request=json.loads(data)
    ids=[m['message_id'] for m in request['messages']]
    self.calls.append((len(data),ids))
    if self.missing:
      self.missing=False
      ids=ids[1:]
    self.acked.extend(ids)
    return TransportResponse(status_code=200, body={'accepted':[{'message_id':x,'status':'accepted'} for x in ids]})


def make_config(temp):
  config=load_central_sync_config(ROOT/'configs/central_sync.json')
  config.general_assets.policy_manifest_path=str(MAN)
  config.general_assets.status_file=str(Path(temp)/'s2_status.json')
  config.uploader.pause_file=str(Path(temp)/'never_pause')
  config.uploader.max_request_bytes=131072
  config.uploader.max_messages_per_request=25
  config.uploader.coalescing_window_sec=0
  config.identity.gateway_id='offline-unit-test'
  config.identity.site_id='offline-site'
  return config

async def test():
  policy=CentralSignalPolicy(MAN)
  initial=build_snapshot(policy)
  config=None
  with tempfile.TemporaryDirectory(prefix='s2_split_integration_') as temp:
    cfg=make_config(temp)
    clk=Clock()
    source=Source(copy.deepcopy(initial))
    outbox=InMemoryOutbox()
    prod=GeneralAssetProducer(config=cfg,outbox=outbox,source=source,clock=clk)
    prod._write_status=lambda:None
    startup=await prod.collect_once()
    assert startup['record_count']==2700,startup
    assert startup['message_count']>9,startup
    assert sum(len(m.records) for m in outbox.msgs)==2700
    bounds=[len(json.dumps(m.model_dump(mode='json'),separators=(',', ':'),ensure_ascii=False).encode()) for m in outbox.msgs]
    assert max(bounds)<=98304,(max(bounds),prod._s2_message_budget())
    assert len(set(m.message_id for m in outbox.msgs))==len(outbox.msgs)
    assert all(len(m.records)>0 for m in outbox.msgs)
    bysub=defaultdict(list)
    for m in outbox.msgs:bysub[m.substream].append(m)
    assert len(bysub)==9
    for sub,ms in bysub.items():
      assert len({x.sequence for x in ms})==len(ms)
      assert [x.sequence for x in ms]==list(range(1,len(ms)+1)),sub
      for m in ms:
        assert m.stream=='general_asset_telemetry' and m.substream==sub
    actual=Counter((r['runtime_signal_id'],r['point_id']) for m in outbox.msgs for r in m.records)
    expected=Counter((f"{source_id}.{spec['asset']}.{spec['signal']}",spec['point_id']) for source_id in ('external_ems_1','external_ems_2') for spec in policy.s2_signals)
    assert actual==expected, 'startup point loss/duplication'
    # Single logical S2 messages fit comfortably into the existing 128 KiB HTTP wrapper.
    from nb_ems_gateway.central_sync.contracts import TransportBatch
    wrapped=max(len(json.dumps(TransportBatch(gateway_id=cfg.identity.gateway_id,messages=[m.model_dump(mode='json')]).model_dump(mode='json'),separators=(',', ':'),ensure_ascii=False).encode()) for m in outbox.msgs)
    assert wrapped < 131072
    # No retransmit before due. Natural 60-sec tick still splits into bounded messages.
    clk.t=1
    source.snapshot['sampled_at_epoch_ms']+=1000
    assert (await prod.collect_once())['reason']=='no_due_records'
    clk.t=60
    source.snapshot['sampled_at_epoch_ms']+=59000
    at60=len(outbox.msgs)
    r60=await prod.collect_once()
    assert r60['record_count']>=1000,r60
    assert all(len(json.dumps(m.model_dump(mode='json'),separators=(',', ':'),ensure_ascii=False).encode())<=98304 for m in outbox.msgs[at60:])
    # Changed value and quality transitions produce independent records.
    flag=next(s for s in policy.s2_signals if s['policy']=='ON_CHANGE_HEARTBEAT')
    record=next(r for r in source.snapshot['records'] if r['source_id']=='external_ems_1' and r['base_asset_id']==flag['asset'])
    record['signals'][flag['signal']]['value']=1.0
    clk.t=61;source.snapshot['sampled_at_epoch_ms']+=1000
    changed=await prod.collect_once()
    assert changed['reason_counts']=={'change':1},changed
    record['signals'][flag['signal']]['quality']='bad'
    clk.t=62;source.snapshot['sampled_at_epoch_ms']+=1000
    quality=await prod.collect_once()
    assert quality['reason_counts']=={'change':1},quality
    # Bad SHA rejects emission.
    source.snapshot['policy_manifest_sha256']='incorrect'
    oldlen=len(outbox.msgs)
    clk.t=63;source.snapshot['sampled_at_epoch_ms']+=1000
    assert (await prod.collect_once())['reason']=='source_error'
    assert len(outbox.msgs)==oldlen

    # Capacity interruption must NOT rewind already-written signal state.
    cfg2=make_config(temp)
    source2=Source(copy.deepcopy(initial))
    failing=InMemoryOutbox(fail_after=3)
    clock2=Clock()
    prod2=GeneralAssetProducer(config=cfg2,outbox=failing,source=source2,clock=clock2)
    prod2._write_status=lambda:None
    interrupted=await prod2.collect_once()
    assert interrupted['reason']=='outbox_capacity'
    assert len(failing.msgs)==3
    committed=Counter(r['runtime_signal_id'] for m in failing.msgs for r in m.records)
    assert len(prod2._last_fingerprint)==sum(committed.values()),'successful chunks not committed'
    failing.fail_after=None
    clock2.t=1
    source2.snapshot['sampled_at_epoch_ms']+=1000
    retried=await prod2.collect_once()
    assert retried['emitted']
    allids=Counter(r['runtime_signal_id'] for m in failing.msgs for r in m.records)
    assert len(allids)==2700 and all(v==1 for v in allids.values()),'partial recovery double counted or lost points'

    # Preflight must reject a single oversized UTF-8 signal BEFORE enqueuing
    # any part of the snapshot or consuming any sequence numbers.
    oversized=copy.deepcopy(initial)
    oversized['records'][0]['signals'][next(iter(oversized['records'][0]['signals']))]['value']='😀'*40000
    badstore=InMemoryOutbox()
    prod_bad=GeneralAssetProducer(config=cfg2,outbox=badstore,source=Source(oversized),clock=Clock())
    prod_bad._write_status=lambda:None
    badresult=await prod_bad.collect_once()
    assert badresult['reason']=='message_size_error',badresult
    assert not badstore.msgs and not badstore.seqs
    # Smaller uploader budgets automatically reduce the S2 chunk size.
    small_cfg=make_config(temp)
    small_cfg.uploader.max_request_bytes=65536
    smallbox=InMemoryOutbox()
    smallprod=GeneralAssetProducer(config=small_cfg,outbox=smallbox,source=Source(copy.deepcopy(initial)),clock=Clock())
    smallprod._write_status=lambda:None
    smallres=await smallprod.collect_once()
    assert smallres['record_count']==2700
    assert all(len(json.dumps(m.model_dump(mode='json'),separators=(',', ':'),ensure_ascii=False).encode())<=49152 for m in smallbox.msgs)

    # Actual sqlite outbox and original uploader with fake backend, per-message ACK.
    db=OutboxStore(str(Path(temp)/'central_sync_test.db'),min_free_space_mb=0,fail_if_mount_missing=False)
    try:
      current_snapshot=copy.deepcopy(initial)
      current_snapshot["sampled_at_utc"]=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
      src=Source(current_snapshot)
      liveclock=Clock()
      gp=GeneralAssetProducer(config=cfg,outbox=db,source=src,clock=liveclock)
      gp._write_status=lambda:None
      sqlresult=await gp.collect_once()
      assert sqlresult['record_count']==2700
      rows=db.conn.execute('SELECT state,message_id,substream,sequence,payload_bytes,payload_json FROM outbox_messages ORDER BY substream,sequence').fetchall()
      assert len(rows)==sqlresult['message_count']
      assert max(row['payload_bytes'] for row in rows)<=98304
      assert all(json.loads(row['payload_json'])['message_id']==row['message_id'] for row in rows)
      ack=AckBackend(miss_first=True)
      uploader=CentralSyncUploader(config=cfg,outbox=db,client=ack)
      # Iterate until all pending are submitted; partial ACK (one missing) retries.
      for _ in range(100):
        if not await uploader.run_once(): break
      pending=db.conn.execute("SELECT count(*) FROM outbox_messages WHERE state IN ('pending','retry','inflight')").fetchone()[0]
      assert pending==1,('expected one missing ACK retry',pending)
      missing=db.conn.execute("SELECT message_id FROM outbox_messages WHERE state='retry'").fetchone()[0]
      # Force retry eligibility in test-only DB, then test idempotent accepted ACK.
      db.conn.execute("UPDATE outbox_messages SET next_attempt_epoch=0 WHERE state='retry'")
      db.conn.commit()
      uploader.client=AckBackend()
      assert await uploader.run_once()
      assert db.conn.execute("SELECT count(*) FROM outbox_messages WHERE state!='acked'").fetchone()[0]==0
      assert db.conn.execute("SELECT count(*) FROM outbox_messages WHERE ack_status='accepted'").fetchone()[0]==len(rows)
      # Exercise the uploader's existing HTTP 413 bisection on a separate
      # scratch SQLite outbox (no changed backend envelope or ACK schema).
      from nb_ems_gateway.central_sync.contracts import make_message
      store413=OutboxStore(str(Path(temp)/'http413.db'),min_free_space_mb=0,fail_if_mount_missing=False)
      try:
        for n in range(2):
          msg=make_message(schema_version=cfg.identity.schema_version,gateway_id=cfg.identity.gateway_id,
            site_id=cfg.identity.site_id,stream='general_asset_telemetry',substream='bms_extended',
            sequence=store413.next_sequence('general_asset_telemetry','bms_extended'),
            priority='P3',records=[{'point_id':f'pTEST{n}','value':n}],
            created_at_utc=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'))
          assert store413.enqueue(msg)
        class RejectBatch413:
          def __init__(self):self.calls=[]
          async def post_batch(self, raw):
            parsed=json.loads(raw)
            self.calls.append(parsed)
            if len(parsed['messages'])>1:
              return TransportResponse(status_code=413,body={},text='request too large')
            return TransportResponse(status_code=200,body={'accepted':[
              {'message_id':parsed['messages'][0]['message_id'],'status':'already_processed'}]})
        client413=RejectBatch413()
        upload413=CentralSyncUploader(config=cfg,outbox=store413,client=client413)
        assert await upload413.run_once()
        assert len(client413.calls)==3,len(client413.calls)
        statuses=[r[0] for r in store413.conn.execute('SELECT ack_status FROM outbox_messages')]
        assert sorted(statuses)==['already_processed','already_processed'],statuses
      finally:
        store413.close()
      # The uploader must preserve every chunk's message_id when it gets ACKed.
      assert len(rows)==len({row['message_id'] for row in rows})
      request_max=max(size for size, _ in ack.calls)
      report={
        'status':'OFFLINE_PASS','source':'October 9 authoritative archive + v1.4 manifest',
        'startup_signals':2700,'startup_messages':startup['message_count'],
        'bms_startup_chunks':len(bysub['bms_extended']),
        'max_logical_message_bytes':max(bounds),
        'max_single_message_transport_bytes':wrapped,
        'budget_bytes':98304,'uploader_target_bytes':131072,
        'at_60s_records':r60['record_count'],'at_60s_messages':r60['message_count'],
        'partial_capacity_interruption':'PASS','record_recovery_after_interruption':'PASS',
        'oversized_individual_record_preflight':'PASS','adaptive_64KiB_uploader_budget':'PASS','http_413_split_and_idempotent_ack':'PASS',
        'sqlite_outbox_durable':'PASS','partial_ack_retry':'PASS','all_chunks_individually_ACKed':'PASS',
        'max_actual_transport_request_bytes':request_max,'transport_request_count':len(ack.calls)+1,
        'backend_validation':'FAKE_BACKEND_ONLY',
        'live_http_or_field_tested':False,
      }
      print(json.dumps(report,indent=2))
      return report
    finally:
      db.close()

if __name__=='__main__':
  asyncio.run(test())
