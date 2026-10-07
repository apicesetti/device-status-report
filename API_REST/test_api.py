#!/usr/bin/env python3
"""
Script para testear la API deviceStatus v2 (paginacion por cursor).

Respuesta del GET:
    {"items": [...], "count": n, "next_cursor": str|null}

Orden interno (no configurable por el cliente):
  - Sin date params    -> date DESC, __name__ DESC  (newest first)
  - Con date_from/to   -> date ASC,  __name__ ASC   (oldest first)
"""

import os
import requests
import json
from datetime import datetime, timedelta

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
TOKEN    = os.getenv("API_TEST_TOKEN", "")
HEADERS  = {"token": TOKEN}


def safe_json(response):
    """Devuelve el JSON de la respuesta, o un dict de error si no es JSON valido."""
    try:
        return response.json()
    except Exception:
        return {"_raw": response.text[:500]}


# ==================== TESTS ====================

def test_health():
    print("=" * 60)
    print("1. TEST: Health Check")
    print("=" * 60)
    r = requests.get(f"{BASE_URL}/health")
    body = safe_json(r)
    print(f"Status: {r.status_code}")
    print(f"firestore: {body.get('firestore')}")
    assert r.status_code == 200, f"Esperaba 200, got {r.status_code}"
    assert body.get("firestore") == "connected", f"Firestore no conectado: {body}"
    print("OK")
    print()


def test_validate_token():
    print("=" * 60)
    print("2. TEST: Validate Token")
    print("=" * 60)
    r = requests.post(f"{BASE_URL}/api/v1/auth/validate-token", headers=HEADERS)
    body = safe_json(r)
    print(f"Status: {r.status_code}")
    assert r.status_code == 200, f"Esperaba 200, got {r.status_code}: {body}"
    assert body.get("valid") is True
    print("OK")
    print()


def test_post_single():
    print("=" * 60)
    print("3. TEST: POST Un Documento")
    print("=" * 60)
    data = {"items": [{
        "myGeoDB": "zone_a",
        "deviceId": "device001",
        "name": "GPS Device 1",
        "licensePlate": "ABC123",
        "comm": True,
        "date": datetime.now().isoformat()
    }]}
    r = requests.post(f"{BASE_URL}/api/v1/deviceStatus", json=data, headers=HEADERS)
    body = safe_json(r)
    print(f"Status: {r.status_code}")
    assert r.status_code == 200, f"Esperaba 200: {body}"
    assert body["success"] == 1 and body["failed"] == 0
    print(f"Insertado: {body['results'][0]['id']}")
    print("OK")
    print()
    return body["results"][0]["id"]


def test_post_multiple():
    print("=" * 60)
    print("4. TEST: POST Multiples Documentos (con item invalido)")
    print("=" * 60)
    data = {"items": [
        {
            "myGeoDB": "zone_a",
            "deviceId": "device002",
            "name": "GPS Device 2",
            "licensePlate": "XYZ789",
            "comm": True,
            "date": datetime.now().isoformat()
        },
        {
            "myGeoDB": "zone_b",
            "deviceId": "device003",
            "name": "GPS Device 3",
            "licensePlate": "DEF456",
            "comm": False,
            "date": (datetime.now() - timedelta(days=1)).isoformat()
        },
        {
            # item invalido: deviceId vacio
            "myGeoDB": "zone_c",
            "deviceId": "",
            "name": "Bad Device",
            "licensePlate": "BAD999",
            "comm": True
        }
    ]}
    r = requests.post(f"{BASE_URL}/api/v1/deviceStatus", json=data, headers=HEADERS)
    body = safe_json(r)
    print(f"Status: {r.status_code}")
    assert r.status_code == 200, f"Esperaba 200: {body}"
    assert body["success"] == 2, f"Esperaba success=2, got {body['success']}"
    assert body["failed"] == 1,  f"Esperaba failed=1, got {body['failed']}"
    assert body["results"][2]["status"] == "error"
    print(f"success={body['success']}, failed={body['failed']} (esperado: 2/1)")
    print("OK")
    print()


