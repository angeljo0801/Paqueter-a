from pathlib import Path

p = Path('app/lib/packages.dart')
s = p.read_text()

old = """  bool _gmailPhotoReceivedInCuba(Map<String, dynamic> image) {
    final url = ''.trim();
    return url.isNotEmpty && cubaReceivedPhotoKeys.contains('gmail:$url');
  }
"""

new = """  bool _gmailPhotoReceivedInCuba(Map<String, dynamic> image) {
    final url = '${image['url'] ?? ''}'.trim();
    if (url.isEmpty) return false;

    // The client photo dashboard stores the status against the original Gmail
    // URL. Use that exact key here so the same green check appears inside the
    // package editor and its full-screen gallery.
    return cubaReceivedPhotoKeys.contains('gmail:$url');
  }
"""

if old not in s:
    raise SystemExit('Missing broken Gmail Cuba-status matcher')
s = s.replace(old, new, 1)
p.write_text(s)

print('Fixed Gmail received-in-Cuba key matching inside package editor.')
