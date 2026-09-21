# Paquetería

Repositorio oficial de la aplicación Android **Paquetería**.

## Versión actual

- **Paquetería v2.4.1**
- Código fuente principal: `paqueteria/`
- APK oficial: publicada en **GitHub Releases**
- Archivo: `Paqueteria-v2.4.1.apk`
- Tamaño: 108,176,252 bytes

## Compilación automática

El repositorio compila la APK directamente desde el código fuente con GitHub Actions.

Cada cambio relevante en `paqueteria/`, en el parche Android o en el workflow:

1. prepara el proyecto Flutter/Android;
2. aplica la integración nativa necesaria;
3. ejecuta análisis;
4. compila la APK release;
5. guarda la APK como artefacto de Actions;
6. publica o actualiza automáticamente el GitHub Release correspondiente.

La versión se obtiene directamente de `paqueteria/pubspec.yaml`.