def test_get_by_license_plate():
    print("=" * 60)
    print("5. TEST: GET por License Plate (sin date params -> newest first)")
    print("=" * 60)
    r = requests.get(
        f"{BASE_URL}/api/v1/deviceStatus",
        params={"licensePlate": "ABC123"},
        headers=HEADERS
    )
    body = safe_json(r)
    print(f"Status: {r.status_code}")
    assert r.status_code == 200, f"Esperaba 200: {body}"
    assert "items" in body,       f"Falta campo 'items': {body}"
    assert "count" in body,       f"Falta campo 'count': {body}"
    assert "next_cursor" in body, f"Falta campo 'next_cursor': {body}"
    items = body["items"]
    print(f"count={body['count']}, next_cursor={body['next_cursor']}")

    # Sin date params -> orden date DESC (non-increasing)
    if len(items) > 1:
        dates = []
        for it in items:
            d = it.get("date")
            if d:
                dates.append(d)
        for i in range(len(dates) - 1):
            assert dates[i] >= dates[i+1], (
                f"Orden esperado DESC (newest first), pero [{i}]={dates[i]} < [{i+1}]={dates[i+1]}"
            )
        print("Orden date DESC verificado")
    print("OK")
    print()
    return items


def test_get_by_comm_and_date():
    print("=" * 60)
    print("6. TEST: GET por Comm y Fecha (con date_from -> oldest first)")
    print("=" * 60)
    date_from = (datetime.now() - timedelta(days=7)).isoformat()
    r = requests.get(
        f"{BASE_URL}/api/v1/deviceStatus",
        params={"comm": "true", "date_from": date_from},
        headers=HEADERS
    )
    body = safe_json(r)
    print(f"Status: {r.status_code}")
    assert r.status_code == 200, f"Esperaba 200: {body}"
    assert "items" in body
    items = body["items"]
    print(f"count={body['count']}, next_cursor={body['next_cursor']}")

    # Con date params -> orden date ASC (non-decreasing)
    if len(items) > 1:
        dates = []
        for it in items:
            d = it.get("date")
            if d:
                dates.append(d)
        for i in range(len(dates) - 1):
            assert dates[i] <= dates[i+1], (
                f"Orden esperado ASC (oldest first), pero [{i}]={dates[i]} > [{i+1}]={dates[i+1]}"
            )
        print("Orden date ASC verificado")
    print("OK")
    print()


def test_get_by_id(doc_id=None):
    print("=" * 60)
    print("7. TEST: GET por ID")
    print("=" * 60)
    if doc_id is None:
        # Buscar uno via GET lista
        r = requests.get(
            f"{BASE_URL}/api/v1/deviceStatus",
            params={"licensePlate": "ABC123"},
            headers=HEADERS
        )
        list_body = safe_json(r)
        items = list_body.get("items", [])
        if not items:
            print("SKIP: no hay documentos disponibles")
            print()
            return
        doc_id = items[0]["id"]

    print(f"Usando ID: {doc_id}")
    r = requests.get(f"{BASE_URL}/api/v1/deviceStatus/{doc_id}", headers=HEADERS)
    body = safe_json(r)
    print(f"Status: {r.status_code}")
    assert r.status_code == 200, f"Esperaba 200: {body}"
    assert body.get("id") == doc_id
    print("OK")
    print()


def test_invalid_token():
    print("=" * 60)
    print("8. TEST: Token Invalido")
    print("=" * 60)
    r = requests.get(
        f"{BASE_URL}/api/v1/deviceStatus",
        params={"licensePlate": "ABC123"},
        headers={"token": "invalid-token"}
    )
    body = safe_json(r)
    print(f"Status: {r.status_code}")
    assert r.status_code == 401, f"Esperaba 401, got {r.status_code}: {body}"
    print("OK")
    print()


