from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from fastapi import FastAPI, Header, HTTPException, Request
app=FastAPI(title='Example NorthBound EMS Backend Receiver')
DATA_DIR=Path(os.getenv('BACKEND_DATA_DIR','received_payloads'))
API_TOKEN=os.getenv('BACKEND_API_TOKEN','CHANGE_ME_API_TOKEN')
@app.get('/health')
def health()->dict[str,Any]: return {'status':'ok'}
@app.post('/api/v1/gateway/telemetry')
async def receive(request: Request, authorization: str|None=Header(default=None), x_gateway_id: str|None=Header(default=None))->dict[str,Any]:
    if API_TOKEN and authorization != f'Bearer {API_TOKEN}': raise HTTPException(401,'invalid bearer token')
    payload=await request.json(); gid=x_gateway_id or payload.get('gateway',{}).get('id','unknown')
    DATA_DIR.mkdir(parents=True,exist_ok=True); path=DATA_DIR/f"{gid}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"; path.write_text(json.dumps(payload,indent=2))
    return {'accepted':True,'gateway_id':gid,'stored_file':str(path)}
