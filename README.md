# Paquetería

Repositorio oficial de la aplicación Android **Paquetería**.

## Versión actual

- **Paquetería v2.6.0**
- Código fuente principal: `paqueteria/`
- APK oficial: publicada en **GitHub Releases**
- Workflow oficial único: `.github/workflows/release-apk.yml`
- Orquestador de funciones: `.github/build_paqueteria_canonical.py`

## Regla principal del repositorio

Paquetería tiene **un solo camino oficial de compilación**. No se deben publicar APKs completas desde workflows paralelos con subconjuntos diferentes de parches.

El workflow oficial siempre:

1. crea el scaffold Android desde `paqueteria/`;
2. aplica **todo** el conjunto de mejoras mediante `build_paqueteria_canonical.py`;
3. ejecuta verificaciones de regresión para Gmail, fotos, WhatsBot, recuperación, búsquedas persistentes, varios números de orden, clientes/compras local-first y restauración de copias grandes;
4. ejecuta `flutter analyze`;
5. compila con `applicationId=com.angelapps.paqueteria`;
6. usa la firma persistente oficial;
7. usa un `versionCode` del rango canónico `100000 + GITHUB_RUN_NUMBER`, superior a los rangos usados por los workflows antiguos;
8. publica el APK como artefacto y como GitHub Release.

Si una función obligatoria desaparece, la compilación falla antes de publicar. Esto evita que una versión con número más nuevo salga con funciones de una base vieja.

## Workflows retirados

Los antiguos workflows separados para recuperación, clientes/compras, números de orden, restauración grande, ajustes, WhatsBot y fotos de Gmail fueron retirados. Sus mejoras forman parte del camino canónico y ya no deben generar APKs competidoras.

## Seguridad de actualización

La APK oficial conserva la misma identidad de paquete y la misma firma persistente. Además, el rango alto de `versionCode` evita el error de Android de *no se pudo actualizar* causado por instalar anteriormente una APK experimental con un `versionCode` mayor.

Antes de esta consolidación se creó la rama de respaldo `backup-before-canonical-20261004` para conservar exactamente el estado anterior del repositorio.
