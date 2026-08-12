from fastapi import APIRouter, Request, HTTPException
router=APIRouter()
@router.get('/api/server-upload/status')
def status(request: Request)->dict: return request.app.state.container.server_upload_status()
@router.post('/api/server-upload/upload-once')
async def upload_once(request: Request)->dict:
    svc=request.app.state.container.server_upload_service
    if not svc: raise HTTPException(503,'server upload service unavailable')
    return await svc.upload_once()
