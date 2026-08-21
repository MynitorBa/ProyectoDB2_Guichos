# Diagrama Entidad-Relación — TiendaYa

El siguiente diagrama cubre todas las tablas del modelo relacional en MySQL 8. Las cardinalidades usan la notación estándar de Mermaid (`||`, `|{`, `}|`, etc.).

```mermaid
erDiagram
    usuarios {
        INT usuario_id PK
        VARCHAR nombre
        VARCHAR email
        VARCHAR password_hash
        BOOLEAN activo
        TIMESTAMP creado_en
        TIMESTAMP actualizado_en
    }

    roles {
        INT rol_id PK
        VARCHAR nombre
        VARCHAR descripcion
    }

    usuario_rol {
        INT usuario_id FK
        INT rol_id FK
        TIMESTAMP asignado_en
    }

    direcciones {
        INT direccion_id PK
        INT usuario_id FK
        VARCHAR calle
        VARCHAR ciudad
        VARCHAR departamento
        VARCHAR pais
        VARCHAR codigo_postal
        BOOLEAN es_principal
    }

    vendedores {
        INT vendedor_id PK
        INT usuario_id FK
        VARCHAR nombre_tienda
        VARCHAR nit
        VARCHAR telefono
        TEXT descripcion
        BOOLEAN verificado
        TIMESTAMP creado_en
    }

    categorias {
        INT categoria_id PK
        INT padre_id FK
        VARCHAR nombre
        TEXT descripcion
        VARCHAR slug
    }

    productos {
        INT producto_id PK
        INT vendedor_id FK
        INT categoria_id FK
        VARCHAR nombre
        TEXT descripcion
        DECIMAL precio
        CHAR mongo_id
        BOOLEAN activo
        TIMESTAMP creado_en
        TIMESTAMP actualizado_en
    }

    producto_imagenes {
        INT imagen_id PK
        INT producto_id FK
        VARCHAR url
        BOOLEAN es_principal
        INT orden
    }

    inventario {
        INT inventario_id PK
        INT producto_id FK
        INT cantidad_disponible
        INT cantidad_reservada
        INT stock_minimo
        TIMESTAMP actualizado_en
    }

    movimientos_inventario {
        INT movimiento_id PK
        INT inventario_id FK
        INT usuario_id FK
        ENUM tipo
        INT cantidad
        VARCHAR referencia
        TEXT notas
        TIMESTAMP creado_en
    }

    pedidos {
        INT pedido_id PK
        INT usuario_id FK
        INT direccion_id FK
        ENUM estado
        DECIMAL subtotal
        DECIMAL impuestos
        DECIMAL total
        TIMESTAMP creado_en
        TIMESTAMP actualizado_en
    }

    pedido_lineas {
        INT linea_id PK
        INT pedido_id FK
        CHAR producto_ref
        VARCHAR producto_nombre
        INT cantidad
        DECIMAL precio_unitario
        DECIMAL subtotal_linea
    }

    pagos {
        INT pago_id PK
        INT pedido_id FK
        INT metodo_pago_id FK
        DECIMAL monto
        ENUM estado
        VARCHAR referencia_externa
        TIMESTAMP procesado_en
    }

    metodos_pago {
        INT metodo_pago_id PK
        VARCHAR nombre
        VARCHAR proveedor
        BOOLEAN activo
    }

    resenas {
        INT resena_id PK
        INT usuario_id FK
        INT producto_id FK
        INT puntuacion
        TEXT comentario
        BOOLEAN verificada
        TIMESTAMP creado_en
    }

    carritos {
        INT carrito_id PK
        INT usuario_id FK
        TIMESTAMP creado_en
        TIMESTAMP actualizado_en
    }

    carrito_items {
        INT item_id PK
        INT carrito_id FK
        CHAR producto_ref
        INT cantidad
        DECIMAL precio_capturado
        TIMESTAMP agregado_en
    }

    usuarios ||--o{ usuario_rol : "tiene"
    roles ||--o{ usuario_rol : "asignado a"

    usuarios ||--o{ direcciones : "registra"

    usuarios ||--o| vendedores : "opera como"

    categorias ||--o{ categorias : "contiene (padre_id)"

    vendedores ||--o{ productos : "publica"
    categorias ||--o{ productos : "clasifica"

    productos ||--o{ producto_imagenes : "tiene"

    productos ||--|| inventario : "controlado por"
    inventario ||--o{ movimientos_inventario : "registra"

    movimientos_inventario }o--|| usuarios : "ejecutado por"

    usuarios ||--o{ pedidos : "realiza"
    direcciones ||--o{ pedidos : "destino de"

    pedidos ||--o{ pedido_lineas : "contiene"

    pedidos ||--o{ pagos : "liquidado con"
    metodos_pago ||--o{ pagos : "usado en"

    usuarios ||--o{ resenas : "escribe"
    productos ||--o{ resenas : "recibe"

    usuarios ||--o| carritos : "posee"
    carritos ||--o{ carrito_items : "contiene"
```

## Notas sobre el diagrama

**Relación `categorias` auto-referenciada:** La columna `padre_id` apunta a la misma tabla `categorias`. Esto permite modelar la jerarquía de dos niveles del catálogo — por ejemplo, `electrónica` es padre de `computadoras`, `celulares` y `audio`. Mermaid lo representa como un loop sobre la misma entidad.

**`producto_ref` en `pedido_lineas` y `carrito_items`:** Esta columna de tipo `CHAR(24)` guarda el ObjectId de MongoDB del producto. No existe FK formal porque MySQL no puede referenciar MongoDB, pero la relación lógica es clara. La documentación del cruce entre bases de datos está en `07-referencia-sql-mongo.md`.

**`mongo_id` en `productos`:** La tabla `productos` de MySQL guarda también el ObjectId de su contraparte en la colección `catalogo` de MongoDB. Esto permite joins a nivel de aplicación entre el registro MySQL (precio, stock, vendedor_id) y el documento MongoDB (atributos variables, imágenes, historial de eventos).

**Cardinalidades destacadas:**
- Un usuario tiene exactamente un carrito (`||--o|`), pero puede tener cero o muchos pedidos (`||--o{`).
- Un producto tiene exactamente un registro de inventario (`||--||`), modelado como 1:1 estricto.
- Un vendedor puede tener cero productos al inicio (`||--o{`), lo que permite onboarding sin publicar de inmediato.
