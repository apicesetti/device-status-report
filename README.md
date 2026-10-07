# Device Status Report

Sistema para registrar y consultar el estado de dispositivos GPS (comunicación, ubicación, placas) almacenado en Firestore, expuesto vía una API REST con autenticación por token y paginación por cursor.

## Estructura

```
device-status-report/
├── API_REST/                # API FastAPI (principal)
│   ├── api_main.py          # Servidor FastAPI
│   ├── test_api.py          # Tests de integración
│   ├── .env.example         # Template de variables de entorno
│   ├── tokens.example.json  # Plantilla de tokens de acceso
│   ├── requirements_api.txt # Dependencias Python
│   ├── Dockerfile.api       # Imagen Docker
│   └── API_README.md        # Documentación detallada de la API
├── scripts/                 # Utilidades de despliegue
│   ├── backend_windows.py   # Launcher para VM Windows (clona repo + lanza API)
│   └── README.md            # Instrucciones de uso del launcher
└── README.md                # Este archivo
```

## Inicio rápido

```bash
cd API_REST
pip install -r requirements_api.txt
cp .env.example
cp tokens.example.json tokens.json
# Editar .env y tokens.json con los valores reales
python api_main.py
```

La API queda disponible en `http://localhost:8000`. Documentación interactiva en `/docs`.

## Despliegue en VM Windows

Para levantar la API en una máquina Windows sin configuración manual del entorno,
usar el launcher incluido. Ver [scripts/README.md](scripts/README.md).

## Documentación completa

Ver [API_REST/API_README.md](API_REST/API_README.md).
