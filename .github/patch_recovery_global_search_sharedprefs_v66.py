from pathlib import Path

# v66 -- The magnifier / search-list action opens BusinessSearchPage.
# Its initState() restores "global" via readPersistentSearch(), which the
# v2.6.71 build still implements with legacy SharedPreferences.getInstance().
# Some upgraded Android installations throw:
# java.lang.NoSuchMethodError:
# SharedPreferencesApiRegistrar.getAll(...Continuation...)
# That is a binary plugin API mismatch, not a corrupt package database.
# Use the already-registered v43 *per-key* native bridge to retain the exact
# existing preference keys; do not clear/reinstall user data.

p = Path('app/lib/main.dart')
s = p.read_text()
old = r'''const String _searchStatePrefix = 'ui_search_';

Future<String> readPersistentSearch(String key) async {
  final prefs = await SharedPreferences.getInstance();
  return prefs.getString('$_searchStatePrefix$key') ?? '';
}

Future<void> writePersistentSearch(String key, String value) async {
  final prefs = await SharedPreferences.getInstance();
  await prefs.setString('$_searchStatePrefix$key', value);
}'''
new = r'''const String _searchStatePrefix = 'ui_search_';

// Search text uses the EXISTING key in FlutterSharedPreferences but reads it
// via native per-key bridge, never the incompatible getAll() plugin method.
Future<String> readPersistentSearch(String key) async {
  try {
    return await Store._readRaw('$_searchStatePrefix$key') ?? '';
  } catch (error) {
    // A broken search preference must not cover the whole page with an
    // unhandled native stack trace. Packages remain readable independently.
    debugPrint('Could not restore search field ($key): $error');
    return '';
  }
}

Future<void> writePersistentSearch(String key, String value) async {
  try {
    await Store._writeRaw('$_searchStatePrefix$key', value);
  } catch (error) {
    debugPrint('Could not persist search field ($key): $error');
  }
}'''
assert s.count(old) == 1, 'v66 persistent search helpers changed'
s = s.replace(old, new, 1)
assert "final prefs = await SharedPreferences.getInstance();" not in s[
    s.index('Future<String> readPersistentSearch('):
    s.index('Future<void> writePersistentSearch(')]
assert "Store._readRaw('$_searchStatePrefix$key')" in s
assert "Store._writeRaw('$_searchStatePrefix$key', value)" in s
p.write_text(s)

# Reopening the global business search should survive a transient preference
# failure and avoid showing a raw native plugin exception even if the initial
# business list itself cannot load.
p = Path('app/lib/search.dart')
s = p.read_text()
start = s.index('class _BusinessSearchPageState extends State<BusinessSearchPage> {')
end = len(s)
segment = s[start:end]
assert segment.count('final saved = await readPersistentSearch(') == 1
assert segment.count("final r = await Future.wait([Store.list('clients'), Store.list('packages'), Store.list('purchases')]);") == 1

# Existing startup already calls _restoreSearch() -> now nonthrowing native
# per-key preference read. Add a visible retry if any business-list read fails.
segment = segment.replace('  bool loading = true;', "  bool loading = true;\n  String loadError = '';", 1)
oldload = r'''  Future<void> load() async {
    final r = await Future.wait([Store.list('clients'), Store.list('packages'), Store.list('purchases')]);
    if (!mounted) return;
    setState(() {
      clients = active(r[0]);
      packages = active(r[1]);
      purchases = active(r[2]);
      loading = false;
    });
  }'''
newload = r'''  Future<void> load() async {
    if (mounted) setState(() { loading = true; loadError = ''; });
    try {
      final r = await Future.wait([
        Store.list('clients'),
        Store.list('packages'),
        Store.list('purchases'),
      ]);
      if (!mounted) return;
      setState(() {
        clients = active(r[0]);
        packages = active(r[1]);
        purchases = active(r[2]);
        loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        loading = false;
        loadError = 'No se pudo leer el índice de búsqueda. '
            'Tus paquetes no se han borrado.';
      });
      debugPrint('Business search load: $error');
    }
  }'''
assert segment.count(oldload) == 1, 'v66 global search load changed'
segment = segment.replace(oldload, newload, 1)
oldbody = r'''      body: loading
          ? const Center(child: CircularProgressIndicator())
          : Column(children: ['''
newbody = r'''      body: loading
          ? const Center(child: CircularProgressIndicator())
          : loadError.isNotEmpty
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Padding(
                        padding: const EdgeInsets.all(16),
                        child: Text(loadError, textAlign: TextAlign.center),
                      ),
                      FilledButton(
                        onPressed: load,
                        child: const Text('Reintentar búsqueda'),
                      ),
                    ],
                  ),
                )
              : Column(children: ['''
assert segment.count(oldbody) == 1, 'v66 global search body changed'
segment = segment.replace(oldbody, newbody, 1)

assert 'readPersistentSearch(' in segment
assert "loadError.isNotEmpty" in segment
s = s[:start] + segment
p.write_text(s)

# Regression test: prove that the native per-key channel is still registered
# in MainActivity after every canonical patch.
p = Path('app/android/app/src/main/kotlin/com/angelapps/paqueteria/MainActivity.kt')
main = p.read_text()
assert 'PaqueteriaLocalStoreBridge.register(' in main
bridge = Path('app/android/app/src/main/kotlin/com/angelapps/paqueteria/PaqueteriaLocalStoreBridge.kt').read_text()
assert '"readChunk" -> {' in bridge and '"writeString" -> {' in bridge
print('v66: global search uses per-key Android storage; no SharedPreferences.getAll; retry UI safe.')
