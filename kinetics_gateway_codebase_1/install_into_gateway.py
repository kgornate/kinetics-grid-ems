#!/usr/bin/env python3
"""Safely add the optional read-only HMI to an existing FastAPI gateway source tree.

Only app/local_hmi/ is copied; a two-line import/register hook is appended to
app/main.py if absent. Original gateway services, Central Sync and register
catalogs are not replaced.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOOK = '''\n\n# Optional local HDMI HMI (read-only client of protected gateway APIs).\nfrom app.local_hmi.router import router as local_hmi_router\napp.include_router(local_hmi_router)\n'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('gateway_dir', type=Path, help='Existing gateway root containing app/main.py')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    root = args.gateway_dir.expanduser().resolve()
    main_py = root / 'app' / 'main.py'
    if not main_py.is_file():
        raise SystemExit(f'Invalid gateway tree: {main_py} not found')
    current = main_py.read_text(encoding='utf-8')
    if 'app = FastAPI(' not in current and 'app=FastAPI(' not in current:
        raise SystemExit('Unknown app/main.py structure: expected FastAPI app. No changes made.')
    source_dir = HERE / 'app' / 'local_hmi'
    target_dir = root / 'app' / 'local_hmi'
    for filename in ('__init__.py', 'router.py', 'index.html', 'styles.css', 'app.js'):
        if not (source_dir / filename).is_file():
            raise SystemExit(f'Incomplete HMI package: missing {filename}')
    need_hook = 'app.include_router(local_hmi_router)' not in current
    print(f'Target: {root}')
    print(f'Action: copy {len(list(source_dir.iterdir()))} HMI files and '+ ('append router hook' if need_hook else 'keep existing router hook'))
    if args.dry_run:
        print('Dry run: no files changed.'); return
    if target_dir.exists():
        stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
        backup=target_dir.with_name(f'local_hmi.backup_{stamp}')
        shutil.copytree(target_dir, backup)
        print(f'HMI directory backup: {backup}')
    if need_hook:
        stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = main_py.with_name(f'main.py.backup_hmi_{stamp}')
        shutil.copy2(main_py, backup)
        main_py.write_text(current.rstrip()+HOOK,encoding='utf-8')
        print(f'Main file backup: {backup}')
    target_dir.mkdir(parents=True, exist_ok=True)
    for filename in ('__init__.py', 'router.py', 'index.html', 'styles.css', 'app.js'):
        shutil.copy2(source_dir / filename, target_dir / filename)
    print('Installed. Restart the EXISTING gateway service during a permitted maintenance window.')
    print('Then open http://<gateway-host>:<gateway-port>/hmi/')

if __name__=='__main__':
    main()
