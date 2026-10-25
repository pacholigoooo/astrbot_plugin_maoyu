"""Mobile-readable UI layout using original generated pixel art, never drawn sprites."""
from pathlib import Path
from functools import lru_cache
import math
from datetime import timedelta, timezone
from PIL import Image, ImageDraw, ImageFont
from .game import COSTUMES, level, presentation
from .version import __version__

INK = '#30394f'
PAPER = '#f8f9fe'
ACCENT = '#6879ae'
MUTED = '#737d96'
LINE = '#d9def0'
PANEL = '#edf0fa'
ASSETS = Path(__file__).parent / 'assets'
CARD_SIZE = (800, 1040)
WARDROBE_SIZE = (800, 1320)

@lru_cache(maxsize=32)
def font(size):
    return ImageFont.truetype(str(ASSETS / 'MaoyuSans.otf'), size)

def sprite(costume='plain'):
    key = costume if costume in COSTUMES else 'plain'
    with Image.open(ASSETS / (key + '.png')) as source:
        return source.convert('RGBA')

def _text(draw, xy, value, size=24, color=INK):
    draw.text(xy, str(value), font=font(size), fill=color)

def _fit(draw, text, size, width):
    text = str(text)
    while text and draw.textlength(text, font=font(size)) > width:
        text = text[:-1]
    return text

def _ellipsis(draw, text, size, width):
    text = str(text)
    if draw.textlength(text, font=font(size)) <= width:
        return text
    return _fit(draw, text, size, max(0, width-draw.textlength('…', font=font(size))))+'…'

def _wrap(draw, text, size, width, max_lines):
    """Measured wrapping, explicit overflow indication, and guaranteed progress."""
    rest = str(text).replace('\r', '').replace('\n', ' ')
    lines = []
    for i in range(max_lines):
        if not rest:
            break
        if i == max_lines-1:
            lines.append(_ellipsis(draw, rest, size, width))
            break
        part = _fit(draw, rest, size, width)
        if not part:
            break
        lines.append(part)
        rest = rest[len(part):]
    return lines

def _right(draw, x, y, text, size=22, color=INK):
    _text(draw, (x-draw.textlength(str(text), font=font(size)), y), text, size, color)

def _pill(draw, xy, text, *, fill=ACCENT, color=PAPER, size=20):
    x, y = xy
    w = math.ceil(draw.textlength(text, font=font(size)))+24
    draw.rectangle((x, y, x+w, y+36), fill=fill)
    _text(draw, (x+12, y+3), text, size, color)
    return w

def _bar(draw, box, ratio, color=ACCENT):
    x, y, r, b = box
    draw.rectangle(box, fill='#dfe5f3')
    width = int((r-x+1)*max(0, min(1, ratio)))
    if width:
        draw.rectangle((x, y, x+width-1, b), fill=color)

def _compact(value):
    value = int(value)
    if value >= 100000000:
        return f'{value/100000000:.1f}亿'
    if value >= 100000:
        return f'{value/10000:.1f}万'
    return str(value)

@lru_cache(maxsize=21)
def _small_sprite(costume, size=320):
    return sprite(costume).resize((size, size), Image.Resampling.NEAREST)

@lru_cache(maxsize=8)
def _garden(width=400, height=270):
    # Crop and scale generated background without stretching its proportions.
    with Image.open(ASSETS/'garden.png') as source:
        im = source.convert('RGB')
    scale = max(width/im.width, height/im.height)
    im = im.resize((math.ceil(im.width*scale), math.ceil(im.height*scale)), Image.Resampling.NEAREST)
    x, y = (im.width-width)//2, (im.height-height)//2
    return im.crop((x, y, x+width, y+height))

