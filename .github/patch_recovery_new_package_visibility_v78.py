from pathlib import Path

# Recovery v78: after creating a package, the dashboard may preserve an old
# search query and hide the newly saved record. This used to say "No hay
# paquetes" even when disk holds multiple active packages. Fix the false empty
# state, reveal the new row, and show verifiable save feedback.
p = Path('app/lib/packages.dart')
s = p.read_text()
page_start = s.index('class _PackagesPageState extends State<PackagesPage> {')
page_end = s.index('\nString inferCarrier(String tracking)', page_start)
page = s[page_start:page_end]

anchor = '  Future<void> _refreshPackages() async {'
assert page.count(anchor) == 1, 'v78: dashboard refresh method changed'
helper = r'''  void _clearPackagesSearch() {
    search.clear();
    setState(() => q = '');
    unawaited(writePersistentSearch('packages', ''));
  }

  Future<void> _afterPackageEditor(String? savedId) async {
    // A package is created/edited in another route. Always bypass the
    // cached dashboard list after returning.
    await load(forceRefresh: true);
    if (!mounted || savedId == null || savedId.isEmpty) return;
    final matching = rows.where((row) =>
        (row['id'] ?? '').toString() == savedId).firstOrNull;
    if (matching == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text(
          'El paquete guardado no aparece en el almacenamiento. '
          'Comprueba Papelera o vuelve a intentarlo.',
        )),
      );
      return;
    }
    // A leftover persistent search must never hide a package JUST created.
    if (q.trim().isNotEmpty) _clearPackagesSearch();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Paquete guardado: ' +
          (matching['tracking'] ?? '').toString()),
        duration: const Duration(seconds: 3),
      ),
    );
  }

'''
page=page.replace(anchor,helper+anchor,1)

# Make new packages visible at the top even with a long package list. The
# dashboard retains its old ordering for every other record.
field = "  String _bulkStamp='';"
assert page.count(field) == 1, 'v78: package list fields changed'
page=page.replace(field,field+"\n  String _latestSavedPackageId='';\n  final ScrollController _newPackageScroll=ScrollController();",1)

dispose = "    search.dispose();\n    super.dispose();"
assert page.count(dispose) == 1, 'v78: package scroll controller lifecycle moved'
page=page.replace(dispose,"    search.dispose();\n    _newPackageScroll.dispose();\n    super.dispose();",1)

fstart=page.index("    final f = rows.where((p) =>")
fend=page.index("    return Scaffold(",fstart)
filter_block=page[fstart:fend]
assert filter_block.count(".toList();") == 1, 'v78: dashboard list filtering changed'
page=page.replace(filter_block,filter_block+r'''    if (_latestSavedPackageId.isNotEmpty) {
      f.sort((a, b) {
        final aTop=(a['id'] ?? '').toString()==_latestSavedPackageId;
        final bTop=(b['id'] ?? '').toString()==_latestSavedPackageId;
        return aTop == bTop ? 0 : (aTop ? -1 : 1);
      });
    }
''',1)

# The dashboard may have a PageStorageKey or slightly different spacing.
# Attach the ScrollController by the unique itemCount rather than formatting.
lv="                  itemCount: f.length,"
assert page.count(lv)==1,'v78: dashboard list item count changed'
page=page.replace(lv,"                  controller: _newPackageScroll,\n"+lv,1)

# Saved item exists and is active: after clearing a stale search, pin to top.
success="    ScaffoldMessenger.of(context).showSnackBar(\n      SnackBar(\n        content: Text('Paquete guardado: ' +"
assert page.count(success)==1,'v78: package save confirmation changed'
page=page.replace(success,r'''    setState(() => _latestSavedPackageId = savedId);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _newPackageScroll.hasClients) {
        _newPackageScroll.jumpTo(0);
      }
    });
'''+success,1)


# Route returning from Save includes the saved ID. This is not called after
# cancellation, so cancelled form edits do not clear the search.
old="onPressed: () async { await Navigator.push(context, MaterialPageRoute(builder: (_) => const PackageEditPage())); load(forceRefresh:true); },"
if page.count(old) != 1:
    old="onPressed: () async { await Navigator.push(context, MaterialPageRoute(builder: (_) => const PackageEditPage())); load(); },"
assert page.count(old) == 1, 'v78: new package action not found'
new=r'''onPressed: () async {
          final savedId = await Navigator.push<String>(
            context,
            MaterialPageRoute(builder: (_) => const PackageEditPage()),
          );
          if (mounted) await _afterPackageEditor(savedId);
        },'''
page=page.replace(old,new,1)

# The scanner can create a package too, and should reveal it identically.
old = "await Navigator.push(context, MaterialPageRoute(builder: (_) => PackageEditPage(initialTracking: code)));"
assert page.count(old) == 1, 'v78: scanner package create changed'
page=page.replace(old, r'''final savedId = await Navigator.push<String>(
                    context,
                    MaterialPageRoute(builder: (_) =>
                        PackageEditPage(initialTracking: code)),
                  );
                  if (mounted) await _afterPackageEditor(savedId);''',1)

# No matching search results is NOT an empty database.
old = "          child: f.isEmpty\n              ? const Center(child: Text('No hay paquetes.'))\n              : ListView.builder("
assert page.count(old) == 1, 'v78: package filtered empty state changed'
new = r'''          child: f.isEmpty
              ? Center(
                  child: rows.isNotEmpty && q.trim().isNotEmpty
                      ? Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.search_off_outlined, size: 40),
                            const SizedBox(height: 10),
                            Text(
                              'Sin resultados para "' + q + '".',
                              textAlign: TextAlign.center,
                            ),
                            Text(
                              'Hay ' + rows.length.toString() +
                              ' paquete(s) guardado(s).',
                            ),
                            const SizedBox(height: 10),
                            OutlinedButton.icon(
                              onPressed: _clearPackagesSearch,
                              icon: const Icon(Icons.filter_alt_off),
                              label: const Text('Mostrar todos los paquetes'),
                            ),
                          ],
                        )
                      : const Text('No hay paquetes activos.'),
                )
              : ListView.builder('''
page=page.replace(old,new,1)
assert "tooltip: 'Actualizar lista de paquetes'" in page
assert 'readPersistentSearch(' in page
assert "label: const Text('Mostrar todos los paquetes')" in page
s=s[:page_start]+page+s[page_end:]

# After successfully verifying a write, return its ID to the parent screen,
# rather than popping with null. Existing callers can ignore the result.
old = "    if (mounted) Navigator.pop(context);"
start=s.index('  Future<void> save() async {', s.index('class PackageEditPage'))
end=s.index('\n  @override\n  Widget build(',start)
section=s[start:end]
assert section.count(old) == 1, 'v78: verified save success pop moved'
assert 'No se pudo verificar el guardado del paquete' in section, 'v78: v74 persisted-save verification missing'
section=section.replace(old,"    if (mounted) Navigator.pop(context, item['id'].toString());",1)
s=s[:start]+section+s[end:]
p.write_text(s)
print('v78: newly-created packages revealed; persistent filters no longer masquerade as missing packages.')
