from pathlib import Path

p = Path('app/lib/background_sync.dart')
s = p.read_text()
a = s.index("  @pragma('vm:entry-point')\n  static Future<bool> execute(")
b = s.index("\n}\n\nclass NotificationService", a)
worker = s[a:b]
needle = """        token: token,
      );
      final result = await _processPackagePhotosInBackground("""
replacement = """        token: token,
        clientId: '${data['clientId'] ?? ''}',
      );
      final result = await _processPackagePhotosInBackground("""
if worker.count(needle) != 1:
    raise SystemExit('Could not identify exactly one Gmail background job call to scope by client')
worker = worker.replace(needle, replacement, 1)
s = s[:a] + worker + s[b:]
p.write_text(s)
print('Gmail v33: WorkManager now uses the same client Gmail scope as the foreground request.')
