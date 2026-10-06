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
    '.github/patch_gmail_photo_gallery.py',
    '.github/patch_gmail_link_badges.py',
    '.github/patch_gmail_smart_product_photos.py',
    '.github/patch_gmail_product_photo_filter_v2.py',
    '.github/patch_gmail_product_photo_filter_v3.py',
    '.github/patch_gmail_temu_url_fix_v4.py',
    '.github/patch_gmail_product_photo_filter_v5_background.py',
    '.github/patch_gmail_product_photo_filter_v6_nonproducts.py',
    '.github/patch_gmail_runtime_stability_v7.py',
    '.github/patch_gmail_background_resume_v8.py',
    '.github/patch_gmail_background_durable_v9.py',
    '.github/patch_gmail_background_photos_and_catalog_v10.py',
    '.github/patch_gmail_nonproduct_banners_v11.py',
    '.github/patch_gmail_photo_persistence_order_v12.py',
    '.github/patch_gmail_recover_discarded_photos.py',
    '.github/patch_fast_tabs_cache.py',
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
        'openGmailPhotoGallery',
        'gmailRecordIsLinked(p)',
        'gmailLinkedBadge(context)',
        '_smartFilterAndCacheGmailPhotos',
        'gmailOfflinePhotoPaths',
        'gmailRejectedImages',
        'gmailManuallyAcceptedPhotoUrls',
        'manuallyAcceptedGmailPhotoUrls',
        'Ver imágenes descartadas',
        'GmailBackgroundSearch.reconstruct(',
        "data['_backgroundPending'] == true",
        'GmailBackgroundSearch.friendlyError(e)',
        'la búsqueda seguirá en segundo plano',
        "PageStorageKey<String>('packages-main-list')",
        'with WidgetsBindingObserver',
        '_recoverFinishedGmailSearch',
        'GmailBackgroundSearch.hasFinished(',
        '_startGmailRecoveryWatch',
        '_persistRecoveredGmailSnapshot',
        'Only mark the background result as consumed after the final accepted',
        'autoAcknowledge: false',
        'GmailBackgroundSearch.acknowledgeFinished(',
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
        'openGmailPhotoGallery',
        'gmailRecordIsLinked(p)',
        'gmailLinkedBadge(context)',
        '_smartFilterAndCachePurchaseGmailPhotos',
        'gmailPurchaseOfflinePhotoPaths',
        'gmailPurchaseRejectedImages',
        'gmailPurchaseManuallyAcceptedPhotoUrls',
        'manuallyAcceptedGmailPhotoUrls',
        'Ver imágenes descartadas',
        'GmailBackgroundSearch.friendlyError(e)',
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
        'openGmailPhotoGallery',
        'Desliza horizontalmente',
        'Borrar esta foto',
        'Recuperar como producto',
        'gmailDetectedItemLooksValid',
        'gmailItemsFromOcrText',
        'gmailReadTextFromImage',
        'gmailImageWorthOcr',
        'bool gmailRecordIsLinked(Map<String, dynamic> record)',
        'Widget gmailLinkedBadge(BuildContext context)',
        'Ya vinculado / reconstruido con Gmail',
        'gmailPrepareProductPhotos',
        '_gmailPromoText',
        'gmailSmartPhotoImage',
        'gmailCatalogRecommendationCard',
        'gmailOrderItemPhotoSignals',
        'showGmailRejectedPhotoGrid',
        'gmailCacheRecoveredPhoto',
        'confirmed_product',
        'manual_product',
        'gmail_product_photos',
        'decimalMoneyCount',
        'compactOrderRow',
        'compactItemCue',
        'order in transit',
        'safe payments',
        'view details on gofo',
        'variantQuantityCount',
        'multiVariantGrid',
        'multiPieceListing',
        'spanishShipmentUi',
        'GmailBackgroundSearch.reconstruct(',
    ],
    'app/lib/background_sync.dart': [
        "const String gmailBackgroundTask = 'gmailBackgroundReconstruct';",
        'class GmailBackgroundSearch',
        'static Future<void> ensureInitialized()',
        'static String friendlyError(Object error)',
        'static Future<Map<String, dynamic>> _requestWithRetry(',
        'static Future<bool> hasFinished({',
        'static Future<void> acknowledgeFinished({',
        'bool autoAcknowledge = true',
        'bool consume = true',
        'initialDelay: const Duration(seconds: 8)',
        "'_backgroundPending': true",
        "tag: 'gmail-background-search'",
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
        'gmailRecordIsLinked(p)',
        'gmailLinkedBadge(context)',
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
        "import 'dart:ui' as ui;",
        'body: IndexedStack(',
        '_listCache',
        'if (!mounted || changed <= 0) return;',
        'await BackgroundCourierSync.initializeAndSchedule();',
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