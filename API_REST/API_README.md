# API REST - Device Status

API FastAPI para gestionar datos de `deviceStatus` en Firestore con autenticación por token, validaciones, rate limits y filtros flexibles.

## 🚀 Características

✅ **Autenticación**: Token-based (archivo local JSON)  
✅ **Rate Limiting**: Configurable por endpoint (GET/POST)  
✅ **Filtros Flexibles**: Múltiples combinaciones (licensePlate, comm, deviceId, myGeoDB, etc.)  
✅ **Validaciones**: Por elemento en POST con feedback detallado  
✅ **Paginación**: Límite configurable de resultados  
✅ **Logging**: Completo para debugging  
✅ **Documentación**: Swagger automático en `/docs`  
✅ **Rate Limit info**: Por cliente IP  

---

## 📋 Requisitos

```bash
pip install -r requirements_api.txt
```

O manual:
```bash
pip install fastapi uvicorn pydantic google-cloud-firestore google-auth python-dotenv
```

---

## 🔧 Setup

### 1. Descargar credenciales Firebase

```bash
# Copiar firebase-key.json a la carpeta raíz
cp /ruta/a/firebase-key.json .
```

### 2. Crear archivo de tokens

```bash
# Copiar la plantilla y reemplazar con tokens reales
cp tokens.example.json tokens.json
# Editar tokens.json y agregar tus tokens válidos (NO commitear)
```

### 3. Variables de entorno

```bash
cp .env.example .env
# Editar .env según sea necesario
```

---

## 🏃 Ejecutar

### Desarrollo (localhost)

```bash
python api_main.py
```

La API estará en: `http://localhost:8000`

Documentación interactiva: `http://localhost:8000/docs`

### Producción (VM con IP pública)

```bash
# Cambiar puerto si es necesario
PORT=8000 python api_main.py

# O con gunicorn (más robusto)
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 api_main:app
```

### Docker

```bash
docker build -f Dockerfile.api -t device-status-api .
docker run -p 8000:8000 \
  -e FIREBASE_PROJECT_ID=device-status-report \
  -e FIREBASE_CREDENTIALS_PATH=/app/firebase-key.json \
  device-status-api
```

---

## 📡 Endpoints

### Health Check

```bash
GET /health
```

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2026-10-07T10:30:00",
  "firestore": "connected"
}
```

---

### Validar Token

```bash
POST /api/v1/auth/validate-token
Headers: token: <tu-token>
```

**Response:**
```json
{
  "valid": true,
  "message": "Token válido"
}
```

---

### GET Documentos (Filtros + Paginación por cursor)

```bash
GET /api/v1/deviceStatus?licensePlate=ABC123&limit=50
Headers: token: <tu-token>
```

**Query Parameters:**
- `myGeoDB` (string): Zona geográfica
- `deviceId` (string): ID del dispositivo
- `licensePlate` (string): Placa de licencia
- `comm` (boolean): Estado de comunicación (`true`/`false`)
- `name` (string): Nombre del dispositivo
- `date_from` (ISO 8601): Fecha mínima
- `date_to` (ISO 8601): Fecha máxima
- `limit` (int): Tamaño de página (default: 100, max: 1000)
- `cursor` (string): ID del último doc de la página anterior (para paginar)

**Restricciones:**
- Se requiere al menos un filtro.
- Máximo **un campo de igualdad** por query (myGeoDB, deviceId, licensePlate, comm, name). Combinar dos retorna 400.
- El orden es interno y no configurable:
  - Sin `date_from`/`date_to` → **date DESC** (newest first)
  - Con `date_from` y/o `date_to` → **date ASC** (oldest first dentro del rango)

**Response:**
```json
{
  "items": [
    {
      "id": "doc_123abc",
      "myGeoDB": "zone_a",
      "deviceId": "device_001",
      "name": "GPS Device 1",
      "licensePlate": "ABC123",
      "comm": true,
      "date": "2026-10-07T10:00:00",
      "inserted": "2026-10-07T09:59:00"
    }
  ],
  "count": 1,
  "next_cursor": null
}
```

Si `next_cursor != null`, pasarlo como `?cursor=<valor>` con los mismos filtros para la página siguiente.

---

### POST Documentos (Múltiples)

```bash
POST /api/v1/deviceStatus
Headers: token: <tu-token>
Content-Type: application/json

