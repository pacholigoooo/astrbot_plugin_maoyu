"""Standalone game rules. No AstrBot, network or LLM dependency."""
import json
from contextlib import closing
import math
import random
import sqlite3
import time
import threading
import uuid
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

COSTUMES = {
    'plain': {'name': '原味毛玉', 'price': 0, 'desc': '软乎乎的本来模样'},
    'reimu': {'name': '灵梦', 'price': 80, 'desc': '红白蝴蝶结 · 小御币'},
    'marisa': {'name': '魔理沙', 'price': 100, 'desc': '黑色魔女帽 · 小扫帚'},
    'cirno': {'name': '琪露诺', 'price': 80, 'desc': '蓝色蝴蝶结 · 六枚冰翼'},
    'patchouli': {'name': '帕秋莉', 'price': 100, 'desc': '月亮睡帽 · 迷你魔导书'},
    'remilia': {'name': '蕾米莉亚', 'price': 120, 'desc': '粉色软帽 · 蝙蝠翅膀'},
    'suwako': {'name': '诹访子', 'price': 120, 'desc': '青蛙眼帽 · 软绵绵'},
}
WALKS = [
    ('博丽神社', '毛玉钻进落叶堆，顶着一片红叶滚了回来。', 15, '红叶'),
    ('雾之湖', '它追着冰面上的倒影转圈，带回一颗凉凉的玻璃珠。', 18, '湖畔玻璃珠'),
    ('魔法森林', '蘑菇伞下躲了会儿雨。回家时，毛尖沾着草木香。', 20, '蘑菇邮票'),
    ('红魔馆', '门卫陪它晒了一会儿太阳，送了一个小小的茶点盒。', 22, '茶点盒'),
    ('人间之里', '它帮摊主追回一团滚走的线，得到一枚纽扣作谢礼。', 16, '花纹纽扣'),
    ('守矢神社', '风把它吹成了一颗蒲公英。落地时，怀里多了一串铃。', 24, '风铃碎片'),
    ('香霖堂', '它在旧物堆里找到一块发亮的圆片，叼回来当镜子。', 18, '旧唱片'),
    ('白玉楼', '它追了一路花瓣，最后在台阶上睡成一小团。', 20, '樱花书签'),
    ('永远亭', '它在竹林里迷了半刻，跟着兔子的脚印找到了回家的路。', 21, '竹叶小船'),
    ('妖怪之山', '山风把毛吹得蓬蓬的。一枚羽毛轻轻落在头上。', 23, '天狗羽毛'),
    ('图书馆', '它缩在书边听翻页声，把掉下来的丝带仔细卷好。', 19, '紫色书签'),
    ('河岸', '它把小石子排成一列，挑了最圆的一颗带回家。', 17, '圆石子'),
]
HELP = ('养毛玉 · 指令\n'
        '/毛玉 领养 名字　 /毛玉 看看\n'
        '/毛玉 喂食　 /毛玉 摸摸　 /毛玉 玩耍\n'
        '/毛玉 散步　 /毛玉 睡觉　 /毛玉 起床\n'
        '/毛玉 签到　 /毛玉 衣柜　 /毛玉 图鉴\n'
        '/毛玉 购买 灵梦　 /毛玉 换装 灵梦\n'
        '/毛玉 改名 名字　 /毛玉 动图\n'
        '/毛玉 日记　 /毛玉 成就　 /毛玉 帮助\n'
        '新领养可免费选一套主题装饰。喂食免费，装饰永久持有。\n'
        '每个群独立养一只；私聊另存。长期不来不会死亡。')

ACHIEVEMENTS = {
    'first_walk': ('初次出门', '完成1次散步', 1, 'visits', 10),
    'traveler': ('小小旅行家', '完成10次散步', 10, 'visits', 30),
    'collector': ('口袋收藏家', '收集6种纪念品', 6, 'souvenirs', 30),
    'wardrobe': ('换装爱好者', '拥有3套主题装饰', 3, 'owned', 30),
    'companion': ('熟悉的掌心', '升到5级', 5, 'level', 40),
    'all_places': ('幻想乡漫游', '收齐12种纪念品', 12, 'souvenirs', 60),
}
READ_ONLY = {'看看', '衣柜', '图鉴', '日记', '成就', '帮助'}

