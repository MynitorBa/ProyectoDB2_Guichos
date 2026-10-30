// Control de acceso de MongoDB (Entrega final): un usuario por servicio, con mínimo privilegio.
//
// Idempotente: crea o actualiza el rol y los usuarios. Lo ejecuta Docker al crear el volumen
// (docker-entrypoint-initdb.d) y scripts/configurar-acceso.ps1 en instalaciones existentes.
// Las contraseñas vienen del entorno del contenedor (archivo .env de la raíz, fuera del repositorio).

const base = db.getSiblingDB(process.env.MONGO_INITDB_DATABASE || 'tiendaya');

const contrasenas = {
  tiendaya_api: process.env.MONGO_API_PASSWORD,
  tiendaya_lectura: process.env.MONGO_LECTURA_PASSWORD,
  tiendaya_admin: process.env.MONGO_ADMIN_PASSWORD,
};
for (const [usuario, clave] of Object.entries(contrasenas)) {
  if (!clave) {
    throw new Error(`Falta la contraseña de ${usuario}. Ejecute scripts/generar-credenciales.ps1.`);
  }
}

// Las colecciones que usa el backend y solo lo que hace con ellas: leer, escribir, borrar
// documentos y crear sus índices al arrancar (db_mongo.ensure_indexes). Sin drop, sin
// dropDatabase, sin crear usuarios ni roles, sin la colección de migraciones y sin otras bases.
const COLECCIONES_APP = ['productos', 'producto_variantes', 'producto_eventos', 'categoria_esquemas', 'tiendas_config'];
const ACCIONES_APP = ['find', 'insert', 'update', 'remove', 'createIndex', 'listIndexes'];
const rolApp = {
  privileges: COLECCIONES_APP.map(c => ({ resource: { db: base.getName(), collection: c }, actions: ACCIONES_APP })),
  roles: [],
};
if (base.getRole('tiendaya_aplicacion')) {
  base.updateRole('tiendaya_aplicacion', rolApp);
} else {
  base.createRole({ role: 'tiendaya_aplicacion', ...rolApp });
}

const usuarios = {
  // Backend (API y workers).
  tiendaya_api: [{ role: 'tiendaya_aplicacion', db: base.getName() }],
  // Mongo Express y diagnóstico: solo lectura de esta base.
  tiendaya_lectura: [{ role: 'read', db: base.getName() }],
  // Instalación y migraciones: dueño de esta base, sin acceso a las demás ni al servidor.
  tiendaya_admin: [{ role: 'dbOwner', db: base.getName() }],
};
for (const [usuario, roles] of Object.entries(usuarios)) {
  if (base.getUser(usuario)) {
    base.updateUser(usuario, { pwd: contrasenas[usuario], roles });
  } else {
    base.createUser({ user: usuario, pwd: contrasenas[usuario], roles });
  }
}
print(`Usuarios de ${base.getName()}: ${Object.keys(usuarios).join(', ')}`);
