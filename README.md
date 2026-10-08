# Device Status Report

Sistema para registrar y consultar el estado de dispositivos GPS (comunicación, ubicación, placas) almacenado en Firestore, expuesto vía una API REST con autenticación por token y paginación por cursor.

## Estructura

```
device-status-report/
├── API_REST/                # API FastAPI (principal)
│   ├── api_main.py          # Servidor FastAPI
│   ├── .env.example         # Template de variables de entorno
│   ├── tokens.example.json  # Plantilla de tokens de acceso
│   ├── requirements_api.txt # Dependencias Python
│   ├── Dockerfile.api       # Imagen Docker
│   └── API_README.md        # Documentación detallada de la API
└── README.md                # Este archivo
```

## Inicio rápido

```bash
cd API_REST
pip install -r requirements_api.txt
cp .env.example .env
cp tokens.example.json tokens.json
# Editar .env y tokens.json con los valores reales
python api_main.py
```

La API queda disponible en `http://localhost:8000`. Documentación interactiva en `/docs`.

## Documentación completa

Ver [API_REST/API_README.md](API_REST/API_README.md).
