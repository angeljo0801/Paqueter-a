from pathlib import Path
import subprocess
import sys

# ONE official Paqueteria build path.
# Every release must pass through this list in this exact order so a newer APK
# can never silently lose fixes that used to live in separate workflows.
PATCHES = [
    '.github/patch_paqueteria.py',
    '.github/patch_paqueteria_recovery.py',
    '.github/patch_paqueteria_clients_local_first.py',
    '.github/patch_paqueteria_purchases_local_first.py',
    '.github/patch_order_numbers.py',
    '.github/patch_large_backup_restore.py',
    '.github/patch_settings_loading.py',
    '.github/patch_whatsbot_resume_sync.py',
    '.github/patch_whatsbot_manual_sync.py',
    '.github/patch_persistent_search_client_weight.py',
]

for patch in PATCHES:
    print(f'==> Applying {patch}', flush=True)
    subprocess.run([sys.executable, patch], check=True)

# Regression guards. If any of these disappear, CI stops instead of publishing
# an APK with a higher version number but older functionality.
CHECKS = {
    'app/lib/packages.dart': [
        'Buscar tracking en Gmail y reconstruir compra',
        'Fotos obtenidas del correo',
        'Toca una imagen para verla en grande',
        'Añadir foto del paquete',
        'hiddenEmailPhotoUrls',
    ],
    'app/lib/whatsbot_sync.dart': [
        'recoverFromServerOnly',
        '_cachedApiKey',
        'if (!forcePush && !await enabled()) return 0;',
    ],
    'app/lib/clients.dart': [
        '_refreshRemoteAfterLocalLoad',
        "readPersistentSearch('clients')",
        'Libras:',
    ],
    'app/lib/purchases.dart': [
        '_refreshRemoteAfterLocalLoad',
        'purchaseOrderNumbers(',
    ],
    'app/lib/backup_service.dart': [
        'restoreFile(String path)',
        'materializeBackup',
    ],
    'app/lib/extras.dart': [
        'apiKeyLoaded',
        'Recuperar desde Railway (solo lectura)',
    ],
    'app/lib/main.dart': [
        '_syncWhatsBotAfterResume',
        'readPersistentSearch',
    ],
}

missing = []
for file_name, markers in CHECKS.items():
    p = Path(file_name)
    if not p.exists():
        missing.append(f'{file_name}: FILE MISSING')
        continue
    text = p.read_text()
    for marker in markers:
        if marker not in text:
            missing.append(f'{file_name}: {marker}')

if missing:
    print('\nCANONICAL BUILD BLOCKED. Missing required Paqueteria features:', file=sys.stderr)
    for item in missing:
        print(f' - {item}', file=sys.stderr)
    raise SystemExit(2)

print('\nCanonical Paqueteria feature set verified successfully.')
