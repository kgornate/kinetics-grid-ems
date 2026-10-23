from pathlib import Path
import json
import sys
backend = Path(sys.argv[1]).resolve()
target = Path(__file__).resolve().parents[1] / "lib/core/presentation/kalpa_signal_catalog.dart"
out={}
for filename in ['lineage_bms_catalog.json','elecod_pcs_catalog.json']:
 c=json.load(open(backend / 'generated_protocols' / filename))
 for p in c['points']:
  role={'bank':'bms_bank','rack':'bms_rack','pcs':'pcs','environment':'environment'}[p['scope']]
  # Compact snapshots omit labels/category/address. Carry protocol metadata only;
  # values and scaling remain entirely owned by the gateway backend.
  m={k:p[k] for k in ['name_en','category','address','address_hex','unit','data_type','enum','bitfields','access','reserved','notes'] if p.get(k) not in (None,{},[],False)}
  out.setdefault(role,{})[p['key']]=m
s=json.dumps(out,ensure_ascii=False,separators=(',',':')).replace('$',r'\$')
target.write_text('// Generated display metadata from the supplied Lineage V05 and Elecod V2.7.0 catalogs.\n// No measured values, transport settings, scale factors or credentials.\nconst Map<String, dynamic> kalpaSignalCatalog = '+s+';\n')
print({k:len(v) for k,v in out.items()})
