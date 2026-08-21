# Referencia Cruzada entre MySQL y MongoDB — pedido_lineas y el catálogo

## El problema de la referencia entre dos motores distintos

Cuando un usuario completa una compra, el sistema crea un registro en `pedido_lineas` (MySQL) que debe identificar cuál producto de MongoDB se compró. Aquí surge un reto de arquitectura: MySQL no tiene forma nativa de referenciar documentos de MongoDB con integridad referencial. No existe `FOREIGN KEY ... REFERENCES mongodb.catalogo(_id)` — eso simplemente no existe en ningún motor relacional.

La solución que implementé tiene dos partes: una columna de referencia lógica y un snapshot desnormalizado.

## La columna `producto_ref` (CHAR 24)

```sql
CREATE TABLE pedido_lineas (
    linea_id        INT AUTO_INCREMENT PRIMARY KEY,
    pedido_id       INT NOT NULL,
    producto_ref    CHAR(24) NOT NULL,      -- ObjectId de MongoDB como string hexadecimal
    producto_nombre VARCHAR(255) NOT NULL,  -- snapshot al momento de la compra
    cantidad        INT NOT NULL,
    precio_unitario DECIMAL(10,2) NOT NULL, -- snapshot al momento de la compra
    subtotal_linea  DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (pedido_id) REFERENCES pedidos(pedido_id)
);
```

El ObjectId de MongoDB tiene siempre 12 bytes representados como 24 caracteres hexadecimales — por ejemplo `6821f3a2c4b7e9d001234567`. Uso `CHAR(24)` (longitud fija) en lugar de `VARCHAR(24)` porque todos los ObjectIds tienen exactamente ese largo, y `CHAR` es marginalmente más eficiente en índices cuando la longitud es conocida.

Esta columna es una **referencia lógica**, no una FK formal. MySQL no puede validarla automáticamente contra MongoDB.

## El snapshot desnormalizado: por qué es necesario

Junto a `producto_ref` guardo `producto_nombre` y `precio_unitario` como snapshot congelado del momento de la compra. Esto responde a dos necesidades:

**1. Legibilidad histórica.** Las órdenes deben ser legibles para siempre, aunque el producto haya cambiado. Si compré una "ThinkPad X1 Carbon" en mayo y el vendedor la renombra a "ThinkPad X1 Carbon Gen 12" en junio, mi historial de pedidos debe seguir mostrando el nombre original que vi cuando compré. Sin snapshot, tendría que ir a MongoDB a buscar el nombre actual y mostraría información incorrecta.

**2. Productos descontinuados.** Si un producto recibe el evento `PRODUCTO_DESCONTINUADO` y su documento en MongoDB se archiva o elimina, la orden sigue siendo válida y legible porque tiene toda la información crítica en MySQL. No hay dependencia de disponibilidad del documento MongoDB para ver el historial de compras.

El precio también está congelado por una razón legal: la orden es un contrato entre el comprador y el vendedor al precio acordado en ese momento. El snapshot garantiza que ese contrato sea inmutable.

## La ausencia de integridad referencial: riesgos

Como no existe una FK formal, los siguientes escenarios son técnicamente posibles aunque el sistema intente prevenirlos:

1. **Referencia a un producto inexistente:** Si se crea una línea de pedido con un `producto_ref` que no existe en MongoDB (por error de código, data corruption, o migración fallida), MySQL lo acepta sin queja.

2. **ObjectId incorrecto por error de formato:** Un string de 24 caracteres que no corresponda a ningún documento en MongoDB es indistinguible de uno válido desde el punto de vista de MySQL.

3. **Inconsistencia de precios:** El `precio_unitario` en `pedido_lineas` podría diferir del precio vigente en MongoDB al momento de la orden si hay una race condition entre la lectura del precio y la escritura de la línea.

## Mitigaciones implementadas

### Validación en capa de aplicación

Antes de confirmar un pedido, FastAPI ejecuta esta secuencia de forma explícita:

```python
async def confirmar_pedido(pedido_data: PedidoCreate) -> Pedido:
    for item in pedido_data.items:
        # 1. Verificar que el producto existe en MongoDB
        producto = await mongo_db.catalogo.find_one({"_id": ObjectId(item.producto_ref)})
        if not producto:
            raise HTTPException(404, f"Producto {item.producto_ref} no encontrado en catálogo")

        # 2. Verificar que el producto está disponible
        if not producto.get("disponible", False):
            raise HTTPException(400, f"Producto {producto['nombre']} no está disponible")

        # 3. Congelar el precio del catálogo en ese momento
        item.precio_unitario = producto["precio"]
        item.producto_nombre = producto["nombre"]

    # 4. Recién aquí crear la orden en MySQL (transacción ACID)
    async with mysql_session.begin():
        pedido = await crear_pedido_mysql(pedido_data)
    return pedido
```

La validación ocurre dentro de la misma request HTTP que crea el pedido, minimizando la ventana de race condition.

### Job de reconciliación

Existe un script en `scripts/reconciliar_referencias.py` que se puede ejecutar periódicamente (o bajo demanda) y hace lo siguiente:

1. Lee todos los `producto_ref` distintos de `pedido_lineas` en MySQL.
2. Consulta en MongoDB si cada ObjectId existe en la colección `catalogo`.
3. Reporta los IDs huérfanos — referencias a documentos que ya no existen.
4. Verifica que el `precio_unitario` registrado estuviera en el rango histórico del producto según sus eventos (detección de anomalías de precio).

El job no corrige automáticamente — genera un reporte para revisión manual, porque modificar líneas de pedidos históricos es una operación que requiere aprobación explícita.

## Referencia inversa: `mongo_id` en la tabla `productos` de MySQL

La tabla `productos` en MySQL tiene una columna `mongo_id CHAR(24)` que guarda el ObjectId del documento correspondiente en MongoDB. Esto permite hacer el join inverso: dado un `producto_id` de MySQL, encontrar el documento completo del catálogo en MongoDB para mostrar atributos variables, imágenes y historial de eventos.

Esta columna se llena al momento de crear el producto y no cambia — el ObjectId de MongoDB es estable durante toda la vida del documento.
