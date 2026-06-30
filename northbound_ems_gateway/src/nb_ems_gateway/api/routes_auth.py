from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from nb_ems_gateway.auth.security import (
    CurrentUser,
    LoginRequest,
    TokenResponse,
    audit_auth_event,
    authenticate_user,
    create_access_token,
    require_auth,
)

router = APIRouter()


@router.post('/api/auth/login', response_model=TokenResponse)
def login(request: Request, body: LoginRequest) -> TokenResponse:
    auth_config = request.app.state.container.config.auth
    result = authenticate_user(auth_config, body.username.strip(), body.password)
    if not result.ok or not result.user:
        audit_auth_event(request, 'auth_login_failed', 'Login failed', {'username': body.username.strip(), 'reason': result.reason}, severity='warning')
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid username or password')
    token = create_access_token(auth_config, result.user)
    audit_auth_event(request, 'auth_login_success', 'Login successful', user=result.user)
    return TokenResponse(
        access_token=token,
        expires_in_sec=auth_config.token_expiry_minutes * 60,
        username=result.user.username,
        role=result.user.role,
        display_name=result.user.display_name,
    )


@router.get('/api/auth/me')
async def me(user: CurrentUser = Depends(require_auth)) -> dict:
    return {'authenticated': True, 'username': user.username, 'role': user.role, 'display_name': user.display_name}
