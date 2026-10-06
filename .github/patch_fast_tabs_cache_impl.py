from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)


main_path = Path('app/lib/main.dart')
s = main_path.read_text()

# SharedPreferences already caches the raw strings, but every Store.list call was
# still JSON-decoding the whole collection again. Keep a session cache of parsed
# rows and update it transactionally whenever Store.saveList writes.
old_store = r'''class Store {
  static Future<List<Map<String, dynamic>>> list(String key) async {
    final p = await SharedPreferences.getInstance();
    final raw = p.getString(key);
    if (raw == null || raw.isEmpty) return [];
    try {
      return (jsonDecode(raw) as List).map((e) => Map<String, dynamic>.from(e as Map)).toList();
    } catch (_) {
      return [];
    }
  }

  static Future<void> saveList(String key, List<Map<String, dynamic>> value) async {
    final p = await SharedPreferences.getInstance();
    await p.setString(key, jsonEncode(value));
    await FinanceSyncService.refreshSnapshot();
  }
'''
new_store = r'''class Store {
  static final Map<String, List<Map<String, dynamic>>> _listCache =
      <String, List<Map<String, dynamic>>>{};

  static List<Map<String, dynamic>> _copyRows(
    List<Map<String, dynamic>> rows,
  ) => rows.map((e) => Map<String, dynamic>.from(e)).toList();

  static Future<List<Map<String, dynamic>>> list(
    String key, {
    bool forceRefresh = false,
  }) async {
    if (!forceRefresh) {
      final cached = _listCache[key];
      if (cached != null) return _copyRows(cached);
    }
    final p = await SharedPreferences.getInstance();
    final raw = p.getString(key);
    if (raw == null || raw.isEmpty) {
      _listCache[key] = <Map<String, dynamic>>[];
      return <Map<String, dynamic>>[];
    }
    try {
      final decoded = (jsonDecode(raw) as List)
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();
      _listCache[key] = _copyRows(decoded);
      return decoded;
    } catch (_) {
      _listCache[key] = <Map<String, dynamic>>[];
      return <Map<String, dynamic>>[];
    }
  }

  static void clearListCache([String? key]) {
    if (key == null) {
      _listCache.clear();
    } else {
      _listCache.remove(key);
    }
  }

  static Future<void> saveList(String key, List<Map<String, dynamic>> value) async {
    final snapshot = _copyRows(value);
    _listCache[key] = snapshot;
    final p = await SharedPreferences.getInstance();
    await p.setString(key, jsonEncode(value));
    await FinanceSyncService.refreshSnapshot();
  }
'''
if 'static final Map<String, List<Map<String, dynamic>>> _listCache' not in s:
    s = replace_once(s, old_store, new_store, 'Store session cache')

# Only reconstruct tab widgets after returning from WhatsBot if the sync actually
# imported/changed something. Previously every resume discarded every dashboard
# state even when nothing changed.
old_resume = r'''      await WhatsBotPurchaseSyncService.syncSilently()
          .timeout(const Duration(seconds: 60));
      if (!mounted) return;
      setState(() {
        pages = [
          DashboardPage(key: UniqueKey()),
          ClientsPage(key: UniqueKey()),
          PackagesPage(key: UniqueKey()),
          TripsPage(key: UniqueKey()),
          MorePage(key: UniqueKey()),
        ];
      });
'''
new_resume = r'''      final changed = await WhatsBotPurchaseSyncService.syncSilently()
          .timeout(const Duration(seconds: 60));
      if (!mounted || changed <= 0) return;
      Store.clearListCache();
      setState(() {
        pages = [
          DashboardPage(key: UniqueKey()),
          ClientsPage(key: UniqueKey()),
          PackagesPage(key: UniqueKey()),
          TripsPage(key: UniqueKey()),
          MorePage(key: UniqueKey()),
        ];
      });
'''
if 'if (!mounted || changed <= 0) return;' not in s:
    s = replace_once(s, old_resume, new_resume, 'resume sync refresh only on change')

# Keep all five main dashboard pages mounted. This preserves their State objects,
# list scroll offsets, searches, parsed data and image widgets while switching
# tabs instead of rebuilding Packages/Clients/Trips from zero every time.
if 'body: IndexedStack(' not in s:
    s = replace_once(
        s,
        '      body: pages[index],\n',
        '''      body: IndexedStack(\n        index: index,\n        children: pages,\n      ),\n''',
        'HomeShell IndexedStack',
    )

main_path.write_text(s)

# Give the principal package list a stable PageStorage identity too. IndexedStack
# already retains it in normal navigation; the key also preserves position across
# benign parent rebuilds.
packages_path = Path('app/lib/packages.dart')
ps = packages_path.read_text()
if "key: const PageStorageKey<String>('packages-main-list')" not in ps:
    ps = replace_once(
        ps,
        '''              : ListView.builder(\n                  itemCount: f.length,\n''',
        '''              : ListView.builder(\n                  key: const PageStorageKey<String>('packages-main-list'),\n                  itemCount: f.length,\n''',
        'package list PageStorageKey',
    )
packages_path.write_text(ps)

print('Fast persistent tabs + in-memory Store cache applied.')
