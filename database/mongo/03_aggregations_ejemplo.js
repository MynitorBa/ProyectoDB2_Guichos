// =============================================================================
// TiendaYa — Ejemplo de Aggregation Framework
// Endpoint: GET /api/v1/admin/stats/catalog
//
// Este pipeline produce un reporte por categoría con:
//   - precio promedio, mínimo y máximo
//   - conteo total de productos y cuántos están disponibles
//   - top 3 productos por precio en esa categoría
//
// Stages usados: $match, $facet, $group, $sort, $lookup, $project
// =============================================================================

const db = db.getSiblingDB('tiendaya');

const pipeline = [
  // 1. Sólo productos activos
  { $match: { estado: 'activo' } },

  // 2. $facet permite calcular múltiples agregaciones en paralelo sobre el mismo set
  {
    $facet: {

      // Facet A: estadísticas por categoría
      estadisticas_por_categoria: [
        {
          $group: {
            _id: '$categoria.slug',
            categoria_nombre: { $first: '$categoria.nombre' },
            total_productos:  { $sum: 1 },
            disponibles:      { $sum: { $cond: ['$disponible', 1, 0] } },
            precio_promedio:  { $avg: '$precio' },
            precio_minimo:    { $min: '$precio' },
            precio_maximo:    { $max: '$precio' }
          }
        },
        { $sort: { total_productos: -1 } },
        {
          $project: {
            _id: 0,
            slug: '$_id',
            categoria_nombre: 1,
            total_productos: 1,
            disponibles: 1,
            precio_promedio: { $round: ['$precio_promedio', 2] },
            precio_minimo: 1,
            precio_maximo: 1
          }
        }
      ],

      // Facet B: top 5 productos más caros del catálogo completo
      top_productos_precio: [
        { $sort: { precio: -1 } },
        { $limit: 5 },
        {
          $project: {
            _id: 1,
            sku: 1,
            nombre: 1,
            precio: 1,
            categoria: '$categoria.nombre',
            disponible: 1
          }
        }
      ],

      // Facet C: conteo global
      resumen_global: [
        {
          $group: {
            _id: null,
            total_productos:    { $sum: 1 },
            total_disponibles:  { $sum: { $cond: ['$disponible', 1, 0] } },
            precio_promedio_global: { $avg: '$precio' }
          }
        },
        {
          $project: {
            _id: 0,
            total_productos: 1,
            total_disponibles: 1,
            precio_promedio_global: { $round: ['$precio_promedio_global', 2] }
          }
        }
      ]
    }
  }
];

// Correr desde mongosh para ver resultado:
// db.productos.aggregate(pipeline).toArray()
const resultado = db.productos.aggregate(pipeline).toArray();
printjson(resultado);
