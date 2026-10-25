"""Static validation and whitelist ZIP packaging; does not import/run plugin or tests."""
import ast
import hashlib
import json
from pathlib import Path
import re
import zipfile

root = Path(__file__).resolve().parents[1]
RELEASE_FILES = ('.gitattributes', '.github/workflows/ci.yml', '.gitignore', 'ARTWORK.md', 'CHANGELOG.md', 'LICENSE', 'PRIVACY.md', 'README.md', 'RELEASE.md', 'TEST_REPORT.md', 'STATIC_REVIEW.md', '__init__.py', '_conf_schema.json', 'art.py', 'game.py', 'main.py', 'workers.py', 'metadata.yaml', 'requirements.txt', 'version.py', 'logo.png', 'assets/FONT-LICENSE.txt', 'assets/MaoyuSans.otf', 'assets/cirno.png', 'assets/garden.png', 'assets/marisa.png', 'assets/patchouli.png', 'assets/plain.png', 'assets/reimu.png', 'assets/remilia.png', 'assets/suwako.png', 'docs/status.png', 'docs/wardrobe.png', 'tests/test_adapter.py', 'tests/test_art.py', 'tests/test_game.py', 'tests/test_release.py', 'tests/test_ui_v12.py', 'tests/test_hardening_v121.py', 'tools/build_release.py', 'tools/framework_smoke.py', 'tools/subset_font.py', 'package.json', 'package-lock.json', 'KOISHI.md', 'koishi/index.cjs', 'koishi/bridge.cjs', 'koishi/worker.py', 'koishi/test.cjs', 'docs/README.md', 'assets/sakuya.png', 'assets/youmu.png', 'assets/yuyuko.png', 'assets/alice.png', 'assets/sanae.png', 'assets/yukari.png', 'assets/ran.png', 'assets/chen.png', 'assets/aya.png', 'assets/reisen.png', 'assets/tenshi.png', 'assets/flandre.png', 'tests/test_wardrobe_v140.py', 'docs/wardrobe-2.png', 'docs/wardrobe-3.png')
version = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", (root/'version.py').read_text()).group(1)
for name in RELEASE_FILES:
    p = root / name
    if not p.is_file() or any(part.is_symlink() for part in (p, *p.parents)):
        raise SystemExit('Missing file or symlink rejected: ' + name)
    if p.suffix == '.py':
        ast.parse(p.read_text(encoding='utf-8'), filename=name)
json.loads((root/'_conf_schema.json').read_text())
if 'version: v' + version not in (root/'metadata.yaml').read_text():
    raise SystemExit('Version mismatch')
output = root/'dist'
output.mkdir(exist_ok=True)
archive = output / f'astrbot_plugin_maoyu_v{version}.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for name in RELEASE_FILES:
        info = zipfile.ZipInfo('astrbot_plugin_maoyu/' + name, date_time=(2026,10,25,0,0,0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        z.writestr(info, (root/name).read_bytes())
if archive.stat().st_size >= 16_000_000:
    raise SystemExit('Archive exceeds conservative 16 MB ceiling')
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix('.sha256').write_text(f'{digest}  {archive.name}\n')
print(f'{archive.name}: {archive.stat().st_size} bytes; {len(RELEASE_FILES)} files; SHA256 {digest}')