def _scene(costume, mood='happy', frame=0, *, size=(400, 270)):
    width, height = size
    im = _garden(width, height).copy()
    pet_size = min(width, round(height*1.12))
    pet = _small_sprite(costume, pet_size)
    im.paste(pet, ((width-pet_size)//2, (height-pet_size)//2-(3 if frame == 1 else 0)), pet)
    return im

def _view(p, now):
    # Use the same timestamp/timezone as the textual response, even after queueing.
    return presentation(p, p.get('_display_now', now),
                        timezone(timedelta(hours=p.get('_display_offset', 8))))


def _state(p, now):
    view = _view(p, now)
    return view['state'], view['message'], view['color']


def _care(p, now):
    return _view(p, now)['care']

def render_card(p, output, now, *, animated=False):
    frames = []
    state, message, accent = _state(p, now)
    for frame in (0, 1, 0, 1) if animated else (0,):
        im = Image.new('RGB', CARD_SIZE, PAPER)
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, 799, 7), fill=ACCENT)
        _text(d, (32, 23), '东方毛玉小院', 30, ACCENT)
        _right(d, 768, 30, '幻想乡 · 陪伴日常', 20, MUTED)
        d.line((32, 75, 768, 75), fill=LINE, width=2)
        name_size = 38
        while d.textlength(p['name'], font=font(name_size)) > 510 and name_size > 22:
            name_size -= 1
        _text(d, (32, 88), p['name'], name_size)
        _right(d, 768, 98, 'Lv.'+_compact(level(p['xp'])), 28, ACCENT)
        _text(d, (32, 139), '今日装饰  /  '+COSTUMES[p['costume']]['name'], 22, MUTED)
        scene = _scene(p['costume'], frame=frame, size=(736, 312))
        im.paste(scene, (32, 182))
        d.rectangle((32, 182, 767, 493), outline=LINE, width=2)
        _pill(d, (48, 198), state, fill=accent)
        # Caption outside the artwork: no pseudo-expression changes to generated art.
        _text(d, (32, 507), message, 23, accent)
        for i, (label, key, color) in enumerate((('饱食', 'food', '#a28bb6'), ('心情', 'mood', '#bb8ca4'), ('精力', 'energy', '#7f9cc3'))):
            x = 32+i*250
            d.rectangle((x, 552, x+235, 655), fill=PANEL)
            _text(d, (x+14, 562), label, 23)
            _right(d, x+221, 564, f'{round(p[key])}/100', 21, color)
            _bar(d, (x+14, 610, x+221, 623), p[key]/100, color)
        lv = level(p['xp']); lower = 50*(lv-1)**2; upper = 50*lv**2
        _text(d, (32, 676), '成长', 22, ACCENT)
        _right(d, 768, 676, f'{_compact(p["xp"]-lower)} / {_compact(upper-lower)} 经验', 21, MUTED)
        _bar(d, (112, 689, 482, 700), (p['xp']-lower)/(upper-lower))
        for i, text in enumerate((f'团子币  {_compact(p["coins"])}', f'散步  {_compact(p["visits"])} 次', f'收藏  {len(p["souvenirs"])}/12')):
            _text(d, (32+i*250, 725), text, 22)
        d.line((32, 770, 768, 770), fill=LINE, width=2)
        _text(d, (32, 787), '小院手记', 23, ACCENT)
        _right(d, 768, 790, '完整记录：/毛玉 日记', 18, MUTED)
        entry = p['diary'][-1] if p.get('diary') else '今天的小院很安静，等你来写下第一段故事。'
        for i, line in enumerate(_wrap(d, entry, 22, 736, 2)):
            _text(d, (32, 829+i*32), line, 22)
        d.rectangle((32, 909, 767, 958), fill='#e8edf9')
        _text(d, (46, 919), _ellipsis(d, _care(p, now), 21, 706), 21, ACCENT)
        _text(d, (32, 978), '发送指令：/毛玉 喂食 · 摸摸 · 散步 · 衣柜', 20, MUTED)
        _right(d, 768, 1011, 'v'+__version__, 14, MUTED)
        frames.append(im)
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    if animated:
        frames[0].save(output, save_all=True, append_images=frames[1:], duration=[800, 650, 800, 180], loop=0)
    else:
        frames[0].save(output)
    return output

def _wardrobe_state(key, p):
    if p and key == p['costume']:
        return '穿戴中', ACCENT
    if p and key in p['owned']:
        return '已拥有', '#78839c'
    if p and p.get('gift'):
        return '首套可免费选', '#88739c'
    return f'{COSTUMES[key]["price"]} 团子币', '#88739c'

def render_wardrobe(output, p=None):
    im = Image.new('RGB', WARDROBE_SIZE, PAPER); d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 799, 7), fill=ACCENT)
    _text(d, (32, 23), '东方毛玉衣柜', 32, ACCENT)
    if p:
        _right(d, 768, 32, '团子币  '+_compact(p['coins']), 23, ACCENT)
    pages = math.ceil((len(COSTUMES)-1)/6)
    page = max(1, min(pages, int(p.get('_wardrobe_page', 1)))) if p else 1
    _text(d, (32, 78), f'{len(COSTUMES)-1}套东方装饰 · 第 {page}/{pages} 页', 23)
    banner = ('首套免费任选，选好后发送 /毛玉 购买 名称' if p and p.get('gift') else
              '已拥有的装饰可随时换上，不会再次扣款') if p else '领养后，首套主题装饰免费任选'
    d.rectangle((32, 119, 767, 165), fill='#e8edf9')
    _text(d, (46, 127), banner, 21, ACCENT)
    for i, key in enumerate(list(COSTUMES)[1+(page-1)*6:1+page*6]):
        x = 32+(i%2)*376; y = 189+(i//2)*324
        active = bool(p and key == p['costume'])
        d.rectangle((x, y, x+359, y+303), fill=PANEL, outline=ACCENT if active else LINE, width=3 if active else 1)
        im.paste(_scene(key, size=(328, 172)), (x+16, y+16))
        _text(d, (x+16, y+196), COSTUMES[key]['name'], 23, ACCENT)
        state, color = _wardrobe_state(key, p)
        _right(d, x+344, y+226, state, 18, color)
        _text(d, (x+16, y+258), COSTUMES[key]['desc'], 17, MUTED)
        if p and key not in p['owned'] and not p.get('gift') and p['coins'] < COSTUMES[key]['price']:
            _text(d, (x+16, y+282), f'还差 {COSTUMES[key]["price"]-p["coins"]} 团子币', 17, '#a16f8c')
    _text(d, (32, 1175), '购买：/毛玉 购买 灵梦    换装：/毛玉 换装 灵梦', 22, ACCENT)
    _text(d, (32, 1217), '恢复原味：/毛玉 换装 原味毛玉', 22, ACCENT)
    _text(d, (32, 1263), f'翻页：/毛玉 衣柜 {page % pages + 1}    图片不可点击，请发送指令', 20, MUTED)
    _right(d, 768, 1292, 'v'+__version__, 14, MUTED)
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    im.save(output)
    return output
