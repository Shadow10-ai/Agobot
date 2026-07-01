"""WebSocket endpoint — authenticated real-time bot updates."""
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from jose import JWTError, jwt
from config import SECRET_KEY, ALGORITHM
from services.websocket_manager import ws_manager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    """
    Authenticated WebSocket endpoint.
    Client connects via:  ws(s)://<host>/api/ws?token=<jwt>
    Broadcasts scan_update messages every bot scan cycle (~10s).
    """
    # Validate JWT before accepting the connection
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=1008)
            return
    except JWTError:
        await websocket.close(code=1008)
        return

    await ws_manager.connect(websocket)
    try:
        # Keep connection alive; client can send pings ("ping") to prevent timeout
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