def test_pagination():
    """
    Test 9: paginacion con limit=1.
    Itera por todas las paginas y verifica que no haya IDs duplicados.
    Verifica el orden segun el modo (con/sin date params).
    """
    print("=" * 60)
    print("9. TEST: Paginacion (limit=1, sin date -> DESC)")
    print("=" * 60)

    # ---- Modo sin date: orden DESC (newest first) ----
    all_ids = []
    all_dates = []
    cursor = None
    page = 0

    while True:
        params = {"licensePlate": "ABC123", "limit": 1}
        if cursor:
            params["cursor"] = cursor

        r = requests.get(
            f"{BASE_URL}/api/v1/deviceStatus",
            params=params,
            headers=HEADERS
        )
        body = safe_json(r)
        assert r.status_code == 200, f"Paginacion DESC page {page}: status={r.status_code}: {body}"
        items = body.get("items", [])
        next_cursor = body.get("next_cursor")

        if not items:
            break

        for it in items:
            all_ids.append(it["id"])
            d = it.get("date")
            if d:
                all_dates.append(d)

        page += 1
        print(f"  Pagina {page}: id={items[0]['id'][:12]}... next_cursor={'si' if next_cursor else 'no'}")

        if not next_cursor:
            break

        cursor = next_cursor

    assert len(all_ids) == len(set(all_ids)), (
        f"IDs duplicados en paginacion DESC: {[x for x in all_ids if all_ids.count(x) > 1]}"
    )
    # Orden non-increasing
    for i in range(len(all_dates) - 1):
        assert all_dates[i] >= all_dates[i+1], (
            f"Orden DESC roto en pagina {i}: {all_dates[i]} > {all_dates[i+1]}"
        )
    print(f"  Total docs: {len(all_ids)}, sin duplicados, orden DESC verificado")

    # ---- Modo con date_from: orden ASC (oldest first) ----
    print()
    print("9b. TEST: Paginacion (limit=1, con date_from -> ASC)")
    date_from = (datetime.now() - timedelta(days=7)).isoformat()
    all_ids_asc = []
    all_dates_asc = []
    cursor = None
    page = 0

    while True:
        params = {"comm": "true", "date_from": date_from, "limit": 1}
        if cursor:
            params["cursor"] = cursor

        r = requests.get(
            f"{BASE_URL}/api/v1/deviceStatus",
            params=params,
            headers=HEADERS
        )
        body = safe_json(r)
        assert r.status_code == 200, f"Paginacion ASC page {page}: {r.status_code}: {body}"
        items = body.get("items", [])
        next_cursor = body.get("next_cursor")

        if not items:
            break

        for it in items:
            all_ids_asc.append(it["id"])
            d = it.get("date")
            if d:
                all_dates_asc.append(d)

        page += 1
        print(f"  Pagina {page}: id={items[0]['id'][:12]}... next_cursor={'si' if next_cursor else 'no'}")

        if not next_cursor:
            break

        cursor = next_cursor

    assert len(all_ids_asc) == len(set(all_ids_asc)), "IDs duplicados en paginacion ASC"
    for i in range(len(all_dates_asc) - 1):
        assert all_dates_asc[i] <= all_dates_asc[i+1], (
            f"Orden ASC roto: {all_dates_asc[i]} > {all_dates_asc[i+1]}"
        )
    print(f"  Total docs: {len(all_ids_asc)}, sin duplicados, orden ASC verificado")
    print("OK")
    print()


# ==================== MAIN ====================

if __name__ == "__main__":
    print("\n")
    print("=" * 60)
    print("  TESTS API v2 - deviceStatus (cursor pagination)")
    print("=" * 60)
    print()

    failures = []

    def run(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except AssertionError as e:
            print(f"  FALLO: {e}")
            failures.append(fn.__name__)
        except Exception as e:
            print(f"  ERROR: {e}")
            failures.append(fn.__name__)

    inserted_id = run(test_health)
    run(test_validate_token)
    inserted_id = run(test_post_single)
    run(test_post_multiple)
    items = run(test_get_by_license_plate)
    run(test_get_by_comm_and_date)
    doc_id = (items[0]["id"] if items else None) if items else None
    run(test_get_by_id, doc_id)
    run(test_invalid_token)
    run(test_pagination)

    print("=" * 60)
    if failures:
        print(f"FALLARON: {failures}")
    else:
        print("TODOS LOS TESTS PASARON")
    print("=" * 60)