{
  "items": [
    {
      "myGeoDB": "zone_a",
      "deviceId": "device_001",
      "name": "GPS Device 1",
      "licensePlate": "ABC123",
      "comm": true,
      "date": "2026-10-07T10:00:00"
    },
    {
      "myGeoDB": "zone_b",
      "deviceId": "device_002",
      "name": "GPS Device 2",
      "licensePlate": "XYZ789",
      "comm": false
    }
  ]
}
```

**Response:**
```json
{
  "total": 2,
  "success": 1,
  "failed": 1,
  "results": [
    {
      "index": 0,
      "status": "success",
      "id": "doc_abc123",
      "message": "Documento insertado: doc_abc123"
    },
    {
      "index": 1,
      "status": "error",
      "id": null,
      "message": "Error: Campo 'deviceId' es requerido"
    }
  ]
}
```

---

### GET por ID

```bash
GET /api/v1/deviceStatus/doc_abc123
Headers: token: <tu-token>
```

**Response:**
```json
{
  "id": "doc_abc123",
  "myGeoDB": "zone_a",
  "deviceId": "device_001",
  "name": "GPS Device 1",
  "licensePlate": "ABC123",
  "comm": true,
  "date": "2026-10-07T10:00:00",
  "inserted": "2026-10-07T09:59:00"
}
```

---

## 🔐 Autenticación

Todos los endpoints (excepto `/health`) requieren un header `token`:

```bash
curl -H "token: <tu-token>" http://localhost:8000/api/v1/deviceStatus
```

Los tokens válidos se definen en `tokens.json`.

---

## 🚦 Rate Limiting

### GET: 60 requests/minuto
### POST: 30 requests/minuto

Si se excede:
```json
{
  "error": "Rate limit excedido. Máximo 60 requests/minuto"
}
```

Rate limit se calcula **por IP del cliente**.

---

## 📊 Ejemplos de Uso

### Obtener últimos 10 documentos de una placa

```bash
curl -H "token: <tu-token>" \
  "http://localhost:8000/api/v1/deviceStatus?licensePlate=ABC123&limit=10"
```

### Obtener documentos de la última semana con comm=true

```bash
curl -H "token: <tu-token>" \
  "http://localhost:8000/api/v1/deviceStatus?comm=true&date_from=2026-09-30T00:00:00"
```

### Insertar múltiples dispositivos

```bash
curl -X POST -H "token: <tu-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {
        "myGeoDB": "zone_a",
        "deviceId": "device_001",
        "name": "Device 1",
        "licensePlate": "ABC123",
        "comm": true
      }
    ]
  }' \
  http://localhost:8000/api/v1/deviceStatus
```

---

## 🧪 Testing

El script lee el token y la URL desde variables de entorno:

```bash
export API_TEST_TOKEN=sk-tu-token-real   # token válido en tokens.json
export API_BASE_URL=http://localhost:8000  # opcional, default: localhost:8000
python test_api.py
```

Esto ejecuta 8 tests:
1. Health check
2. Validación de token
3. POST un documento
4. POST múltiples documentos (incluyendo errores)
5. GET por licensePlate
6. GET por comm y rango de fechas
7. GET por ID
8. Token inválido (401)

---

## 📝 Logging

Los logs se escriben en stdout:

```
INFO:__main__:✅ Firestore conectado
INFO:__main__:✅ GET: 5 documentos encontrados (IP: 192.168.1.100)
INFO:__main__:✅ POST: 2/3 éxito (IP: 192.168.1.100)
```

---

## 🐛 Troubleshooting

### Error: 403 SERVICE_DISABLED

Firestore no está habilitado. Ve a:
```
https://console.cloud.google.com/apis/api/firestore.googleapis.com/overview?project=device-status-report
```

### Error: 401 Token inválido

El token no está en `tokens.json` o es incorrecto. Verifica:
```bash
cat tokens.json
```

### Error: RATE_LIMIT_GET excedido

Se alcanzó el límite de 60 requests/minuto. Espera o cambia en `.env`:
```
RATE_LIMIT_GET=120
```

---

## 📦 Estructura

```
.
├── api_main.py              # Código principal
├── firebase-key.json        # Credenciales (NO commitear — ignorado en .gitignore)
├── tokens.json              # Tokens válidos (NO commitear — ignorado en .gitignore)
├── tokens.example.json      # Plantilla de tokens (copiar a tokens.json)
├── .env                     # Variables de entorno (NO commitear — ignorado en .gitignore)
├── .env.example             # Template .env (incluido en repo)
├── requirements_api.txt     # Dependencias Python
├── test_api.py              # Script de tests
├── Dockerfile.api           # Para Docker
└── API_README.md            # Este archivo
```

---

## 🔗 Integración con Backend VM

El backend en la VM puede consumir esta API así:

```python
import requests

class APIClient:
    def __init__(self, base_url, token):
        self.base_url = base_url
        self.token = token
    
    def get_by_license_plate(self, plate):
        headers = {"token": self.token}
        params = {"licensePlate": plate}
        response = requests.get(
            f"{self.base_url}/api/v1/deviceStatus",
            headers=headers,
            params=params
        )
        return response.json()
    
    def insert(self, items):
        headers = {"token": self.token}
        response = requests.post(
            f"{self.base_url}/api/v1/deviceStatus",
            headers=headers,
            json={"items": items}
        )
        return response.json()

# Uso
client = APIClient("http://<IP_SERVIDOR>:8000", "sk-vm-device-status-001")
docs = client.get_by_license_plate("ABC123")
```

---

## 📞 Support

Para preguntas o problemas, revisar logs en la API:
```bash
tail -f api.log
```

---

**Versión:** 1.0.0  
**Última actualización:** 2026-10-08

---

## 🐍 Compatibilidad Python

- **Python 3.11** (Docker, desarrollo local)
- **Python 3.14** (VM de producción, cp314-win_amd64) — todas las dependencias tienen wheels binarios precompilados; no se requieren compiladores C/Rust.

Versiones de dependencias directas:

| Paquete | Versión |
|---|---|
| fastapi | 0.115.12 |
| uvicorn | 0.34.3 |
| pydantic | 2.14.0 |
| google-cloud-firestore | 2.20.2 |
| google-auth | 2.40.1 |
| python-dotenv | 1.1.0 |
