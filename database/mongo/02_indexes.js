// =============================================================================
// TiendaYa — Índices MongoDB
// =============================================================================

const db = db.getSiblingDB('tiendaya');

// ─── Colección: productos ─────────────────────────────────────────────────────

// Índice único sobre SKU. Garantiza unicidad equivalente a MySQL.
db.productos.createIndex(
  { sku: 1 },
  { unique: true, name: 'uidx_sku' }
);

// Índice compuesto principal del catálogo.
// Consulta que lo justifica:
//   db.productos.find({ "categoria.slug": "electronica", disponible: true })
//               .sort({ precio: -1 })
// El prefijo "categoria.slug + disponible" filtra la partición de datos y
// "precio" permite ordenar sin SORT en memoria. Sin este índice, un filtro por
// categoría requeriría un full-scan de toda la colección.
db.productos.createIndex(
  { "categoria.slug": 1, disponible: 1, precio: -1 },
  { name: 'idx_catalogo_categoria_disponible_precio' }
);

// Índice de texto para búsqueda full-text en el buscador del frontend.
// Consulta: db.productos.find({ $text: { $search: "laptop procesador ryzen" } })
db.productos.createIndex(
  { nombre: 'text', descripcion: 'text' },
  { name: 'idx_texto_nombre_descripcion', default_language: 'spanish' }
);

// Índice para filtro por estado (activo/borrador/descontinuado) en el panel admin.
db.productos.createIndex(
  { estado: 1 },
  { name: 'idx_estado' }
);

// Índice sobre vendedor_id para listar catálogo de un vendedor.
db.productos.createIndex(
  { vendedor_id: 1, estado: 1 },
  { name: 'idx_vendedor_estado' }
);

// Índice sobre rango de precio (para filtros de precio min-max en el catálogo).
db.productos.createIndex(
  { precio: 1 },
  { name: 'idx_precio' }
);

// ─── Colección: producto_eventos ─────────────────────────────────────────────

// Índice compuesto para reconstrucción de estado: filtrar por producto y ordenar
// por timestamp. Esta es la consulta más frecuente del historial:
//   db.producto_eventos.find({ producto_id: "..." }).sort({ timestamp: 1 })
db.producto_eventos.createIndex(
  { producto_id: 1, timestamp: -1 },
  { name: 'idx_eventos_producto_timestamp' }
);

// Índice por tipo de evento, útil para auditoría ("dame todos los cambios de precio").
db.producto_eventos.createIndex(
  { tipo_evento: 1, timestamp: -1 },
  { name: 'idx_eventos_tipo_timestamp' }
);

// Garantiza que reintentar un mensaje del outbox no duplique el historial.
db.producto_eventos.createIndex(
  { outbox_id: 1 },
  { unique: true, sparse: true, name: 'uidx_evento_outbox' }
);

// ─── Colección: categoria_esquemas ───────────────────────────────────────────
db.categoria_esquemas.createIndex(
  { categoria_slug: 1 },
  { unique: true, name: 'uidx_esquema_slug' }
);

print('TiendaYa: índices creados correctamente.');
