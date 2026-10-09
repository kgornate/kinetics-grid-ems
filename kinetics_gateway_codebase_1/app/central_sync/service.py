from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
from typing import Any

from .alarm_event_producer import AlarmEventProducer
from .charge_discharge_producer import ChargeDischargeProducer
from .command_downlink import CommandDownlinkProcessor
from .compat_application_producer import CompatibilityApplicationProducer
from .config import load_central_sync_config
from .configuration_audit_producer import ConfigurationAuditProducer
from .fast_bess_producer import FastBESSProducer
from .gateway_health_producer import GatewayHealthProducer
from .general_asset_producer import GeneralAssetProducer
from .outbox import OutboxStore
from .overflow_archiver import OverflowArchiver
from .overflow_recovery import OverflowRecoveryService
from .uploader import CentralSyncUploader


def parse_args() -> argparse.Namespace:
    p=argparse.ArgumentParser(description='Ornate EMS Central Sync - Northbound frozen v1.3 compatible + S10')
    p.add_argument('--config',default='configs/central_sync_frozen_v1_3_kalpa.json')
    p.add_argument('--status',action='store_true')
    p.add_argument('--once',action='store_true',help='one uploader transport attempt')
    p.add_argument('--produce-once',choices=['s1','s2','s3','s4','s5','s6','s7','s8','s10'])
    p.add_argument('--poll-d1-once',action='store_true')
    p.add_argument('--dry-contract',action='store_true',help='print frozen stream/substream architecture')
    return p.parse_args()


async def amain() -> int:
    args=parse_args(); config=load_central_sync_config(args.config)
    logging.basicConfig(level=getattr(logging,config.log_level,logging.INFO),format='%(asctime)s %(levelname)s %(name)s - %(message)s')
    if args.dry_contract:
        print(json.dumps({
            'schema_version':config.identity.schema_version,
            'northbound_frozen_compatible_streams':{
                'S1':'fast_bess_telemetry','S2':'general_asset_telemetry','S3':'gateway_health','S4':'alarms_events',
                'S5':'soc_controller','S6':'solis','S7':'edge_ai','S8':'configuration_audit','S9':'command_results',
                'S10':'battery_charge_discharge_control','D1':'command_requests'},
            's2_substreams':['ems_system','pcs_extended','bms_extended','io_module','liquid_cooling','fire_protection','dehumidifier','remote_control','utility_meter'],
        },indent=2)); return 0

    outbox=OutboxStore(config.outbox.path,max_db_size_mb=config.outbox.max_db_size_mb,min_free_space_mb=config.outbox.min_free_space_mb,required_mount_path=config.outbox.required_mount_path,fail_if_mount_missing=config.outbox.fail_if_mount_missing)
    transport_lock=asyncio.Lock(); uploader=CentralSyncUploader(config=config,outbox=outbox,transport_lock=transport_lock)
    s1=FastBESSProducer(config=config,outbox=outbox)
    s2=GeneralAssetProducer(config=config,outbox=outbox)
    s3=GatewayHealthProducer(config=config,outbox=outbox,central_status_provider=uploader.status)
    s4=AlarmEventProducer(config=config,outbox=outbox)
    s5=CompatibilityApplicationProducer(config=config,outbox=outbox,producer_config=config.soc_controller)
    s6=CompatibilityApplicationProducer(config=config,outbox=outbox,producer_config=config.solis)
    s7=CompatibilityApplicationProducer(config=config,outbox=outbox,producer_config=config.edge_ai)
    s8=ConfigurationAuditProducer(config=config,outbox=outbox,central_sync_config_path=args.config)
    s10=ChargeDischargeProducer(config=config,outbox=outbox)
    d1=CommandDownlinkProcessor(config=config,outbox=outbox)
    overflow_archiver=OverflowArchiver(config=config,outbox=outbox)
    overflow_recovery=OverflowRecoveryService(config,transport_lock=transport_lock,client=uploader.client)
    producers={'s1':s1,'s2':s2,'s3':s3,'s4':s4,'s5':s5,'s6':s6,'s7':s7,'s8':s8,'s10':s10}

    async def shutdown() -> None:
        await d1.stop()
        for producer in producers.values(): await producer.stop()
        await overflow_recovery.stop(); await overflow_archiver.stop(); await uploader.stop()

    try:
        if args.status:
            print(json.dumps({'uploader':uploader.status(),'outbox':outbox.stats(),'producers':{k:v.status() for k,v in producers.items()},'d1':d1.status()},indent=2,default=str)); return 0
        if not config.enabled:
            print(f'Central Sync disabled by config: {args.config}'); return 0
        if args.produce_once:
            producer=producers[args.produce_once]
            if not producer.producer_config.enabled:
                print(json.dumps({'emitted':False,'reason':'producer_disabled','producer':args.produce_once},indent=2)); return 2
            kwargs={}
            if args.produce_once=='s3': kwargs={'force_heartbeat':True,'reason':'manual_test'}
            if args.produce_once in {'s5','s6','s7','s10'}: kwargs={'force_emit':True}
            result=await producer.collect_once(**kwargs); print(json.dumps(result,indent=2,default=str)); return 0
        if args.poll_d1_once:
            if not config.command_downlink.enabled:
                print(json.dumps({'processed':0,'reason':'D1 disabled'},indent=2)); return 2
            print(json.dumps(await d1.poll_once(),indent=2,default=str)); return 0
        if args.once:
            await uploader.run_once(); print(json.dumps(uploader.status(),indent=2,default=str)); return 0

        loop=asyncio.get_running_loop()
        for sig in (signal.SIGTERM,signal.SIGINT):
            try: loop.add_signal_handler(sig,lambda:asyncio.create_task(shutdown()))
            except NotImplementedError: pass
        tasks=[asyncio.create_task(uploader.run_forever(),name='central-sync-uploader')]
        if config.overflow_archive.enabled: tasks.append(asyncio.create_task(overflow_archiver.run_forever(),name='overflow-archiver'))
        if config.overflow_recovery.enabled: tasks.append(asyncio.create_task(overflow_recovery.run_forever(),name='overflow-recovery'))
        for key,producer in producers.items():
            if producer.producer_config.enabled: tasks.append(asyncio.create_task(producer.run_forever(),name=f'producer-{key}'))
        if config.command_downlink.enabled: tasks.append(asyncio.create_task(d1.run_forever(),name='d1-command-downlink'))
        await asyncio.gather(*tasks)
        return 0
    finally:
        await d1.close()
        for p in producers.values():
            close=getattr(p,'close',None)
            if close:
                result=close()
                if asyncio.iscoroutine(result): await result
        await uploader.close(); outbox.close()


def main() -> None:
    raise SystemExit(asyncio.run(amain()))

if __name__=='__main__': main()
