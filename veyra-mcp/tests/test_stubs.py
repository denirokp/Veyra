"""Smoke-тест skeleton veyra-mcp.

На Фазе 1 проверяем ровно две вещи: health отвечает, инструменты
возвращают корректные заглушки. Реальной логики нет — её и не тестируем.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_check_initiative_stub():
    r = client.post("/tools/check_initiative", json={"text": "пример инициативы"})
    assert r.status_code == 200
    body = r.json()
    assert body["stub"] is True
    assert body["tool"] == "check_initiative"
    assert body["echo"]["text_len"] == len("пример инициативы")


def test_find_contradictions_stub():
    r = client.post("/tools/find_contradictions", json={"doc_id": "doc-42"})
    assert r.status_code == 200
    assert r.json()["stub"] is True


def test_search_corpus_stub():
    r = client.post("/tools/search_corpus", json={"query": "выручка", "top_k": 3})
    assert r.status_code == 200
    assert r.json()["echo"]["top_k"] == 3


def test_get_document_stub():
    r = client.post("/tools/get_document", json={"doc_id": "doc-7"})
    assert r.status_code == 200
    assert r.json()["stub"] is True


def test_unknown_tool_404():
    r = client.post("/tools/nonexistent", json={})
    assert r.status_code == 404
