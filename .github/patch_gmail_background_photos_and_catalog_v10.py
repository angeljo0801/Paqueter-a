from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)


# v10 fixes two field-reported issues:
# 1) A background Gmail result could be consumed while PackageEditPage was still
#    loading backend URL/API key. The reconstruction data existed, but image OCR/
#    caching then ran with empty credentials and all photos disappeared.
# 2) Temu storefront/listing cards (Halloween example) can contain x3 variant
#    labels. Those labels look like order quantity signals, so older code skipped
#    the catalog-card rejection even when the same image had sale/listing cues.

# ---------------------------------------------------------------------------
# Hard reject catalog/storefront cards even when xN makes orderItemSignals true.
# ---------------------------------------------------------------------------
helper_path = Path('app/lib/gmail_purchase_link.dart')
hs = helper_path.read_text()

hs = replace_once(
    hs,
    "  if (gmailCatalogRecommendationCard(text) && !gmailOrderItemPhotoSignals(text)) {\n    return <Map<String, dynamic>>[];\n  }\n",
    "  if (gmailCatalogRecommendationCard(text)) {\n    return <Map<String, dynamic>>[];\n  }\n",
    'hard reject catalog cards during item OCR',
)

hs = replace_once(
    hs,
    "      if (catalogCard && !orderItemSignals) {\n",
    "      if (catalogCard) {\n",
    'hard reject catalog cards during photo filtering',
)

# Strengthen explicit Temu listing cues that OCR reliably sees even if star/cart
# glyphs are missed. The Halloween card has a multi-piece title, many x3 rows and
# sale pricing; any of those combinations must stay out of accepted photos.
needle = "  final multiPieceListing = RegExp(\n    r'\\b\\d{2,4}\\s*(?:pcs?|pieces)\\b',\n    caseSensitive: false,\n  ).hasMatch(lower);\n"
insert = needle + "\n  final truncatedListingTitle = RegExp(\n    r'\\b(?:pcs?|pieces)\\b.*\\.\\.\\.|\\.\\.\\..*(?:pcs?|pieces)\\b',\n    caseSensitive: false,\n  ).hasMatch(lower);\n"
hs = replace_once(hs, needle, insert, 'Temu truncated listing-title signal')

hs = replace_once(
    hs,
    "  if (multiVariantGrid && (priceCount >= 1 || decimalMoneyCount >= 1)) {\n    return true;\n  }\n",
    "  if (multiVariantGrid && (priceCount >= 1 || decimalMoneyCount >= 1)) {\n    return true;\n  }\n  if (multiPieceListing && (priceCount >= 1 || decimalMoneyCount >= 1 || multiVariantGrid)) {\n    return true;\n  }\n  if (truncatedListingTitle && (priceCount >= 1 || decimalMoneyCount >= 1)) {\n    return true;\n  }\n",
    'Temu listing-card hard guards',
)

helper_path.write_text(hs)


# ---------------------------------------------------------------------------
# Package editor: do not recover/apply background results until Gmail settings
# are loaded. Also reload settings defensively before OCR/photo caching.
# ---------------------------------------------------------------------------
packages_path = Path('app/lib/packages.dart')
ps = packages_path.read_text()

ps = replace_once(
    ps,
    "      if (gmailLoading || _recoveringFinishedGmailSearch) return;\n",
    "      if (!loaded ||\n          gmailBackendUrl.trim().isEmpty ||\n          gmailApiKey.trim().isEmpty ||\n          gmailLoading ||\n          _recoveringFinishedGmailSearch) {\n        return;\n      }\n",
    'background watcher waits for Gmail credentials',
)

ps = replace_once(
    ps,
    "    if (!mounted || gmailLoading || _recoveringFinishedGmailSearch) return;\n",
    "    if (!mounted ||\n        !loaded ||\n        gmailBackendUrl.trim().isEmpty ||\n        gmailApiKey.trim().isEmpty ||\n        gmailLoading ||\n        _recoveringFinishedGmailSearch) {\n      return;\n    }\n",
    'background recovery waits for Gmail credentials',
)

# After init finishes, explicitly keep the watcher alive. This covers the case
# where the WorkManager result became ready while the editor was still loading.
ps = replace_once(
    ps,
    "      setState(() => loaded = true);\n      await Future<void>.delayed(const Duration(milliseconds: 120));\n      await _recoverFinishedGmailSearch();\n",
    "      setState(() => loaded = true);\n      _startGmailRecoveryWatch();\n      await Future<void>.delayed(const Duration(milliseconds: 120));\n      await _recoverFinishedGmailSearch();\n",
    'restart Gmail watcher after editor initialization',
)

# Defensive credential refresh for both image OCR and photo caching. A recovered
# result must never be filtered with blank URL/key even after Android recreated
# the activity/process.
ps = replace_once(
    ps,
    "  Future<void> _smartFilterAndCacheGmailPhotos() async {\n    final allImages = _emailPhotoEntries();\n",
    "  Future<void> _smartFilterAndCacheGmailPhotos() async {\n    if (gmailBackendUrl.trim().isEmpty) {\n      gmailBackendUrl = (await WhatsBotPurchaseSyncService.backendUrl()).trim();\n    }\n    if (gmailApiKey.trim().isEmpty) {\n      gmailApiKey = (await WhatsBotPurchaseSyncService.apiKey()).trim();\n    }\n    final allImages = _emailPhotoEntries();\n",
    'refresh Gmail credentials before photo cache/filter',
)

ps = replace_once(
    ps,
    "  Future<void> _mergeItemsFromEmailImageOcr() async {\n    final candidates = _emailPhotoEntries()\n",
    "  Future<void> _mergeItemsFromEmailImageOcr() async {\n    if (gmailBackendUrl.trim().isEmpty) {\n      gmailBackendUrl = (await WhatsBotPurchaseSyncService.backendUrl()).trim();\n    }\n    if (gmailApiKey.trim().isEmpty) {\n      gmailApiKey = (await WhatsBotPurchaseSyncService.apiKey()).trim();\n    }\n    final candidates = _emailPhotoEntries()\n",
    'refresh Gmail credentials before image OCR',
)

packages_path.write_text(ps)

print('Gmail v10 applied: background recovery waits for loaded credentials; recovered photos are processed correctly; catalog/listing cards are hard rejected.')
