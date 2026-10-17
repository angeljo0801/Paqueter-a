# Paquetería — recuperación controlada desde v2.6.38

## Objetivo
Restaurar el flujo de Gmail y de fotos sin trasladar automáticamente los cambios de almacenamiento y reconstrucción de v2.6.40–v2.6.48 a producción.

## Referencia
- Fuente original: tag **v2.6.38** (15 de octubre de 2026).
- Rama aislada: `recovery/pre-permissions-v2.6.38`.
- APK de prueba: versión **2.6.49**, `versionCode` **100251** (la última compilación oficial antes de la prueba era **100250**). La siguiente actualización oficial debe compilarse con un `versionCode` mayor que **100251**.
- Mismo `applicationId` y la misma firma persistente, para permitir la actualización sin desinstalar.
- No se publica GitHub Release ni se actualiza `main`.

## Medidas antes de la prueba
1. Exportar una **copia de migración JSON** de la instalación actual y guardar una copia fuera del teléfono.
2. Comprobar que el respaldo no esté vacío: debe incluir clientes, paquetes, compras y fotografías/relaciones si existen.
3. No utilizar «Borrar datos» ni desinstalar Paquetería.
4. Solo instalar la APK de prueba cuando la compilación y firma pasen; guardar la APK actual para referencia.

## Comprobaciones manuales de aceptación
- [ ] La pantalla Inicio abre, también después de cerrar y volver a abrir.
- [ ] Los clientes, paquetes, compras, pedidos y sus asociaciones siguen presentes.
- [ ] Los vínculos paquete ↔ compras/pedidos se pueden consultar y editar.
- [ ] La comprobación/renovación de permisos en el backend no requiere reinstalar la app.
- [ ] La búsqueda Gmail encuentra un tracking que realmente aparece en los mensajes.
- [ ] Para un correo con fotos reales, se recuperan fotos y se ven en el paquete.
- [ ] Las fotos siguen disponibles tras cerrar y reabrir.
- [ ] Una búsqueda sin coincidencias no inventa una fuente Gmail ni fotos.
- [ ] Un error de Gmail no se presenta como «No encontrado».
- [ ] La búsqueda en segundo plano puede finalizar y mostrar fotos al volver al paquete.
- [ ] No aparecen fotos de banners/precios como si fueran artículos.
- [ ] No se reemplaza un paquete modificado por un resultado anterior.

## Criterio de publicación
**No convertir la recuperación en versión general hasta confirmar las pruebas en un teléfono con una copia de respaldo.** Si falla, aislar la regresión con un único cambio a la vez. No migrar masivamente los parches posteriores.
