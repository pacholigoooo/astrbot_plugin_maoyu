"""Local JSON-lines bridge. No network listener, shell, AstrBot or LLM dependency."""
import importlib
import json
import math
import sys
import time
import traceback
import types
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType('maoyu_shared')
package.__path__ = [str(ROOT)]
sys.modules['maoyu_shared'] = package
GameModule = importlib.import_module('maoyu_shared.game')
Art = importlib.import_module('maoyu_shared.art')


def emit(data):
    print(json.dumps(data, ensure_ascii=False), flush=True)


def main():
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    directory = Path(sys.argv[1]).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    cache = directory / 'cards'
    cache.mkdir(exist_ok=True)
    config = json.loads(sys.stdin.readline())
    def number(key, default, low, high):
        value = config.get(key, default)
        return max(low, min(high, value)) if type(value) in (int, float) and math.isfinite(value) else default
    game = GameModule.Game(directory/'maoyu.sqlite3', cooldown_scale=number('cooldownScale', 1, .1, 10),
                           utc_offset=number('utcOffset', 8, -12, 14))
    last_cleanup = 0
    emit({'ready': True})
    for line in sys.stdin:
        request = None
        try:
            request = json.loads(line)
            action = request['action']
            text, pet, kind = game.run(request['scope'], request['owner'],
                                       '看看' if action == '动图' else action,
                                       request.get('arg', ''), request.get('messageId'))
            result = {'id': request['id'], 'text': text}
            if pet is not None and config.get('autoBackup', True):
                try:
                    game.backup(directory/'backups')
                except Exception:
                    traceback.print_exc(file=sys.stderr)
            if pet is not None and kind != 'text' and config.get('sendImages', True):
                try:
                    now = time.time()
                    if now - last_cleanup > 3600:
                        last_cleanup = now
                        candidates = []
                        for file in cache.iterdir():
                            if file.suffix not in ('.png', '.gif'):
                                continue
                            stamp = file.stat().st_mtime
                            if now - stamp > 86400:
                                file.unlink(missing_ok=True)
                            else:
                                candidates.append((stamp, file))
                        for stamp, file in sorted(candidates)[:-512]:
                            if now - stamp > 600:
                                file.unlink(missing_ok=True)
                    gif = action == '动图'
                    path = cache/(uuid.uuid4().hex + ('.gif' if gif else '.png'))
                    if kind == 'wardrobe':
                        Art.render_wardrobe(path, pet)
                    else:
                        Art.render_card(pet, path, now, animated=gif)
                    result['image'] = path.name
                except Exception:
                    traceback.print_exc(file=sys.stderr)
                    result['text'] += '\n操作已保存，本次图片生成失败。'
            emit(result)
        except GameModule.GameError as exc:
            emit({'id': request.get('id') if isinstance(request, dict) else None, 'text': str(exc)})
        except Exception:
            traceback.print_exc(file=sys.stderr)
            emit({'id': request.get('id') if isinstance(request, dict) else None,
                  'text': '存档操作结果未确认，请先查看状态；不要重复购买或删除数据库。'})


if __name__ == '__main__':
    main()
