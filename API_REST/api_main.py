#!/usr/bin/env python3
"""
API REST para deviceStatus - FastAPI
Endpoints con autenticación token, validaciones, rate limits, filtros flexibles
y paginación por cursor.
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
import time

from fastapi import FastAPI, HTTPException, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, ValidationError
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.oauth2 import service_account

# ==================== CONFIGURACIÓN ====================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).parent

app = FastAPI(
    title="Device Status API",
    version="2.0.0",
    description=(
        "API para gestionar deviceStatus con Firestore. "
        "Paginación por cursor. Orden interno fijo: date ASC, __name__ ASC."
    ),
)

PROJECT_ID   = os.getenv("FIREBASE_PROJECT_ID",  "device-status-report")
DATABASE_ID  = os.getenv("FIREBASE_DATABASE_ID", "device-status-report")
RESULTS_LIMIT = int(os.getenv("RESULTS_LIMIT", 1000))
RATE_LIMIT_GET  = int(os.getenv("RATE_LIMIT_GET",  60))
RATE_LIMIT_POST = int(os.getenv("RATE_LIMIT_POST", 30))


def _resolve_credentials_path() -> str:
    env_val = os.getenv("FIREBASE_CREDENTIALS_PATH", "")
    if env_val:
        p = Path(env_val)
        return str(p if p.is_absolute() else _BASE_DIR / env_val)
    for candidate in [
        _BASE_DIR / "firebase-key.json",
        _BASE_DIR.parent / "FIREBASE" / "firebase-key.json",
    ]:
        if candidate.exists():
            return str(candidate)
    return str(_BASE_DIR / "firebase-key.json")  # fallback explícito


CREDENTIALS_PATH = _resolve_credentials_path()

_tokens_env = os.getenv("TOKENS_PATH", "tokens.json")
TOKENS_PATH = str(
    Path(_tokens_env) if Path(_tokens_env).is_absolute()
    else _BASE_DIR / _tokens_env
)

# Campos que admiten filtro de igualdad (uno a la vez como máximo)
EQUALITY_FIELDS = {"myGeoDB", "deviceId", "licensePlate", "comm", "name"}

# ==================== FIRESTORE CLIENT ====================

class FirestoreClient:
    def __init__(self):
        credentials = service_account.Credentials.from_service_account_file(
            CREDENTIALS_PATH
        )
        self.db = firestore.Client(
            credentials=credentials,
            project=PROJECT_ID,
            database=DATABASE_ID,
        )
        self.collection = "deviceStatus"
        logger.info(
            f"Firestore: project={PROJECT_ID}, database={DATABASE_ID}, "
            f"collection={self.collection}, creds={CREDENTIALS_PATH}"
        )

    def get_documents(
        self,
        filters: Dict[str, Any],
        limit: int,
        cursor_doc_id: Optional[str] = None,
    ) -> List[Dict]:
        """
        Consulta con filtros, paginación por cursor y orden determinista:

        - Sin date_from/date_to → date DESC, __name__ DESC  (newest first)
        - Con date_from y/o date_to → date ASC, __name__ ASC (oldest first)

        El orden NO es configurable por el cliente; se deriva de los parámetros
        de fecha presentes. El cursor (doc id) debe reutilizarse con los mismos
        filtros para mantener coherencia de dirección.

        Restricción: máximo UN campo de igualdad por query.
        Índices compuestos requeridos (ambas direcciones para cada campo):
            <equality_field> ASC | date DESC | __name__ DESC
            <equality_field> ASC | date ASC  | __name__ ASC
        """
        # Validar que no se combinen múltiples igualdades
        equality_used = [k for k in filters if k in EQUALITY_FIELDS]
        if len(equality_used) > 1:
            raise ValueError(
                f"Solo se permite UN campo de igualdad por query. "
                f"Se recibieron: {equality_used}."
            )

        query = self.db.collection(self.collection)

        # Filtro de igualdad (máximo uno)
        for field in equality_used:
            query = query.where(filter=FieldFilter(field, "==", filters[field]))

        # Rango de fechas
        has_date_range = "date_from" in filters or "date_to" in filters
        if "date_from" in filters:
            query = query.where(filter=FieldFilter("date", ">=", filters["date_from"]))
        if "date_to" in filters:
            query = query.where(filter=FieldFilter("date", "<=", filters["date_to"]))

        # Orden determinista según presencia de filtro de fecha
        if has_date_range:
            # Con rango: oldest → newest (ASC)
            direction = firestore.Query.ASCENDING
        else:
            # Sin rango: newest → oldest (DESC)
            direction = firestore.Query.DESCENDING

        query = (query
                 .order_by("date",     direction=direction)
                 .order_by("__name__", direction=direction))

        # Cursor: start_after con el snapshot del último doc de la página previa
        if cursor_doc_id:
            snap = self.db.collection(self.collection).document(cursor_doc_id).get()
            if snap.exists:
                query = query.start_after(snap)
            # Si el doc ya no existe, ignoramos el cursor (devuelve desde el inicio)

        # limit+1 para detectar si hay página siguiente
        query = query.limit(limit + 1)
        docs = list(query.stream())

        return [{"id": doc.id, **doc.to_dict()} for doc in docs]

    def insert_document(self, data: Dict[str, Any]) -> str:
        doc_ref = self.db.collection(self.collection).document()
        doc_ref.set(data)
        return doc_ref.id

    def get_by_id(self, doc_id: str) -> Optional[Dict]:
        doc = self.db.collection(self.collection).document(doc_id).get()
        if doc.exists:
            return {"id": doc.id, **doc.to_dict()}
        return None


try:
    fs_client = FirestoreClient()
    logger.info("Firestore conectado correctamente")
except Exception as e:
    logger.error(f"Error conectando Firestore: {e}")
    fs_client = None

# ==================== TOKENS ====================

def load_tokens() -> List[str]:
    try:
        with open(TOKENS_PATH, "r") as f:
            return json.load(f).get("tokens", [])
    except FileNotFoundError:
        logger.warning(f"TOKENS_PATH no encontrado: {TOKENS_PATH}")
        return []

valid_tokens = load_tokens()

# ==================== RATE LIMITING ====================

class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, List[float]] = {}

    def is_allowed(self, identifier: str) -> bool:
        now = time.time()
        cutoff = now - self.window_seconds
        bucket = self.requests.setdefault(identifier, [])
        self.requests[identifier] = [ts for ts in bucket if ts > cutoff]
        if len(self.requests[identifier]) >= self.max_requests:
            return False
        self.requests[identifier].append(now)
        return True

limiter_get  = RateLimiter(RATE_LIMIT_GET)
limiter_post = RateLimiter(RATE_LIMIT_POST)

# ==================== MODELOS ====================

class DeviceStatusCreate(BaseModel):
    myGeoDB:      str            = Field(..., min_length=1)
    deviceId:     str            = Field(..., min_length=1)
    name:         str            = Field(..., min_length=1)
    licensePlate: str            = Field(..., min_length=1)
    comm:         bool
    date:         Optional[datetime] = None

    @field_validator("licensePlate")
    @classmethod
    def validate_license_plate(cls, v):
        if len(v) < 2:
            raise ValueError("licensePlate debe tener al menos 2 caracteres")
        return v.upper()

    @field_validator("deviceId")
    @classmethod
    def validate_device_id(cls, v):
        if not v.isalnum():
            raise ValueError("deviceId solo puede contener letras y números")
        return v


class InsertResultItem(BaseModel):
    index:   int
    status:  str
    id:      Optional[str] = None
    message: str


class InsertResponse(BaseModel):
    total:   int
    success: int
    failed:  int
    results: List[InsertResultItem]


class DeviceStatusBatchRequest(BaseModel):
    # Acepta raw dicts para validar per-item en el loop
    items: List[Dict[str, Any]]


class DeviceStatusListResponse(BaseModel):
    """Respuesta paginada del GET /api/v1/deviceStatus"""
    items:       List[Dict[str, Any]]
    count:       int
    next_cursor: Optional[str]  # doc id del último ítem; None si no hay más páginas


# ==================== HELPERS ====================

def _firestore_error_detail(e: Exception) -> tuple[int, str]:
    """Convierte excepciones de Firestore en (http_status, mensaje)."""
    msg = str(e)
    if "FAILED_PRECONDITION" in msg or "requires an index" in msg.lower():
        link = ""
        if "https://" in msg:
            link = msg[msg.find("https://"):].strip()
        detail = "Esta query requiere un índice compuesto en Firestore."
        if link:
            detail += f" Crealo aquí: {link}"
        return 503, detail
    if "PERMISSION_DENIED" in msg or "403" in msg:
        return 503, f"Error de permisos en Firestore: {msg[:200]}"
    return 500, msg


# ==================== ENDPOINTS ====================

@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status":    "ok",
        "timestamp": datetime.now().isoformat(),
        "firestore": "connected" if fs_client else "disconnected",
    }


@app.post("/api/v1/auth/validate-token", tags=["Auth"])
async def validate_token(token: str = Header(...)):
    if token in valid_tokens:
        return {"valid": True, "message": "Token válido"}
    raise HTTPException(status_code=401, detail="Token inválido")


@app.get("/api/v1/deviceStatus", tags=["DeviceStatus"], response_model=DeviceStatusListResponse)
async def get_device_status(
    request:      Request,
    token:        str            = Header(...),
    myGeoDB:      Optional[str]  = Query(None),
    deviceId:     Optional[str]  = Query(None),
    licensePlate: Optional[str]  = Query(None),
    comm:         Optional[bool] = Query(None),
    name:         Optional[str]  = Query(None),
    date_from:    Optional[datetime] = Query(None, description="Fecha mínima (ISO 8601)"),
    date_to:      Optional[datetime] = Query(None, description="Fecha máxima (ISO 8601)"),
    limit:        int            = Query(100, ge=1, le=RESULTS_LIMIT),
    cursor:       Optional[str]  = Query(None, description="ID del último doc de la página anterior"),
):
    """
    GET con filtros y paginación por cursor.

    Orden interno (no configurable por el cliente):
    - Sin date_from/date_to → date DESC, __name__ DESC (newest first)
    - Con date_from y/o date_to → date ASC, __name__ ASC (oldest first)

    Máximo un campo de igualdad por query (myGeoDB, deviceId, licensePlate, comm, name).
    Combinar dos o más retorna 400.

    Respuesta: {"items": [...], "count": n, "next_cursor": str|null}
    Si next_cursor != null, pasarlo como ?cursor=<valor> con los MISMOS filtros
    para obtener la página siguiente.
    """
    if token not in valid_tokens:
        raise HTTPException(status_code=401, detail="Token inválido")

    client_ip = request.client.host
    if not limiter_get.is_allowed(client_ip):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit excedido. Máximo {RATE_LIMIT_GET} requests/minuto",
        )

    # Construir filtros (solo los que no son None)
    filters: Dict[str, Any] = {}
    if myGeoDB      is not None: filters["myGeoDB"]      = myGeoDB
    if deviceId     is not None: filters["deviceId"]     = deviceId
    if licensePlate is not None: filters["licensePlate"] = licensePlate
    if comm         is not None: filters["comm"]         = comm
    if name         is not None: filters["name"]         = name
    if date_from    is not None: filters["date_from"]    = date_from
    if date_to      is not None: filters["date_to"]      = date_to

    if not filters:
        raise HTTPException(status_code=400, detail="Debe proporcionar al menos un filtro")

    # Validar: máximo 1 campo de igualdad
    equality_used = [k for k in filters if k in EQUALITY_FIELDS]
    if len(equality_used) > 1:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Solo se permite UN campo de igualdad por query. "
                f"Se recibieron: {equality_used}."
            ),
        )

    if fs_client is None:
        raise HTTPException(status_code=503, detail="Firestore no disponible")

    try:
        raw_docs = fs_client.get_documents(filters, limit=limit, cursor_doc_id=cursor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        status, detail = _firestore_error_detail(e)
        logger.error(f"Error en GET: {e}")
        raise HTTPException(status_code=status, detail=detail)

    # Detectar si hay página siguiente (pedimos limit+1)
    has_next = len(raw_docs) > limit
    page_docs = raw_docs[:limit]
    next_cursor = page_docs[-1]["id"] if has_next and page_docs else None

    logger.info(f"GET: {len(page_docs)} docs, next_cursor={'si' if next_cursor else 'no'} (IP: {client_ip})")
    return DeviceStatusListResponse(
        items=page_docs,
        count=len(page_docs),
        next_cursor=next_cursor,
    )


@app.post("/api/v1/deviceStatus", tags=["DeviceStatus"], response_model=InsertResponse)
async def create_device_status(
    request: Request,
    token:   str = Header(...),
    body:    DeviceStatusBatchRequest = None,
):
    """
    POST batch. Body: {"items": [...]}
    Valida cada item por separado; items inválidos → results[i].status="error".
    """
    if token not in valid_tokens:
        raise HTTPException(status_code=401, detail="Token inválido")

    client_ip = request.client.host
    if not limiter_post.is_allowed(client_ip):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit excedido. Máximo {RATE_LIMIT_POST} requests/minuto",
        )

    if fs_client is None:
        raise HTTPException(status_code=503, detail="Firestore no disponible")

    raw_items = body.items if body else None
    if not raw_items:
        raise HTTPException(status_code=400, detail="Se requiere al menos un elemento")

    results: List[InsertResultItem] = []
    success_count = 0
    failed_count  = 0

    for idx, raw in enumerate(raw_items):
        try:
            item = DeviceStatusCreate(**raw)
            doc_data = {
                "myGeoDB":      item.myGeoDB,
                "deviceId":     item.deviceId,
                "name":         item.name,
                "licensePlate": item.licensePlate,
                "comm":         item.comm,
                "date":         item.date or datetime.now(),
                "inserted":     firestore.SERVER_TIMESTAMP,
            }
            doc_id = fs_client.insert_document(doc_data)
            results.append(InsertResultItem(
                index=idx, status="success", id=doc_id,
                message=f"Documento insertado: {doc_id}",
            ))
            success_count += 1
        except (ValidationError, ValueError) as e:
            failed_count += 1
            if isinstance(e, ValidationError):
                msgs = "; ".join(
                    f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}"
                    for err in e.errors()
                )
            else:
                msgs = str(e)
            results.append(InsertResultItem(
                index=idx, status="error", message=f"Validación: {msgs}",
            ))
        except Exception as e:
            failed_count += 1
            results.append(InsertResultItem(
                index=idx, status="error", message=f"Error: {str(e)}",
            ))

    logger.info(f"POST: {success_count}/{len(raw_items)} éxito (IP: {client_ip})")
    return InsertResponse(
        total=len(raw_items),
        success=success_count,
        failed=failed_count,
        results=results,
    )


@app.get("/api/v1/deviceStatus/{doc_id}", tags=["DeviceStatus"])
async def get_device_status_by_id(doc_id: str, token: str = Header(...)):
    """Obtiene un documento específico por ID"""
    if token not in valid_tokens:
        raise HTTPException(status_code=401, detail="Token inválido")

    if fs_client is None:
        raise HTTPException(status_code=503, detail="Firestore no disponible")

    try:
        doc = fs_client.get_by_id(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Documento no encontrado")
        return doc
    except HTTPException:
        raise
    except Exception as e:
        status, detail = _firestore_error_detail(e)
        logger.error(f"Error en GET by ID: {e}")
        raise HTTPException(status_code=status, detail=detail)


# ==================== ERROR HANDLING ====================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "timestamp": datetime.now().isoformat()},
    )


# ==================== MAIN ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        log_level="info",
    )
