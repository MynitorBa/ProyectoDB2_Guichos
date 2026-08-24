// =============================================================================
// TiendaYa — Inicialización de colecciones MongoDB
// Este script se ejecuta automáticamente al arrancar el contenedor de Mongo.
// Crea las colecciones con validación de esquema (JSON Schema) y la colección
// categoria_esquemas que alimenta los formularios dinámicos del panel admin.
// =============================================================================

const db = db.getSiblingDB('tiendaya');

// ─── Colección: productos ─────────────────────────────────────────────────────
db.createCollection('productos', {
  validator: {
    $jsonSchema: {
      bsonType: 'object',
      required: ['sku', 'nombre', 'precio', 'categoria', 'estado'],
      properties: {
        sku:       { bsonType: 'string' },
        nombre:    { bsonType: 'string' },
        precio:    { bsonType: ['double', 'decimal', 'int'] },
        categoria: {
          bsonType: 'object',
          required: ['slug', 'nombre'],
          properties: {
            slug:   { bsonType: 'string' },
            nombre: { bsonType: 'string' }
          }
        },
        estado: {
          bsonType: 'string',
          enum: ['activo', 'inactivo', 'borrador', 'descontinuado']
        }
      }
    }
  },
  validationLevel: 'moderate'
});

// ─── Colección: producto_eventos (append-only) ────────────────────────────────
db.createCollection('producto_eventos', {
  validator: {
    $jsonSchema: {
      bsonType: 'object',
      required: ['producto_id', 'tipo_evento', 'timestamp', 'version'],
      properties: {
        producto_id: { bsonType: 'string' },
        tipo_evento: {
          bsonType: 'string',
          enum: [
            'PRODUCTO_CREADO',
            'PRECIO_ACTUALIZADO',
            'DESCRIPCION_ACTUALIZADA',
            'DISPONIBILIDAD_CAMBIADA',
            'ATRIBUTOS_ACTUALIZADOS',
            'PRODUCTO_DESCONTINUADO'
          ]
        },
        timestamp: { bsonType: 'date' },
        version:   { bsonType: 'int' }
      }
    }
  }
});

// ─── Colección: categoria_esquemas ───────────────────────────────────────────
// Alimenta el formulario dinámico: al seleccionar una categoría, el frontend
// pide GET /api/v1/categories/{slug}/schema y construye los campos del formulario.
db.createCollection('categoria_esquemas');

