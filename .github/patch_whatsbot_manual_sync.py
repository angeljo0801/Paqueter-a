from pathlib import Path

# Manual sync must work even if the automatic WhatsBot sync toggle is off.
# The toggle should only control silent/background sync. Before this patch,
# sync(forcePush:true) returned 0 before touching the backend when disabled,
# so Settings misleadingly showed "Sin datos nuevos".
sync = Path('app/lib/whatsbot_sync.dart')
s = sync.read_text()
old = """  static Future<int> sync({bool forcePush = false}) async {
    if (!await enabled()) return 0;
"""
new = """  static Future<int> sync({bool forcePush = false}) async {
    if (!forcePush && !await enabled()) return 0;
"""
if old not in s:
    raise SystemExit('sync enabled guard not found')
s = s.replace(old, new, 1)
sync.write_text(s)

# Make the Settings result clearer after a real manual request.
extras = Path('app/lib/extras.dart')
e = extras.read_text()
e = e.replace(
    "? 'Sin datos nuevos de WhatsBot.'",
    "? 'Sin cambios nuevos después de consultar WhatsBot.'",
    1,
)
extras.write_text(e)
