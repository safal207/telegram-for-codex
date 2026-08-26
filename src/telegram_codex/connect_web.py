from __future__ import annotations

import hashlib
import inspect
import logging
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession

from .config import (
    ConfigurationError,
    Settings,
    _ensure_private_directory,
    _harden_private_file,
    validate_high_entropy_secret,
)

_FLOW_TTL_SECONDS = 10 * 60
_MAX_ACTIVE_FLOWS = 5
_flows: dict[str, "AuthFlow"] = {}
logger = logging.getLogger(__name__)

_NO_STORE_HEADERS = {"Cache-Control": "no-store"}
_CONNECT_PAGE_HEADERS = {
    **_NO_STORE_HEADERS,
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


@dataclass(slots=True)
class AuthFlow:
    client: TelegramClient
    phone: str
    phone_code_hash: str
    created_at: float
    closed: bool = False


def _valid_connect_token(value: str) -> bool:
    try:
        validate_high_entropy_secret(value, "TELEGRAM_CONNECT_TOKEN")
    except ConfigurationError:
        return False
    return True


def _authorized(request: Request) -> bool:
    expected = os.getenv("TELEGRAM_CONNECT_TOKEN", "").strip()
    supplied = request.headers.get("x-telegram-connect-token", "")
    if not _valid_connect_token(expected) or not supplied:
        return False
    expected_digest = hashlib.sha256(expected.encode("utf-8")).digest()
    supplied_digest = hashlib.sha256(supplied.encode("utf-8")).digest()
    return secrets.compare_digest(expected_digest, supplied_digest)


def _session_store_path() -> Path:
    raw = os.getenv("TELEGRAM_SESSION_STRING_FILE", "").strip()
    if not raw:
        raw = ".telegram/remote.session.string"
    return Path(raw).expanduser()


def _persist_session_string(value: str) -> Path:
    path = _session_store_path()
    _ensure_private_directory(path.parent)
    _harden_private_file(path)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    payload = value.encode("utf-8")
    flags = (
        os.O_CREAT
        | os.O_EXCL
        | os.O_WRONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor: int | None = None
    try:
        descriptor = os.open(tmp, flags, 0o600)
        try:
            remaining = memoryview(payload)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise OSError("partial Telegram session write")
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
            descriptor = None
        _harden_private_file(tmp)
        os.replace(tmp, path)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if os.path.lexists(tmp):
            os.unlink(tmp)
    _harden_private_file(path)
    # Make the new session available to this process immediately. It is never
    # returned to the browser or exposed through an MCP tool.
    os.environ["TELEGRAM_SESSION_STRING"] = value
    return path


async def _discard_flow(flow_id: str, fallback: AuthFlow | None = None) -> None:
    """Remove a login flow and best-effort disconnect its Telegram client."""
    flow = _flows.pop(flow_id, None) or fallback
    if flow is None or flow.closed:
        return
    flow.closed = True
    try:
        await flow.client.disconnect()
    except Exception:
        logger.warning("Could not disconnect Telegram login flow", exc_info=True)


async def _prune_flows() -> None:
    cutoff = time.monotonic() - _FLOW_TTL_SECONDS
    expired = [flow_id for flow_id, flow in _flows.items() if flow.created_at < cutoff]
    for flow_id in expired:
        await _discard_flow(flow_id)


async def _json(request: Request) -> dict[str, Any]:
    try:
        value = await request.json()
    except Exception as exc:  # Starlette may wrap malformed JSON differently by version.
        raise ValueError("Invalid JSON body") from exc
    if not isinstance(value, dict):
        raise ValueError("JSON body must be an object")
    return value


def _error(message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": message},
        status_code=status_code,
        headers=_NO_STORE_HEADERS,
    )


def _response(payload: dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers=_NO_STORE_HEADERS)


async def _finish_login(
    flow_id: str,
    flow: AuthFlow,
    on_session_saved: Callable[[], Any] | None,
) -> JSONResponse:
    try:
        me = await flow.client.get_me()
        session_string = flow.client.session.save()
        if not session_string:
            return _error("Telegram authorized, but the session could not be serialized.", 500)
        _persist_session_string(session_string)
    finally:
        await _discard_flow(flow_id, flow)

    if on_session_saved is not None:
        result = on_session_saved()
        if inspect.isawaitable(result):
            await result

    return _response(
        {
            "ok": True,
            "status": "connected",
            "user": {
                "id": int(me.id),
                "username": getattr(me, "username", None),
                "first_name": getattr(me, "first_name", None),
            },
        }
    )


def install_connect_routes(
    mcp: FastMCP,
    on_session_saved: Callable[[], Any] | None = None,
) -> None:
    @mcp.custom_route("/connect", methods=["GET"])
    async def connect_page(request: Request) -> Response:
        return HTMLResponse(_CONNECT_HTML, headers=_CONNECT_PAGE_HEADERS)

    @mcp.custom_route("/connect/start", methods=["POST"])
    async def connect_start(request: Request) -> Response:
        if not _authorized(request):
            return _error("Invalid connect key.", 401)
        await _prune_flows()
        if len(_flows) >= _MAX_ACTIVE_FLOWS:
            return _error("Too many active login attempts. Try again shortly.", 429)
        client: TelegramClient | None = None
        try:
            body = await _json(request)
            phone = str(body.get("phone", "")).strip()
            if not phone.startswith("+") or len(phone) < 8 or len(phone) > 20:
                return _error("Enter the phone number in international format, for example +79991234567.")

            settings = Settings.from_env()
            client = TelegramClient(StringSession(), settings.api_id, settings.api_hash)
            await client.connect()
            sent = await client.send_code_request(phone)
            flow_id = secrets.token_urlsafe(24)
            _flows[flow_id] = AuthFlow(
                client=client,
                phone=phone,
                phone_code_hash=sent.phone_code_hash,
                created_at=time.monotonic(),
            )
            # The flow now owns the live client and will disconnect it on completion/expiry.
            client = None
            return _response(
                {
                    "ok": True,
                    "status": "code_sent",
                    "flow_id": flow_id,
                    "delivery": sent.type.__class__.__name__,
                }
            )
        except FloodWaitError as exc:
            return _error(f"Telegram rate limit. Retry after {exc.seconds} seconds.", 429)
        except Exception as exc:
            return _error(f"Could not start Telegram login: {type(exc).__name__}", 400)
        finally:
            if client is not None:
                try:
                    await client.disconnect()
                except Exception:
                    logger.warning("Could not disconnect failed Telegram login client", exc_info=True)

    @mcp.custom_route("/connect/code", methods=["POST"])
    async def connect_code(request: Request) -> Response:
        if not _authorized(request):
            return _error("Invalid connect key.", 401)
        await _prune_flows()
        flow_id = ""
        flow: AuthFlow | None = None
        try:
            body = await _json(request)
            flow_id = str(body.get("flow_id", ""))
            code = str(body.get("code", "")).strip().replace("-", "")
            flow = _flows.get(flow_id)
            if flow is None:
                return _error("Login attempt expired. Start again.", 410)
            if not code.isdigit() or not 4 <= len(code) <= 8:
                return _error("Enter the Telegram login code.")

            try:
                await flow.client.sign_in(
                    phone=flow.phone,
                    code=code,
                    phone_code_hash=flow.phone_code_hash,
                )
            except SessionPasswordNeededError:
                return _response({"ok": True, "status": "password_required", "flow_id": flow_id})
            except PhoneCodeInvalidError:
                return _error("Telegram says the code is invalid.")
            except PhoneCodeExpiredError:
                await _discard_flow(flow_id, flow)
                return _error("Telegram code expired. Start again.", 410)

            return await _finish_login(flow_id, flow, on_session_saved)
        except FloodWaitError as exc:
            await _discard_flow(flow_id, flow)
            return _error(f"Telegram rate limit. Retry after {exc.seconds} seconds.", 429)
        except Exception as exc:
            await _discard_flow(flow_id, flow)
            return _error(f"Could not complete Telegram login: {type(exc).__name__}", 400)

    @mcp.custom_route("/connect/password", methods=["POST"])
    async def connect_password(request: Request) -> Response:
        if not _authorized(request):
            return _error("Invalid connect key.", 401)
        await _prune_flows()
        flow_id = ""
        flow: AuthFlow | None = None
        try:
            body = await _json(request)
            flow_id = str(body.get("flow_id", ""))
            password = str(body.get("password", ""))
            flow = _flows.get(flow_id)
            if flow is None:
                return _error("Login attempt expired. Start again.", 410)
            if not password:
                return _error("Enter your Telegram 2FA password.")

            try:
                await flow.client.sign_in(password=password)
            except PasswordHashInvalidError:
                return _error("Telegram says the 2FA password is invalid.")

            return await _finish_login(flow_id, flow, on_session_saved)
        except FloodWaitError as exc:
            await _discard_flow(flow_id, flow)
            return _error(f"Telegram rate limit. Retry after {exc.seconds} seconds.", 429)
        except Exception as exc:
            await _discard_flow(flow_id, flow)
            return _error(f"Could not complete Telegram 2FA: {type(exc).__name__}", 400)


_CONNECT_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<title>Connect Telegram</title>
<style>
:root{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color-scheme:light dark}body{margin:0;background:#111827;color:#f9fafb;min-height:100vh;display:grid;place-items:center}.card{width:min(92vw,440px);background:#1f2937;border:1px solid #374151;border-radius:20px;padding:24px;box-sizing:border-box;box-shadow:0 20px 60px #0006}h1{margin:0 0 8px;font-size:28px}p{color:#cbd5e1;line-height:1.45}.field{margin:16px 0}label{display:block;font-size:13px;color:#cbd5e1;margin-bottom:6px}input{width:100%;box-sizing:border-box;padding:14px;border:1px solid #4b5563;border-radius:12px;background:#111827;color:#fff;font-size:16px}button{width:100%;padding:14px;border:0;border-radius:12px;background:#229ED9;color:#fff;font-size:16px;font-weight:700}button:disabled{opacity:.5}.hidden{display:none}.status{margin-top:14px;padding:12px;border-radius:12px;background:#111827;color:#d1d5db;white-space:pre-wrap}.ok{color:#86efac}.warn{color:#fbbf24}.small{font-size:12px;color:#94a3b8}</style>
</head>
<body>
<main class="card">
<h1>Connect Telegram</h1>
<p>Authorize your Telegram account for ChatGPT/Codex. Login codes and 2FA passwords are never shown back or stored by this page.</p>
<section id="step-start">
<div class="field"><label>Connect key</label><input id="token" type="password" autocomplete="off" placeholder="Private connect key"></div>
<div class="field"><label>Telegram phone</label><input id="phone" type="tel" autocomplete="tel" placeholder="+79991234567"></div>
<button id="start">Send Telegram code</button>
</section>
<section id="step-code" class="hidden">
<div class="field"><label>Telegram login code</label><input id="code" inputmode="numeric" autocomplete="one-time-code" placeholder="12345"></div>
<button id="verify">Verify code</button>
</section>
<section id="step-password" class="hidden">
<div class="field"><label>Telegram 2FA password</label><input id="password" type="password" autocomplete="current-password" placeholder="2FA password"></div>
<button id="verify-password">Complete connection</button>
</section>
<div id="status" class="status">Ready.</div>
<p class="small">Security: use this page only over HTTPS. The server must set TELEGRAM_CONNECT_TOKEN. The resulting Telegram session is a bearer credential and must stay on the server.</p>
</main>
<script>
let flowId=null;const $=id=>document.getElementById(id);const status=(text,ok=false)=>{$('status').textContent=text;$('status').className='status '+(ok?'ok':'')};
async function post(path,payload){const token=$('token').value;const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Telegram-Connect-Token':token},body:JSON.stringify(payload),cache:'no-store'});const data=await r.json();if(!r.ok||!data.ok)throw new Error(data.error||('HTTP '+r.status));return data}
$('start').onclick=async()=>{try{$('start').disabled=true;status('Requesting Telegram code…');const d=await post('/connect/start',{phone:$('phone').value});flowId=d.flow_id;$('step-start').classList.add('hidden');$('step-code').classList.remove('hidden');status('Code sent. Check Telegram and enter it here.');$('code').focus()}catch(e){status(e.message)}finally{$('start').disabled=false}};
$('verify').onclick=async()=>{try{$('verify').disabled=true;status('Checking code…');const d=await post('/connect/code',{flow_id:flowId,code:$('code').value});if(d.status==='password_required'){$('step-code').classList.add('hidden');$('step-password').classList.remove('hidden');status('Telegram 2FA is enabled. Enter your password.');$('password').focus()}else if(d.status==='connected'){done(d)}}catch(e){status(e.message)}finally{$('verify').disabled=false}};
$('verify-password').onclick=async()=>{try{$('verify-password').disabled=true;status('Checking 2FA…');const d=await post('/connect/password',{flow_id:flowId,password:$('password').value});if(d.status==='connected')done(d)}catch(e){status(e.message)}finally{$('verify-password').disabled=false}};
function done(d){$('step-code').classList.add('hidden');$('step-password').classList.add('hidden');$('password').value='';$('code').value='';$('token').value='';$('phone').value='';flowId=null;const u=d.user||{};status('Connected ✓\n'+(u.username?'@'+u.username:(u.first_name||'Telegram user')),true)}
</script>
</body>
</html>"""
