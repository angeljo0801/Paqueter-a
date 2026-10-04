# Paquetería Migrador JSON merge recovery

The canonical Paquetería build supports additive recovery from the legacy `alas-cargo-finance-sync-v1` migration JSON.

Rules:
- Never clear current SharedPreferences or delete current rows.
- Current non-empty fields win.
- Missing/empty current fields are filled from the migration JSON.
- New records are added.
- Duplicates are matched with strong IDs/sync IDs plus entity-specific identities such as package tracking, purchase order number, client phone/email, and unique client/agent names.
- When a duplicate imported ID maps to a different current ID, dependent references are remapped before merge.
- List fields are unioned instead of replaced.
- Old private Android photo paths are imported only when the referenced file still exists; dead paths are skipped.
- The UI always shows a preview with added/enriched/duplicate counts before applying.

Implementation is applied by `.github/patch_migration_json_merge.py` and guarded by `.github/build_paqueteria_canonical.py` so future APK releases cannot silently lose the feature.
