from pathlib import Path

p=Path('app/lib/packages.dart')
s=p.read_text()
old='''    if (_gmailNotFoundForCurrent) {
      gmailSourceEmails.clear();
      gmailStatus.clear();
      gmailEta.clear();
    }'''
new='''    // Old Gmail metadata is not evidence for the tracking currently shown.
    // Preserve manual store/recipient fields but hide previous Gmail-derived
    // status and delivery dates until the current tracking is verified.
    if (!_gmailVerifiedForCurrent) {
      gmailStatus.clear();
      gmailEta.clear();
      if (_gmailNotFoundForCurrent) gmailSourceEmails.clear();
    }'''
if s.count(old)!=1: raise SystemExit('Gmail v40: old status init anchor missing')
s=s.replace(old,new,1)
p.write_text(s)

p=Path('app/lib/background_sync.dart')
s=p.read_text()
anchor='''    if (_transientNetworkError(error)) {'''
if s.count(anchor)!=1: raise SystemExit('Gmail v40: error mapping anchor missing')
s=s.replace(anchor,'''    if (lower.contains('sharedpreferences') ||
        lower.contains('fluttersharedpreferences') ||
        lower.contains('local_store') ||
        lower.contains('platformexception') ||
        lower.contains('channel-error') ||
        lower.contains('unable to establish connection on channel')) {
      return 'La búsqueda no llegó a Gmail porque Android no pudo leer su estado local. '
          'Actualiza Paquetería y vuelve a intentar, sin borrar tus datos.';
    }
    if (_transientNetworkError(error)) {''',1)
p.write_text(s)
print('Gmail v40: old Gmail status hidden unless confirmed, storage failures identified.')
