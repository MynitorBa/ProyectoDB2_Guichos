from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db_mysql import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.core.deps import get_current_user
from app.models.usuario import Usuario, Rol, UsuarioRol
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserResponse, ProfileUpdateRequest

router = APIRouter(prefix='/auth', tags=['Auth'])


# Registra un nuevo usuario y le asigna el rol 'comprador' por defecto
@router.post('/register', response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(Usuario).filter_by(email=payload.email).first():
        raise HTTPException(status_code=400, detail='El email ya está registrado.')

    rol_comprador = db.query(Rol).filter_by(nombre='comprador').first()
    if not rol_comprador:
        raise HTTPException(status_code=500, detail='Rol comprador no encontrado.')

    usuario = Usuario(
        email=payload.email,
        password_hash=hash_password(payload.password),
        nombre=payload.nombre,
        apellido=payload.apellido,
        telefono=payload.telefono,
    )
    db.add(usuario)
    db.flush()
    db.add(UsuarioRol(usuario_id=usuario.id, rol_id=rol_comprador.id))
    db.commit()
    db.refresh(usuario)

    return UserResponse(
        id=usuario.id,
        email=usuario.email,
        nombre=usuario.nombre,
        apellido=usuario.apellido,
        roles=[r.nombre for r in usuario.roles],
        estado=usuario.estado,
    )


# Valida credenciales y devuelve un JWT; rechaza cuentas inactivas o suspendidas
@router.post('/login', response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter_by(email=payload.email).first()
    if not usuario or not verify_password(payload.password, usuario.password_hash):
        raise HTTPException(status_code=401, detail='Credenciales incorrectas.')
    if usuario.estado != 'activo':
        raise HTTPException(status_code=403, detail='Cuenta inactiva o suspendida.')

    token = create_access_token({'sub': str(usuario.id)})
    return TokenResponse(access_token=token)


# Devuelve el perfil completo del usuario autenticado incluyendo sus roles
@router.get('/me', response_model=UserResponse)
def me(current_user: Usuario = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        nombre=current_user.nombre,
        apellido=current_user.apellido,
        telefono=current_user.telefono,
        roles=[r.nombre for r in current_user.roles],
        estado=current_user.estado,
    )


# Emite un nuevo token con fecha de expiración renovada sin necesidad de re-autenticar
@router.post('/refresh', response_model=TokenResponse)
def refresh(current_user: Usuario = Depends(get_current_user)):
    token = create_access_token({'sub': str(current_user.id)})
    return TokenResponse(access_token=token)


# Actualiza nombre, apellido y teléfono del usuario autenticado (el email no cambia)
@router.put('/me', response_model=UserResponse)
def update_me(
    payload: ProfileUpdateRequest,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.nombre = payload.nombre
    current_user.apellido = payload.apellido
    current_user.telefono = payload.telefono
    db.commit()
    db.refresh(current_user)
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        nombre=current_user.nombre,
        apellido=current_user.apellido,
        telefono=current_user.telefono,
        roles=[r.nombre for r in current_user.roles],
        estado=current_user.estado,
    )
