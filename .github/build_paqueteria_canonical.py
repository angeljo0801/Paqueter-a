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
    '.github/patch_multi_gmail_accounts_v2.py',
    '.github/patch_gmail_product_checklists.py',
    '.github/patch_gmail_item_editor_ocr.py',
    '.github/patch_migration_json_merge.py',
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
        'gmailSourceEmails',
        'Encontrado en:',
        'gmailItems',
        'Checklist de artículos del correo',
        'Seleccionar varias fotos',
        '_propagateReceivedGmailItemsToPurchase',
        '_editGmailItem',
        '_deleteGmailItem',
        'hiddenGmailItemKeys',
        'gmailOcrScannedUrls',
        '_mergeItemsFromEmailImageOcr',
        'OCR de imágenes del correo',
    ],
    'app/lib/purchases.dart': [
        '_refreshRemoteAfterLocalLoad',
        'purchaseOrderNumbers(',
        'Vincular con correo usando número de orden',
        'Checklist de artículos',
        'gmailPurchasePhotoUrls',
        'gmailLinkedOrderNumbers',
        '_removeMultiplePurchaseEmailPhotos',
        'Marca el cuadrito cuando el artículo haya llegado.',
    ],
    'app/lib/gmail_accounts.dart': [
        'class GmailAccountsPage',
        'Conectar otra cuenta Gmail',
        '/api/gmail/accounts',
        'Hacer principal',
        'Volver a autorizar',
    ],
    'app/lib/gmail_purchase_link.dart': [
        'class GmailPurchaseLinkService',
        'mergeGmailDetectedItems',
        'selectGmailPhotosToRemove',
        'openGmailPhotoPreview',
        'gmailDetectedItemLooksValid',
        'gmailItemsFromOcrText',
        'gmailReadTextFromImage',
        'gmailImageWorthOcr',
    ],
    'app/lib/migration_merge.dart': [
        'class MigrationMergePage',
        'alas-cargo-finance-sync-v1',
        'Combinar y recuperar datos',
        'Réplicas evitadas',
        'skippedLegacyPhotoRefs',
        'remappedReferences',
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
    'app/lib/backup_service.dart': [
        'restoreFile(String path)',
        'materializeBackup',
        'Recuperar datos desde JSON de Paquetería Migrador',
        "import 'migration_merge.dart';",
    ],
    'app/lib/extras.dart': [
        'apiKeyLoaded',
        'Recuperar desde Railway (solo lectura)',
        'Correos conectados',
    ],
    'app/lib/main.dart': [
        '_syncWhatsBotAfterResume',
        'readPersistentSearch',
        "part 'gmail_accounts.dart';",
        "part 'gmail_purchase_link.dart';",
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