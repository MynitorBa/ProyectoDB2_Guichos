#!/bin/sh
# Arranca Redis con el control de acceso de database/redis/acl.conf.
# Las contraseñas vienen del entorno (archivo .env de la raíz, fuera del repositorio);
# si falta alguna, Redis no arranca: no hay modo «sin contraseña».
set -eu

for variable in REDIS_API_PASSWORD REDIS_LECTURA_PASSWORD REDIS_ADMIN_PASSWORD; do
  eval "valor=\${$variable:-}"
  if [ -z "$valor" ]; then
    echo "Falta $variable. Ejecute scripts/setup.ps1 para generar las contraseñas de Redis en .env." >&2
    exit 1
  fi
done

ACL=/tmp/users.acl
grep -v '^\s*#' /etc/redis/acl.conf | grep -v '^\s*$' \
  | sed -e "s|^user default on |user default on >${REDIS_LECTURA_PASSWORD} |" \
        -e "s|^user tiendaya_api on |user tiendaya_api on >${REDIS_API_PASSWORD} |" \
        -e "s|^user tiendaya_lectura on |user tiendaya_lectura on >${REDIS_LECTURA_PASSWORD} |" \
        -e "s|^user tiendaya_admin on |user tiendaya_admin on >${REDIS_ADMIN_PASSWORD} |" > "$ACL"
chmod 600 "$ACL"

exec redis-server --save 60 1 --loglevel warning --aclfile "$ACL" "$@"
