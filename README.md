# Paquetería

Repositorio oficial de la aplicación **Paquetería**.

## Estado actual

- Última APK verificada: **Paquetería v2.3.4**
- APK: `Paqueteria-v2.3.4.apk`
- Tamaño aproximado del APK: **107.9 MB**
- Paquete comprimido: `Paqueteria-v2.3.4-APK.zip` (~52.1 MB)

El APK supera el límite normal de 100 MB para archivos Git. La solución usada en este repositorio es:

1. Guardar en el repositorio el ZIP comprimido, que está por debajo de 100 MB.
2. GitHub Actions lo descomprime.
3. El workflow publica automáticamente el APK real en **GitHub Releases**, donde puede superar 100 MB.

## Subir una nueva versión

El archivo debe llamarse siguiendo este patrón:

`Paqueteria-vX.Y.Z-APK.zip`

Dentro del ZIP debe existir un archivo `.apk`.

Al hacer push del ZIP, el workflow **Publicar APK de Paquetería** crea o actualiza el Release correspondiente y adjunta el APK.