class GameError(ValueError):
    pass

def clean_name(value):
    value = unicodedata.normalize('NFKC', str(value)).strip()
    if not 1 <= len(value) <= 12:
        raise GameError('名字请用 1～12 个字。例：/毛玉 领养 糯米')
    if any(unicodedata.category(c).startswith('C') or c in '\n\r<>[]' for c in value):
        raise GameError('名字中请不要放控制字符、换行或消息标记。')
    return value

def level(xp):
    return 1 + math.isqrt(max(0, int(xp)) // 50)

def resolve_costume(name):
    name = name.strip()
    aliases = {'原味': 'plain', '卸下': 'plain', '帕琪': 'patchouli', '蕾米': 'remilia', '青蛙帽': 'suwako'}
    if name in aliases:
        return aliases[name]
    for key, info in COSTUMES.items():
        if name in (key, info['name']):
            return key
    raise GameError('没有这套装饰。发送 /毛玉 衣柜 查看名称。')

class Game:
    def __init__(self, db, *, clock=time.time, rng=None, cooldown_scale=1, utc_offset=8):
        self.path = Path(db)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.rng = rng or random.Random()
        self.scale = max(0.1, min(10.0, float(cooldown_scale)))
        self._backup_lock = threading.Lock()
        self.tz = timezone(timedelta(hours=max(-12, min(14, float(utc_offset)))))
        with closing(self.connect()) as con, con:
            version = con.execute('PRAGMA user_version').fetchone()[0]
            if version > 2:
                raise RuntimeError('数据库来自更新版本，请勿用旧插件覆盖；先恢复兼容版本。')
            if version == 1:
                before = self.path.with_name(self.path.stem + '.pre-v1.1.sqlite3')
                if not before.exists():
                    temporary=before.with_name(uuid.uuid4().hex+'.pending')
                    try:
                        with closing(sqlite3.connect(temporary)) as target:
                            con.backup(target)
                        temporary.replace(before)
                    finally:
                        if temporary.exists():temporary.unlink()
            con.execute('PRAGMA journal_mode=WAL')
            con.execute('CREATE TABLE IF NOT EXISTS pets (scope TEXT NOT NULL, owner TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(scope,owner))')
            con.execute('CREATE TABLE IF NOT EXISTS receipts (scope TEXT NOT NULL, owner TEXT NOT NULL, message_id TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(scope, owner, message_id))')
            con.execute('CREATE INDEX IF NOT EXISTS receipts_age ON receipts(created)')
            con.execute('PRAGMA user_version=2')

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def _refresh(self, pet, now):
        # Monotonic cursor: clock rollback cannot duplicate recovery or decay.
        prev = pet['updated']
        if now <= prev:
            return
        sleeping = max(0, min(now, pet['sleep_until']) - prev)
        awake = max(0, now - prev - sleeping)
        # Long absence is gentle; no death, illness or loss of cosmetics.
        pet['food'] = max(15, pet['food'] - min(awake / 3600, 24) * 1.5 - sleeping / 3600 * 0.4)
        pet['mood'] = max(20, pet['mood'] - min(awake / 3600, 24) * 0.8)
        pet['energy'] = min(100, pet['energy'] + sleeping / 3600 * 24 + min(awake / 3600, 24) * 2)
        pet['updated'] = now

    def _cooldown(self, pet, action, seconds, now):
        last = pet['cooldowns'].get(action)
        remaining = 0 if last is None else last + seconds * self.scale - now
        if remaining > 0:
            raise GameError(f'先让它缓一缓，{max(1, math.ceil(remaining / 60))} 分钟后再来{action}。')
        pet['cooldowns'][action] = now

    def run(self, scope, owner, action='看看', arg='', message_id=None):
        """Atomic read/modify/write per command, safe across threads/processes."""
        aliases = {'帮助':'帮助','help':'帮助','菜单':'帮助','状态':'看看','查看':'看看','投喂':'喂食','玩':'玩耍','抚摸':'摸摸','唤醒':'起床','装扮':'换装'}
        action = aliases.get(action, action)
        if action == '帮助':
            return HELP, None, 'text'
        con = self.connect()
        try:
            read_only = action in READ_ONLY
            con.execute('BEGIN' if read_only else 'BEGIN IMMEDIATE')
            now = float(self.clock())
            if message_id and action not in READ_ONLY:
                existing = con.execute('SELECT 1 FROM receipts WHERE scope=? AND owner=? AND message_id=? AND created >= ?', (scope, owner, str(message_id), now - 7 * 86400)).fetchone()
                if existing:
                    con.rollback()
                    return '这条指令已经处理过，不会重复扣款或发奖。', None, 'text'
            row = con.execute('SELECT payload FROM pets WHERE scope=? AND owner=?', (scope, owner)).fetchone()
            pet = json.loads(row[0]) if row else None
            if row is not None and not isinstance(pet, dict):
                raise GameError('存档格式异常，请联系管理员；原文件已保留。')
            if pet is not None:
                for key in ('_presentation', '_display_now', '_display_offset'):
                    pet.pop(key, None)
                self._validate(pet)
                if 'achievements' not in pet:
                    # v1.0 save upgrade: recognize existing milestones without minting retroactive rewards.
                    pet['achievements'] = [k for k, info in ACHIEVEMENTS.items() if self._progress(pet, info) >= info[2]]
            if action == '领养':
                if pet:
                    raise GameError('你已经有一只毛玉啦。用 /毛玉 改名 新名字 给它改名。')
                pet = dict(name=clean_name(arg or '糯米'), food=85., mood=85., energy=90., xp=0, coins=40,
                           costume='plain', owned=['plain'], gift=True, souvenirs=[], visits=0,
                           created=now, updated=now, sleep_until=0, daily='', cooldowns={},
                           diary=['今天起，我们一起生活。'], achievements=[])
                text = f'{pet["name"]}从草丛里探出头，轻轻蹭了蹭你的手。\n领养成功！去 /毛玉 衣柜 免费选第一套装饰。'
                kind = 'card'
            elif pet is None:
                raise GameError('先领养一只吧：/毛玉 领养 糯米')
            else:
                self._refresh(pet, now)
                before={k:pet[k] for k in ('food','mood','energy','xp','coins')}
                text, kind = self._act(pet, action, arg, now)
                if action in ('喂食','摸摸','玩耍','散步'):
                    changes=[]
                    for key,label in (('food','饱食'),('mood','心情'),('energy','精力'),('xp','经验'),('coins','团子币')):
                        delta=pet[key]-before[key]
                        if abs(delta)>0.001:
                            changes.append(f'{label} {delta:+.1f}'.rstrip('0').rstrip('.'))
                    if changes:text += '\n'+' · '.join(changes)
                if level(pet['xp'])>level(before['xp']):text += f'\n长大一点啦！现在是 Lv.{level(pet["xp"])}。'
                if action not in READ_ONLY:
                    awards = self._award(pet)
                    if awards:
                        text += '\n' + '\n'.join(awards)
            if message_id and action not in READ_ONLY:
                con.execute('DELETE FROM receipts WHERE created < ?', (now - 7 * 86400,))
                con.execute('INSERT INTO receipts VALUES (?,?,?,?)', (scope, owner, str(message_id), now))
            if not read_only:
                con.execute('INSERT INTO pets(scope,owner,payload) VALUES(?,?,?) ON CONFLICT(scope,owner) DO UPDATE SET payload=excluded.payload',
                            (scope, owner, json.dumps(pet, ensure_ascii=False)))
            con.commit()
            # Return detached payload; rendering never writes into game state.
            pet['_display_now'] = now
            pet['_display_offset'] = self.tz.utcoffset(None).total_seconds() / 3600
            return text, pet, kind
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _act(self, p, action, arg, now):
        name = p['name']
        sleeping = p['sleep_until'] > now
        if action in ('喂食', '摸摸', '玩耍', '散步') and sleeping:
            raise GameError('毛玉正在睡觉。可以等它睡醒，或发送 /毛玉 起床。')
        if action == '看看':
            return self.status(p, now), 'card'
        if action == '日记':
            return '毛玉手记 · 最近五条\n' + '\n\n'.join(p['diary']), 'text'
        if action == '成就':
            lines = ['毛玉成长册 · 只奖励一次']
            for key, info in ACHIEVEMENTS.items():
                title, desc, target, _, bonus = info
                progress = min(target,self._progress(p,info))
                state = '已完成' if key in p['achievements'] else f'{progress}/{target}'
                lines.append(f'{title} · {state}\n{desc} · 奖励{bonus}币')
            return '\n'.join(lines), 'text'
        if action == '签到':
            day = datetime.fromtimestamp(now, self.tz).date().isoformat()
            # Also rejects older local days if server clock goes backwards.
            if p['daily'] >= day:
                raise GameError('今天的点心钱已经领过了，明天再来吧。')
            p['daily'] = day
            p['coins'] += 40
            text = '今日点心钱 +40 团子币。毛玉把硬币一枚枚摆好了。'
        elif action == '喂食':
            if p['food'] >= 95:
                raise GameError('它已经吃饱啦，先把点心收好。')
            self._cooldown(p, action, 900, now)
            p['food'] = min(100, p['food'] + 30)
            p['mood'] = min(100, p['mood'] + 4)
            p['xp'] += 5
            text = f'{name}抱住一小块米糕，吃得毛尖都在晃。'
        elif action == '摸摸':
            self._cooldown(p, action, 600, now)
            p['mood'] = min(100, p['mood'] + 12)
            p['xp'] += 3
            text = f'{name}往你的掌心拱了拱，发出轻轻的呼噜声。'
        elif action == '玩耍':
            if p['energy'] < 15 or p['food'] < 20:
                raise GameError('先吃点东西、休息一下吧。玩耍需要精力15、饱食20。')
            self._cooldown(p, action, 1800, now)
            p['energy'] -= 15
            p['food'] -= 5
            p['mood'] = min(100, p['mood'] + 18)
            p['xp'] += 12
            text = f'{name}追着线球扑了三次，最后把自己也裹了进去。'
        elif action == '散步':
            if p['energy'] < 20 or p['food'] < 25:
                raise GameError('出门需要精力20、饱食25，先照顾好它吧。')
            self._cooldown(p, action, 3600, now)
            place, event, coins, souvenir = self.rng.choice(WALKS)
            p['energy'] -= 20
            p['food'] -= 10
            p['mood'] = min(100, p['mood'] + 10)
            p['xp'] += 20
            p['coins'] += coins
            p['visits'] += 1
            first = souvenir not in p['souvenirs']
            if first:
                p['souvenirs'].append(souvenir)
            p['diary'] = (p['diary'] + [f'{datetime.fromtimestamp(now,self.tz):%m-%d %H:%M} · {place}：{event}'])[-5:]
            text = f'散步 · {place}\n{event}\n' + (f'新收藏：{souvenir}' if first else f'再次遇见：{souvenir}')
        elif action == '睡觉':
            if sleeping:
                raise GameError('它已经睡着啦。')
            p['sleep_until'] = now + 4 * 3600
            text = '毛玉缩进小窝，睡成了一团。每小时恢复24精力，4小时后自然醒。'
        elif action == '起床':
            if not sleeping:
                raise GameError('它已经醒着啦。')
            p['sleep_until'] = 0
            text = '毛玉揉揉眼睛，慢吞吞地伸了个懒腰。'
        elif action == '衣柜':
            lines = ['毛玉衣柜 · 永久装饰（纯外观）']
            for key, item in COSTUMES.items():
                state = '穿戴中' if key == p['costume'] else ('已拥有' if key in p['owned'] else str(item['price']) + '币')
                lines.append(f'{item["name"]} · {state}')
            lines += ['第一套主题装饰免费任选。' if p['gift'] else f'余额：{p["coins"]} 团子币',
                      '/毛玉 购买 灵梦　/毛玉 换装 灵梦']
            return '\n'.join(lines), 'wardrobe'
        elif action == '购买':
            key = resolve_costume(arg)
            if key in p['owned']:
                raise GameError('这套已经在衣柜里啦，用 /毛玉 换装 ' + COSTUMES[key]['name'])
            price = 0 if p['gift'] else COSTUMES[key]['price']
            if p['coins'] < price:
                raise GameError(f'还差 {price - p["coins"]} 团子币。签到和散步都能获得。')
            p['coins'] -= price
            p['owned'].append(key)
            p['costume'] = key
            p['gift'] = False
            text = f'已获得并穿上「{COSTUMES[key]["name"]}」装饰。' + ('首次赠礼，不扣团子币。' if price == 0 else f'花费 {price} 团子币。')
        elif action == '换装':
            key = resolve_costume(arg)
            if key not in p['owned']:
                raise GameError('衣柜里还没有这套。先发送 /毛玉 购买 ' + COSTUMES[key]['name'])
            p['costume'] = key
            text = f'{name}穿好了「{COSTUMES[key]["name"]}」，得意地转了一圈。'
        elif action == '改名':
            p['name'] = clean_name(arg)
            text = f'以后就叫 {p["name"]} 啦。'
        elif action == '图鉴':
            lines = [f'散步收藏 {len(p["souvenirs"])}/{len(WALKS)} · 出门 {p["visits"]} 次']
            lines += [f'{"●" if s in p["souvenirs"] else "○"} {s if s in p["souvenirs"] else "未发现"} · {place}' for place, _, _, s in WALKS]
            return '\n'.join(lines), 'text'
        else:
            raise GameError('没有这个操作。发送 /毛玉 帮助 查看指令。')
        return text, 'card'

    def status(self, p, now=None):
        now = self.clock() if now is None else now
        state = presentation(p, now, self.tz)['state']
        return (f'{p["name"]} · Lv.{level(p["xp"])} · {state}\n'
                f'饱食 {round(p["food"])} / 心情 {round(p["mood"])} / 精力 {round(p["energy"])}\n'
                f'团子币 {p["coins"]} · 装饰 {COSTUMES[p["costume"]]["name"]}\n'
                + self.hint(p,now))


    @staticmethod
    def _progress(p,info):
        field=info[3]
        if field=='souvenirs':return len(p['souvenirs'])
        if field=='owned':return max(0,len(p['owned'])-1)
        if field=='level':return level(p['xp'])
        return p[field]

    def _award(self,p):
        lines=[]
        for key,info in ACHIEVEMENTS.items():
            if key not in p['achievements'] and self._progress(p,info)>=info[2]:
                p['achievements'].append(key)
                p['coins']+=info[4]
                lines.append(f'获得成就「{info[0]}」· 团子币 +{info[4]}')
        return lines

    def hint(self, p, now):
        return presentation(p, now, self.tz)['care']

    @staticmethod
    def _validate(p):
        def invalid():
            raise GameError('存档字段或关联关系异常，请联系管理员；原文件已保留。')
        if not isinstance(p, dict):
            invalid()
        for key in ('food', 'mood', 'energy', 'created', 'updated', 'sleep_until'):
            value = p.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                invalid()
        for key in ('xp', 'coins', 'visits'):
            if type(p.get(key)) is not int or p[key] < 0:
                invalid()
        if any(p[key] > 100 for key in ('food', 'mood', 'energy')):
            invalid()
        if type(p.get('gift')) is not bool:
            invalid()
        for key in ('owned', 'souvenirs', 'diary'):
            if not isinstance(p.get(key), list) or not all(isinstance(v, str) for v in p[key]):
                invalid()
        owned = p['owned']
        souvenirs = p['souvenirs']
        valid_souvenirs = {item[3] for item in WALKS}
        if (len(owned) != len(set(owned)) or 'plain' not in owned
                or any(k not in COSTUMES for k in owned)
                or not isinstance(p.get('costume'), str) or p['costume'] not in owned):
            invalid()
        if p['gift'] and owned != ['plain']:
            invalid()
        if (len(souvenirs) != len(set(souvenirs))
                or any(v not in valid_souvenirs for v in souvenirs)
                or len(souvenirs) > p['visits'] or len(p['diary']) > 5):
            invalid()
        if not isinstance(p.get('name'), str) or clean_name(p['name']) != p['name']:
            invalid()
        if not isinstance(p.get('daily'), str) or not isinstance(p.get('cooldowns'), dict):
            invalid()
        if p['daily']:
            try:
                if datetime.strptime(p['daily'], '%Y-%m-%d').date().isoformat() != p['daily']:
                    invalid()
            except ValueError:
                invalid()
        if any(k not in ('喂食', '摸摸', '玩耍', '散步') or type(v) not in (int, float)
               or not math.isfinite(v) or v < 0 for k, v in p['cooldowns'].items()):
            invalid()
        if 'achievements' in p:
            awards = p['achievements']
            if (not isinstance(awards, list) or not all(isinstance(k, str) for k in awards)
                    or len(awards) != len(set(awards)) or any(k not in ACHIEVEMENTS for k in awards)):
                invalid()

    def backup(self,directory,keep=7):
        """One consistent SQLite backup per UTC day. Does not copy a live WAL file."""
        day=datetime.fromtimestamp(self.clock(),timezone.utc).date().isoformat()
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
        destination=directory/f'maoyu-{day}.sqlite3'
        with self._backup_lock:
            if destination.exists():return destination
            temporary=directory/(uuid.uuid4().hex+'.pending')
            try:
                with closing(self.connect()) as source, closing(sqlite3.connect(temporary)) as target:
                    source.backup(target)
                temporary.replace(destination)
            finally:
                if temporary.exists():temporary.unlink()
            for old in sorted(directory.glob('maoyu-????-??-??.sqlite3'))[:-keep]:
                old.unlink()
        return destination


def presentation(p, now, tz=None):
    """Single state/priority model shared by text and image output."""
    tz = timezone(timedelta(hours=8)) if tz is None else tz
    if p['sleep_until'] > now:
        minutes = math.ceil((p['sleep_until'] - now) / 60)
        state, message, color = '休息中', f'约 {minutes} 分钟后自然醒', '#686488'
        care = f'再睡 {minutes} 分钟自然醒，也可 /毛玉 起床'
    else:
        if p['food'] < 35:
            state, message, color = '想吃点心', '小肚子咕咕叫，喂一口就好', '#956239'
        elif p['energy'] < 25:
            state, message, color = '有点困了', '今天玩累了，回窝休息一会儿', '#686488'
        elif p['mood'] < 40:
            state, message, color = '想你陪陪', '摸摸这团软乎乎的小家伙', '#9b5f6d'
        else:
            state, message, color = '精神不错', '今天也想和你待在一起', '#466653'
        if p['food'] < 50:
            care = '现在适合喂点心：/毛玉 喂食'
        elif p['energy'] < 25:
            care = '让它好好休息：/毛玉 睡觉'
        elif p['mood'] < 40:
            care = '陪它待一会儿：/毛玉 摸摸'
        elif p['gift']:
            care = '首套装饰免费任选：/毛玉 衣柜'
        elif p['daily'] < datetime.fromtimestamp(now, tz).date().isoformat():
            care = '今天的点心钱还没领：/毛玉 签到'
        else:
            care = '可以去看看成长记录：/毛玉 成就'
    return dict(state=state, message=message, color=color, care=care)
