from pathlib import Path

main = Path('app/lib/main.dart')
ms = main.read_text()

if "part 'server_recovery.dart';" not in ms:
    anchor = "part 'whatsbot_sync.dart';"
    if anchor not in ms:
        raise SystemExit('No se encontró whatsbot_sync.dart en main.dart')
    ms = ms.replace(anchor, anchor + "\npart 'server_recovery.dart';", 1)

recovery_call = """  try {
    await PaqueteriaServerRecoveryService.restoreIfLocalEmpty();
  } catch (_) {}
"""
main_anchor = "Future<void> main() async {\n  WidgetsFlutterBinding.ensureInitialized();\n"
if recovery_call not in ms:
    if main_anchor not in ms:
        raise SystemExit('No se encontró main() async compatible para recuperación')
    ms = ms.replace(main_anchor, main_anchor + recovery_call, 1)

main.write_text(ms)

extras = Path('app/lib/extras.dart')
ex = extras.read_text()

if 'bool recovering=false;' not in ex:
    ex = ex.replace(
        '  bool syncing=false;\n',
        '  bool syncing=false;\n  bool recovering=false;\n',
        1,
    )

recover_method = """
  Future<void>recoverNow()async{
    if(recovering)return;
    setState(()=>recovering=true);
    try{
      await save();
      final result=await PaqueteriaServerRecoveryService.restoreCoreData();
      if(mounted){
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content:Text(
            'Recuperación terminada: ${result['clients']??0} clientes · '
            '${result['purchases']??0} compras · ${result['packages']??0} paquetes en el teléfono.'
          )),
        );
      }
    }catch(e){
      if(mounted){
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content:Text('No se pudo recuperar desde Railway: $e')),
        );
      }
    }finally{
      if(mounted)setState(()=>recovering=false);
    }
  }

"""
settings_build_anchor = "  @override\n  Widget build(BuildContext context){\n    if(!loaded)return const Scaffold"
if 'Future<void>recoverNow()async{' not in ex:
    if settings_build_anchor not in ex:
        raise SystemExit('No se encontró el build de SettingsPage')
    ex = ex.replace(
        settings_build_anchor,
        recover_method + settings_build_anchor,
        1,
    )

button_anchor = """          const SizedBox(height:12),
          OutlinedButton.icon(
            onPressed:syncing?null:syncNow,
"""
recovery_button = """          const SizedBox(height:12),
          FilledButton.tonalIcon(
            onPressed:(recovering||syncing)?null:recoverNow,
            icon:recovering
              ? const SizedBox.square(dimension:18,child:CircularProgressIndicator(strokeWidth:2))
              : const Icon(Icons.download_for_offline_outlined),
            label:Text(recovering?'Recuperando…':'Restaurar desde Railway (solo descargar)'),
          ),
          const SizedBox(height:8),
          OutlinedButton.icon(
            onPressed:(syncing||recovering)?null:syncNow,
"""
if 'Restaurar desde Railway (solo descargar)' not in ex:
    if button_anchor not in ex:
        raise SystemExit('No se encontró el botón de sincronización de SettingsPage')
    ex = ex.replace(button_anchor, recovery_button, 1)

ex = ex.replace(
    "'El botón manual fuerza el envío completo aunque los datos no hayan cambiado.'",
    "'Usa Restaurar para descargar sin sobrescribir el servidor. El botón manual de sincronización también puede subir datos.'",
    1,
)

extras.write_text(ex)
