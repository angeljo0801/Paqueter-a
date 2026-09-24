from pathlib import Path
import re
import shutil
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else "agentes")
overrides = Path("agentes_overrides")

shutil.copy2(overrides / "clients.dart", root / "lib" / "clients.dart")
shutil.copy2(overrides / "orders.dart", root / "lib" / "orders.dart")\nshutil.copy2(overrides / "store_ocr.dart", root / "lib" / "store_ocr.dart")

main = root / "lib" / "main.dart"
s = main.read_text()
contact_import = "import 'package:flutter_contacts/flutter_contacts.dart';"
if contact_import not in s:
    s = s.replace(
        "import 'package:flutter/material.dart';",
        "import 'package:flutter/material.dart';\n" + contact_import,
    )
ocr_import = "import 'package:google_mlkit_text_recognition/google_mlkit_text_recognition.dart';"
if ocr_import not in s:
    s = s.replace(
        "import 'package:flutter/material.dart';",
        "import 'package:flutter/material.dart';\n" + ocr_import,
    )

path_import = "import 'package:path_provider/path_provider.dart';"
if path_import not in s:
    s = s.replace(
        "import 'package:flutter/material.dart';",
        "import 'package:flutter/material.dart';\n" + path_import,
    )

part_line = "part 'store_ocr.dart';"
if part_line not in s:
    anchor = "part 'orders.dart';"
    if anchor in s:
        s = s.replace(anchor, anchor + "\n" + part_line)
    else:
        s += "\n" + part_line + "\n"

main.write_text(s)

pub = root / "pubspec.yaml"
s = pub.read_text()
if "flutter_contacts:" not in s:
    s = s.replace(
        "  shared_preferences: ^2.5.3\n",
        "  shared_preferences: ^2.5.3\n  flutter_contacts: ^2.5.0\n",
    )
if "google_mlkit_text_recognition:" not in s:
    s = s.replace(
        "  image_picker: ^1.1.2\n",
        "  image_picker: ^1.1.2\n  google_mlkit_text_recognition: ^0.15.1\n",
    )
    if "google_mlkit_text_recognition:" not in s:
        s = s.replace(
            "  shared_preferences: ^2.5.3\n",
            "  shared_preferences: ^2.5.3\n  google_mlkit_text_recognition: ^0.15.1\n",
        )

if "path_provider:" not in s:
    s = s.replace(
        "  shared_preferences: ^2.5.3\n",
        "  shared_preferences: ^2.5.3\n  path_provider: ^2.1.5\n",
    )

pub.write_text(s)

store = root / "lib" / "store.dart"
s = store.read_text()
replacement = """double orderStoreCost(Map<String, dynamic> e) => number(e['storeCost'] ?? e['storeTotal']);
bool orderIsUnassigned(Map<String, dynamic> e) => e['unassigned'] == true || '${e['clientId'] ?? ''}'.trim().isEmpty;
double orderSavedClientTotal(Map<String, dynamic> e) => number(e['clientTotal']);
double orderClientTotal(Map<String, dynamic> e) => orderIsUnassigned(e) ? 0.0 : orderSavedClientTotal(e);
double orderAgentMargin(Map<String, dynamic> e) => orderIsUnassigned(e) ? 0.0 : orderSavedClientTotal(e) - orderStoreCost(e);

double packageWeight"""
s, count = re.subn(
    r"double orderStoreCost[\s\S]*?double packageWeight",
    replacement,
    s,
    count=1,
)
if count != 1:
    raise SystemExit("No se pudo actualizar la lógica común de pedidos")
store.write_text(s)