db.categoria_esquemas.insertMany([
  {
    categoria_slug: 'computadoras',
    categoria_nombre: 'Computadoras',
    atributos: [
      { nombre: 'procesador',     tipo: 'string',  requerido: true,  etiqueta: 'Procesador',       placeholder: 'Ej: Intel Core i5-1235U' },
      { nombre: 'ram_gb',         tipo: 'number',  requerido: true,  etiqueta: 'RAM (GB)',          placeholder: 'Ej: 8' },
      { nombre: 'almacenamiento', tipo: 'string',  requerido: true,  etiqueta: 'Almacenamiento',   placeholder: 'Ej: 512GB SSD' },
      { nombre: 'pulgadas',       tipo: 'number',  requerido: true,  etiqueta: 'Tamaño pantalla (pulgadas)', placeholder: 'Ej: 15.6' },
      { nombre: 'sistema_op',     tipo: 'string',  requerido: false, etiqueta: 'Sistema operativo', placeholder: 'Ej: Windows 11' },
      { nombre: 'color',          tipo: 'string',  requerido: false, etiqueta: 'Color',             placeholder: 'Ej: Plateado' }
    ]
  },
  {
    categoria_slug: 'celulares',
    categoria_nombre: 'Celulares',
    atributos: [
      { nombre: 'ram_gb',         tipo: 'number',  requerido: true,  etiqueta: 'RAM (GB)',          placeholder: 'Ej: 6' },
      { nombre: 'almacenamiento', tipo: 'string',  requerido: true,  etiqueta: 'Almacenamiento',   placeholder: 'Ej: 128GB' },
      { nombre: 'camara_mp',      tipo: 'number',  requerido: true,  etiqueta: 'Cámara principal (MP)', placeholder: 'Ej: 50' },
      { nombre: 'pulgadas',       tipo: 'number',  requerido: true,  etiqueta: 'Tamaño pantalla (pulgadas)', placeholder: 'Ej: 6.4' },
      { nombre: 'sistema_op',     tipo: 'string',  requerido: false, etiqueta: 'Sistema operativo', placeholder: 'Ej: Android 13' },
      { nombre: 'color',          tipo: 'string',  requerido: false, etiqueta: 'Color',             placeholder: 'Ej: Negro' }
    ]
  },
  {
    categoria_slug: 'audio',
    categoria_nombre: 'Audio',
    atributos: [
      { nombre: 'tipo_audio',      tipo: 'string', requerido: true,  etiqueta: 'Tipo',              placeholder: 'Ej: Over-ear, In-ear, Bocina' },
      { nombre: 'conectividad',    tipo: 'string', requerido: true,  etiqueta: 'Conectividad',      placeholder: 'Ej: Bluetooth 5.2, 3.5mm jack' },
      { nombre: 'bateria_horas',   tipo: 'number', requerido: false, etiqueta: 'Batería (horas)',   placeholder: 'Ej: 30' },
      { nombre: 'cancelacion_ruido', tipo: 'boolean', requerido: false, etiqueta: 'Cancelación de ruido activa', placeholder: '' },
      { nombre: 'color',           tipo: 'string', requerido: false, etiqueta: 'Color',             placeholder: 'Ej: Negro' }
    ]
  },
  {
    categoria_slug: 'camisas',
    categoria_nombre: 'Camisas',
    atributos: [
      { nombre: 'talla',     tipo: 'string', requerido: true,  etiqueta: 'Talla',    placeholder: 'Ej: S, M, L, XL, XXL' },
      { nombre: 'color',     tipo: 'string', requerido: true,  etiqueta: 'Color',    placeholder: 'Ej: Azul marino' },
      { nombre: 'material',  tipo: 'string', requerido: true,  etiqueta: 'Material', placeholder: 'Ej: 100% algodón' },
      { nombre: 'genero',    tipo: 'string', requerido: true,  etiqueta: 'Género',   placeholder: 'Hombre / Mujer / Unisex' },
      { nombre: 'corte',     tipo: 'string', requerido: false, etiqueta: 'Corte',    placeholder: 'Ej: Slim fit, Regular' },
      { nombre: 'manga',     tipo: 'string', requerido: false, etiqueta: 'Manga',    placeholder: 'Ej: Larga, Corta' }
    ]
  },
  {
    categoria_slug: 'pantalones',
    categoria_nombre: 'Pantalones',
    atributos: [
      { nombre: 'talla',     tipo: 'string', requerido: true,  etiqueta: 'Talla (cintura)', placeholder: 'Ej: 28, 30, 32, 34' },
      { nombre: 'color',     tipo: 'string', requerido: true,  etiqueta: 'Color',           placeholder: 'Ej: Azul índigo' },
      { nombre: 'material',  tipo: 'string', requerido: true,  etiqueta: 'Material',        placeholder: 'Ej: 98% algodón 2% elastano' },
      { nombre: 'corte',     tipo: 'string', requerido: true,  etiqueta: 'Corte',           placeholder: 'Ej: Slim fit, Skinny, Regular' },
      { nombre: 'genero',    tipo: 'string', requerido: true,  etiqueta: 'Género',          placeholder: 'Hombre / Mujer / Unisex' }
    ]
  },
  {
    categoria_slug: 'calzado',
    categoria_nombre: 'Calzado',
    atributos: [
      { nombre: 'talla',     tipo: 'number', requerido: true,  etiqueta: 'Talla (EU)',   placeholder: 'Ej: 42' },
      { nombre: 'color',     tipo: 'string', requerido: true,  etiqueta: 'Color',        placeholder: 'Ej: Blanco' },
      { nombre: 'material',  tipo: 'string', requerido: true,  etiqueta: 'Material',     placeholder: 'Ej: Cuero sintético' },
      { nombre: 'genero',    tipo: 'string', requerido: true,  etiqueta: 'Género',       placeholder: 'Hombre / Mujer / Unisex' },
      { nombre: 'tipo_suela',tipo: 'string', requerido: false, etiqueta: 'Tipo de suela',placeholder: 'Ej: Goma, Cuero' }
    ]
  },
  {
    categoria_slug: 'libros',
    categoria_nombre: 'Libros',
    atributos: [
      { nombre: 'autor',     tipo: 'string', requerido: true,  etiqueta: 'Autor',       placeholder: 'Nombre del autor' },
      { nombre: 'isbn',      tipo: 'string', requerido: true,  etiqueta: 'ISBN',        placeholder: 'Ej: 978-0132350884' },
      { nombre: 'paginas',   tipo: 'number', requerido: true,  etiqueta: 'Páginas',     placeholder: 'Ej: 431' },
      { nombre: 'editorial', tipo: 'string', requerido: true,  etiqueta: 'Editorial',   placeholder: 'Ej: Prentice Hall' },
      { nombre: 'idioma',    tipo: 'string', requerido: false, etiqueta: 'Idioma',      placeholder: 'Ej: Español, Inglés' },
      { nombre: 'genero_literario', tipo: 'string', requerido: false, etiqueta: 'Género literario', placeholder: 'Ej: Ficción, Técnico, Educativo' }
    ]
  },
  {
    categoria_slug: 'deportes',
    categoria_nombre: 'Deportes',
    atributos: [
      { nombre: 'deporte',  tipo: 'string', requerido: true,  etiqueta: 'Deporte',            placeholder: 'Ej: Fútbol, Natación, Ciclismo' },
      { nombre: 'talla',    tipo: 'string', requerido: false, etiqueta: 'Talla / Tamaño',     placeholder: 'Ej: M, L, Talla 5' },
      { nombre: 'material', tipo: 'string', requerido: false, etiqueta: 'Material',           placeholder: 'Ej: Cuero sintético, Poliamida' },
      { nombre: 'genero',   tipo: 'string', requerido: false, etiqueta: 'Género',             placeholder: 'Hombre / Mujer / Unisex' },
      { nombre: 'color',    tipo: 'string', requerido: false, etiqueta: 'Color',              placeholder: 'Ej: Negro/Rosa' }
    ]
  },
  {
    categoria_slug: 'alimentos',
    categoria_nombre: 'Alimentos',
    atributos: [
      { nombre: 'peso_g',        tipo: 'number',  requerido: true,  etiqueta: 'Peso (g)',         placeholder: 'Ej: 500' },
      { nombre: 'origen',        tipo: 'string',  requerido: false, etiqueta: 'Origen / Región',  placeholder: 'Ej: Huehuetenango, Guatemala' },
      { nombre: 'apto_vegano',   tipo: 'boolean', requerido: false, etiqueta: 'Apto para veganos',placeholder: '' },
      { nombre: 'sin_gluten',    tipo: 'boolean', requerido: false, etiqueta: 'Sin gluten',       placeholder: '' },
      { nombre: 'ingredientes',  tipo: 'string',  requerido: false, etiqueta: 'Ingredientes principales', placeholder: 'Ej: Café, Agua' }
    ]
  },
  {
    categoria_slug: 'juguetes',
    categoria_nombre: 'Juguetes',
    atributos: [
      { nombre: 'edad_minima',   tipo: 'number', requerido: true,  etiqueta: 'Edad mínima (años)', placeholder: 'Ej: 3' },
      { nombre: 'num_piezas',    tipo: 'number', requerido: false, etiqueta: 'Número de piezas',   placeholder: 'Ej: 126' },
      { nombre: 'material',      tipo: 'string', requerido: false, etiqueta: 'Material',           placeholder: 'Ej: Plástico ABS, Madera' },
      { nombre: 'requiere_pilas',tipo: 'boolean',requerido: false, etiqueta: '¿Requiere pilas?',   placeholder: '' },
      { nombre: 'genero',        tipo: 'string', requerido: false, etiqueta: 'Orientado a',        placeholder: 'Niño / Niña / Unisex' }
    ]
  },
  {
    categoria_slug: 'herramientas',
    categoria_nombre: 'Herramientas',
    atributos: [
      { nombre: 'potencia_w',    tipo: 'number', requerido: false, etiqueta: 'Potencia (W)',      placeholder: 'Ej: 750' },
      { nombre: 'voltaje',       tipo: 'string', requerido: false, etiqueta: 'Voltaje',           placeholder: 'Ej: 120V / 18V batería' },
      { nombre: 'uso',           tipo: 'string', requerido: true,  etiqueta: 'Uso principal',     placeholder: 'Ej: Carpintería, Electricidad' },
      { nombre: 'incluye',       tipo: 'string', requerido: false, etiqueta: 'Incluye',           placeholder: 'Ej: Maletín, 2 brocas, guía' },
      { nombre: 'garantia_meses',tipo: 'number', requerido: false, etiqueta: 'Garantía (meses)',  placeholder: 'Ej: 12' }
    ]
  },
  {
    categoria_slug: 'hogar',
    categoria_nombre: 'Hogar',
    atributos: [
      { nombre: 'material',      tipo: 'string', requerido: false, etiqueta: 'Material',          placeholder: 'Ej: Acero inoxidable, MDF' },
      { nombre: 'color',         tipo: 'string', requerido: false, etiqueta: 'Color',             placeholder: 'Ej: Negro, Nogal' },
      { nombre: 'dimensiones',   tipo: 'string', requerido: false, etiqueta: 'Dimensiones',       placeholder: 'Ej: 60x90cm, 140x100cm' },
      { nombre: 'potencia_w',    tipo: 'number', requerido: false, etiqueta: 'Potencia (W)',      placeholder: 'Ej: 600' },
      { nombre: 'incluye',       tipo: 'string', requerido: false, etiqueta: 'Incluye',           placeholder: 'Ej: Set 5 piezas, con tapa' }
    ]
  }
]);

print('TiendaYa: colecciones e inicializadas correctamente.');
