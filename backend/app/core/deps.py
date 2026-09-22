from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.db_mysql import get_db
from app.core.db_mongo import get_mongo_db
from app.core.security import decode_token
from app.models.usuario import Usuario

bearer_scheme = HTTPBearer()
bearer_scheme_optional = HTTPBearer(auto_error=False)


# Valida el JWT del header Authorization y devuelve el usuario activo de la BD
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Usuario:
    payload = decode_token(credentials.credentials)
    user_id: int | None = payload.get('sub')
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Token inválido')

    user = db.get(Usuario, int(user_id))
    if not user or user.estado != 'activo':
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Usuario no encontrado o inactivo')
    return user


# Fábrica de dependencias: genera un Depends que exige uno de los roles indicados
def require_role(*roles: str):
    def dependency(current_user: Usuario = Depends(get_current_user)) -> Usuario:
        user_roles = {r.nombre for r in current_user.roles}
        if not user_roles.intersection(roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f'Se requiere uno de los roles: {", ".join(roles)}'
            )
        return current_user
    return dependency


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme_optional),
    db: Session = Depends(get_db),
) -> Usuario | None:
    if not credentials:
        return None
    try:
        payload = decode_token(credentials.credentials)
        user_id = payload.get('sub')
        if not user_id:
            return None
        user = db.get(Usuario, int(user_id))
        return user if user and user.estado == 'activo' else None
    except Exception:
        return None


def get_admin_user(current_user: Usuario = Depends(require_role('administrador'))) -> Usuario:
    return current_user


def get_mongo(db=Depends(get_mongo_db)):
    return db


from app.core.db_neo4j import get_neo4j as _get_neo4j_session
from neo4j import Session as Neo4jSession

def get_neo4j() -> Neo4jSession:
    yield from _get_neo4j_session()
