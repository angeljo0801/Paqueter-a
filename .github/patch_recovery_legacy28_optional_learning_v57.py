from pathlib import Path

# Stable baseline: tags v2.6.27 and v2.6.28 have the same package-editor
# source SHA b47b4ab... and BOTH precede patch v30 adaptive learning and
# v31 bulk-selection UI. Keep the later Gmail transport/storage repairs.
h=Path('app/lib/gmail_purchase_link.dart')
s=h.read_text()
anchor="  static const String _key = 'gmail_photo_learning_v1';"
assert s.count(anchor)==1,'v57 learning service not found'
s=s.replace(anchor,anchor+'''
  // v2.6.27/28 behavior by default. Enabling is an explicit opt-in.
  static const String _enabledKey = 'gmail_photo_learning_enabled_v2';
  static bool? _enabledCache;
  static Future<bool> isEnabled() async {
    if (_enabledCache != null) return _enabledCache!;
    try {
      final raw = await Store._readRaw(_enabledKey);
      return _enabledCache = raw?.trim() == 'true';
    } catch (_) {
      return false; // Settings/database errors never activate learning.
    }
  }

  static Future<void> setEnabled(bool enabled) async {
    await Store._writeRaw(_enabledKey, enabled ? 'true' : 'false');
    _enabledCache = enabled;
  }

  static const GmailPhotoLearningDecision _neutral =
      GmailPhotoLearningDecision(
        reject: false,
        positive: false,
        negativeScore: 0,
        positiveScore: 0,
        reason: '',
      );
''',1)
method="  static Future<GmailPhotoLearningDecision> decide({"
assert s.count(method)==1
start=s.index(method)
point="  }) async {"
pos=s.index(point,start)+len(point)
s=s[:pos]+'''
    // The v2.6.28 non-learning photo rules always remain active.
    if (!await isEnabled()) return _neutral;
'''+s[pos:]
# Old deleted-image negatives are never consulted, even if the user later
# opts into learning. Their saved examples remain intact for reversibility.
start=s.index('  static Future<GmailPhotoLearningDecision> decide({')
end=s.index('  static Future<void> rememberImage({',start)
decision=s[start:end]
needle="      if (label == 'negative') {"
assert decision.count(needle)==1,'old negative label path changed'
decision=decision.replace(needle,"      if (label == 'negative') {\n        continue; // Legacy deletions were NOT an explicit non-product vote.",1)
s=s[:start]+decision+s[end:]
start=s.index('  static Future<void> rememberImage({')
end=s.index('\n}\n',start)
method=s[start:end]
needle='  }) async {\n    try {'
assert method.count(needle)==1,'learning input method changed'
method=method.replace(needle,'''  }) async {
    // Never learn from deletion, at any settings value. Only explicitly
    // approved recovered/received products can opt in to positive learning.
    if (!product || !await isEnabled()) return;
    try {''',1)
s=s[:start]+method+s[end:]
h.write_text(s)

# Put the toggle in the business settings, NOT in the package editor, which
# the user asked to look like v2.6.28. Default false even on old installs
# where the prior adaptive-learning database exists.
p=Path('app/lib/extras.dart')
s=p.read_text()
state="  bool whatsBotSyncEnabled=true;"
assert s.count(state)==1
s=s.replace(state,state+"\n  bool gmailAdaptiveLearningEnabled=false;",1)
# Settings screen receives this new switch only, not new editor controls.
needle="    whatsBotSyncEnabled=settings['whatsBotSyncEnabled']!=false;"
assert s.count(needle)==1
s=s.replace(needle,needle+"\n    gmailAdaptiveLearningEnabled=await GmailPhotoLearningService.isEnabled();",1)
anchor="    await Store.saveSettings(settings);"
assert s.count(anchor)>=1
# Use only the SettingsPage.save method; other settings features can also save.
st=s.index('class _SettingsPageState extends State<SettingsPage> {')
en=s.find('\nclass ',st+15)
if en<0:en=len(s)
section=s[st:en]
assert section.count(anchor)==1
section=section.replace(anchor,anchor+"\n    await GmailPhotoLearningService.setEnabled(gmailAdaptiveLearningEnabled);",1)
needle="""          Text(
            'Sincronización con WhatsBot',"""
assert section.count(needle)==1
switch=r'''          Text(
            'Fotos recuperadas de Gmail',
            style:Theme.of(context).textTheme.titleMedium?.copyWith(
              fontWeight:FontWeight.bold,
            ),
          ),
          SwitchListTile(
            contentPadding:EdgeInsets.zero,
            title:const Text('Aprendizaje adaptativo (opcional)'),
            subtitle:const Text(
              'Desactivado por defecto. Solo aprende de fotos que '
              'confirmes como producto. Borrar una foto nunca cuenta '
              'como rechazo ni afecta las próximas búsquedas.',
            ),
            value:gmailAdaptiveLearningEnabled,
            onChanged:(v)=>setState(()=>gmailAdaptiveLearningEnabled=v),
          ),
          const SizedBox(height:24),
'''
section=section.replace(needle,switch+needle,1)
s=s[:st]+section+s[en:]
p.write_text(s)

