from pathlib import Path

# Recovery v77: manual refresh button in the Packages dashboard.
# Read the latest *local* records directly from persistent storage. This is
# deliberately NOT an implicit WhatsBot pull: automatic remote import could
# undo a user's fresh package edits/deletions. Keep Gmail bulk controls and
# the search text untouched.
p = Path('app/lib/packages.dart')
s = p.read_text()
start = s.index('class _PackagesPageState extends State<PackagesPage> {')
end = s.index('\nString inferCarrier(String tracking)', start)
page = s[start:end]

old = "  String _bulkStamp='';"
assert page.count(old) == 1, 'v77: packages dashboard state changed'
page = page.replace(old, old + "\n  bool _refreshingPackages = false;", 1)

old = "  Future<void> _refreshBulk() async {"
assert page.count(old) == 1, 'v77: background Gmail refresh helper moved'
method = r'''  Future<void> _refreshPackages() async {
    if (_refreshingPackages) return;
    if (mounted) setState(() => _refreshingPackages = true);
    try {
      // Force a new disk read, not the old cached list, so latest edits,
      // restored packages and Trash changes appear immediately.
      await load(forceRefresh: true);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Lista de paquetes actualizada.'),
          duration: Duration(seconds: 2),
        ),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('No se pudieron actualizar los paquetes: $error'),
        ),
      );
    } finally {
      if (mounted) setState(() => _refreshingPackages = false);
    }
  }

'''
page=page.replace(old,method+old,1)

# v57 intentionally restored the classic compact app bar. The refresh button
# must live next to the existing Gmail bulk action, not replace it.
old = r'''        title: const Text('Paquetes'),
        actions: [
          _bulkButton(),'''
if page.count(old) != 1:
    # Some upstream formatting uses one extra space in the title indent.
    old = r'''        title: const Text('Paquetes'),
         actions: [
           _bulkButton(),'''
assert page.count(old) == 1, 'v77: classic package app bar not found'
new = old.replace(
    "_bulkButton(),",
    r'''IconButton(
            tooltip: 'Actualizar lista de paquetes',
            onPressed: _refreshingPackages ? null : _refreshPackages,
            icon: _refreshingPackages
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh),
          ),
          _bulkButton(),''',
)
page=page.replace(old,new,1)
assert page.count("tooltip: 'Actualizar lista de paquetes'") == 1
assert page.count("await load(forceRefresh: true);") >= 1
assert page.count("_bulkButton(),") >= 1
assert "readPersistentSearch('packages')" in page
s=s[:start]+page+s[end:]
p.write_text(s)
print('v77: Packages dashboard refresh button forces a fresh local read, preserving search and Gmail bulk.')
