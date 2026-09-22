"""Conexión singleton a Neo4j para el grafo de reseñas."""
from __future__ import annotations
import threading
from neo4j import GraphDatabase, Driver
from app.core.config import settings

_driver: Driver | None = None
_lock = threading.Lock()

def get_driver() -> Driver:
    global _driver
    if _driver is not None:
        return _driver
    with _lock:
        if _driver is not None:
            return _driver
        _driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        _driver.verify_connectivity()
        _ensure_constraints(_driver)
    return _driver

def _ensure_constraints(driver: Driver) -> None:
    with driver.session() as s:
        s.run("CREATE CONSTRAINT usuario_id IF NOT EXISTS FOR (u:Usuario) REQUIRE u.id IS UNIQUE")
        s.run("CREATE CONSTRAINT producto_ref IF NOT EXISTS FOR (p:Producto) REQUIRE p.ref IS UNIQUE")
        s.run("CREATE CONSTRAINT vendedor_id IF NOT EXISTS FOR (v:Vendedor) REQUIRE v.id IS UNIQUE")
        s.run("CREATE CONSTRAINT resena_id IF NOT EXISTS FOR (r:Reseña) REQUIRE r.id IS UNIQUE")

def close_driver() -> None:
    global _driver
    if _driver:
        _driver.close()
        _driver = None

def get_neo4j():
    """FastAPI dependency — yields a Neo4j session."""
    with get_driver().session() as session:
        yield session

def neo4j_health() -> dict:
    info = get_driver().get_server_info()
    return {"version": info.agent, "address": info.address}