# Revert the visible v31 multi-selection chrome in the package list to the
# v2.6.27/28 editor. Keep the underlying methods available for safe migrations
# and background batch tasks; only the UI reverts. No data field removed.
p=Path('app/lib/packages.dart')
s=p.read_text()
title=r'''        title: packageSelectionMode
            ? Text('\${selectedPackageIds.length} seleccionados')
            : const Text('Paquetes'),
        actions: [
          if(packageSelectionMode)
            IconButton(
              tooltip:'Seleccionar todos los visibles',
              onPressed:()=>_toggleSelectAll(f),
              icon:const Icon(Icons.select_all),
            ),
          IconButton(
            tooltip:packageSelectionMode?'Salir de selección':'Seleccionar paquetes',
            onPressed:()=>setState((){
              packageSelectionMode=!packageSelectionMode;
              if(!packageSelectionMode) selectedPackageIds.clear();
            }),
            icon:Icon(packageSelectionMode?Icons.close:Icons.checklist),
          ),
          if(!packageSelectionMode) _bulkButton(),
'''
old=r'''        title: const Text('Paquetes'),
        actions: [
          _bulkButton(),
'''
title=title.replace("\\$","$")
assert s.count(title)==1,'v57 package list app bar no longer v31'
s=s.replace(title,old,1)
# Do not remove the selection helpers; switching off the chrome is enough.
# This restores the earlier package list without dropping background scans.
leading="                      leading: packageSelectionMode\n                          ? Checkbox("
if s.count(leading)==1:
    a=s.index(leading)
    b=s.index("                      onTap:",a)
    frag=s[a:b]
    begin=frag.index("                          : Builder(builder: (_) {")
    restored="                      leading: Builder(builder: (_) {"+frag[begin+len("                          : Builder(builder: (_) {"):]
    # A simple trailing parenthesis belongs to the ternary after Builder.
    restored=restored.replace("                            }),\n","                      }),\n",1)
    s=s[:a]+restored+s[b:]
else:
    raise RuntimeError('v57 package list selection thumbnail mismatch')

# The old v28 list tap should open the editor immediately, with no selection mode.
tap=r'''                      onTap: () async {
                        if(packageSelectionMode){
                          _togglePackageSelection(p);
                          return;
                        }
                        await Navigator.push(context, MaterialPageRoute(builder: (_) => PackageEditPage(existing: p)));
                        load(forceRefresh:true);
                      },
                      onLongPress:()=>_togglePackageSelection(p),
                      trailing: packageSelectionMode
                          ? null
                          : IconButton(icon: const Icon(Icons.delete_outline), onPressed: () async { if (await confirmDelete(context, 'este paquete')) { await softDelete('packages', '\${p['id']}'); load(forceRefresh:true); } }),
'''
tap=tap.replace("\\$","$")
assert s.count(tap)==1,'v57 package list tap behavior moved'
original=r'''                      onTap: () async { await Navigator.push(context, MaterialPageRoute(builder: (_) => PackageEditPage(existing: p))); load(forceRefresh:true); },
                      trailing: IconButton(icon: const Icon(Icons.delete_outline), onPressed: () async { if (await confirmDelete(context, 'este paquete')) { await softDelete('packages', '\${p['id']}'); load(forceRefresh:true); } }),
'''.replace("\\$","$")
s=s.replace(tap,original,1)
old="      bottomNavigationBar: packageSelectionMode ? _packageSelectionBar() : null,\n      floatingActionButton: packageSelectionMode ? null : FloatingActionButton.extended("
assert s.count(old)==1,'v57 multi-select floating bar moved'
s=s.replace(old,"      floatingActionButton: FloatingActionButton.extended(",1)
p.write_text(s)

# Revert the extra client-detail photo-search button inserted in v31. The
# original "Nuevo paquete" action stays, while background Gmail remains
# accessible from the package itself.
p=Path('app/lib/clients.dart')
s=p.read_text()
start=s.index("              Align(\n                alignment: Alignment.centerLeft,\n                child: Wrap(\n                  spacing:8,")
end=s.index("              ),\n",start)+len("              ),\n")
# End first matching Align closure, avoid eating later client-detail widgets.
old=s[start:end]
if "Buscar todos en Gmail" not in old:
    # The Wrap is nested: match through this exact button text + next Align close
    end=s.index("              ),\n",s.index("label: const Text('Buscar todos en Gmail')",start))+len("              ),\n")
    old=s[start:end]
assert "Nuevo paquete" in old and "Buscar todos en Gmail" in old
original=r'''              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: createPackage,
                  icon: const Icon(Icons.add),
                  label: const Text('Nuevo paquete'),
                ),
              ),
'''
s=s[:start]+original+s[end:]
p.write_text(s)
print('v57: 2.6.28 list/editor chrome, opt-in positive-only adaptive, deletion never trains false negatives.')
