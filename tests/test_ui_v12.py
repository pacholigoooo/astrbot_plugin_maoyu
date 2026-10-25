"""UI semantics and edge cases; artwork is unchanged generated PNGs."""
import copy
import tempfile
import time
import unittest
from pathlib import Path
from PIL import Image, ImageDraw
from astrbot_plugin_maoyu.art import (
    _wrap, _ellipsis, _wardrobe_state, _state, _garden, _care,
    render_card, render_wardrobe, font, CARD_SIZE, WARDROBE_SIZE,
)
from astrbot_plugin_maoyu.game import Game

class MobileUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.now = time.time()
        self.pet = Game(self.root/'game.db').run('demo','demo','领养','糯米')[1]
        self.d = ImageDraw.Draw(Image.new('RGB', (800, 1040)))

    def test_free_outfit_badge(self):
        self.assertEqual(_wardrobe_state('reimu', self.pet)[0], '首套可免费选')

    def test_active_outfit_has_priority(self):
        self.pet.update(costume='reimu', owned=['plain','reimu'])
        self.assertEqual(_wardrobe_state('reimu', self.pet)[0], '穿戴中')

    def test_owned_has_priority_over_free(self):
        self.pet['owned'].append('reimu')
        self.assertEqual(_wardrobe_state('reimu', self.pet)[0], '已拥有')

    def test_price_after_gift(self):
        self.pet['gift'] = False
        self.assertEqual(_wardrobe_state('reimu', self.pet)[0], '80 团子币')

    def test_preview_without_pet(self):
        self.assertEqual(_wardrobe_state('reimu', None)[0], '80 团子币')
        p = render_wardrobe(self.root/'nested'/'wardrobe.png')
        with Image.open(p) as im: self.assertEqual(im.size, WARDROBE_SIZE)

    def test_sleep_has_priority(self):
        self.pet.update(sleep_until=self.now+61, food=15)
        state = _state(self.pet,self.now)
        self.assertEqual(state[0], '休息中'); self.assertIn('2 分钟', state[1])
        self.assertIn('起床', _care(self.pet,self.now))

    def test_low_energy_and_mood_states(self):
        self.pet.update(food=80, energy=10)
        self.assertEqual(_state(self.pet,self.now)[0], '有点困了')
        self.pet.update(energy=80,mood=20)
        self.assertEqual(_state(self.pet,self.now)[0], '想你陪陪')

    def test_truncation_visible_and_measured(self):
        lines = _wrap(self.d, '很长的手记'*100, 22, 736, 2)
        self.assertEqual(len(lines),2); self.assertTrue(lines[-1].endswith('…'))
        for line in lines:
            self.assertLessEqual(self.d.textlength(line,font=font(22)),736)

    def test_short_text_unchanged(self):
        self.assertEqual(_ellipsis(self.d,'红叶',22,100),'红叶')
        self.assertEqual(_wrap(self.d,'',22,736,2),[])

    def test_empty_diary(self):
        self.pet['diary'] = []
        render_card(self.pet,self.root/'empty.png',self.now)

    def test_render_does_not_mutate_save(self):
        before = copy.deepcopy(self.pet)
        render_card(self.pet,self.root/'card.png',self.now)
        render_wardrobe(self.root/'wardrobe.png',self.pet)
        self.assertEqual(self.pet,before)

    def test_background_size_and_cache_unchanged(self):
        original = _garden(736,312).tobytes()
        render_card(self.pet,self.root/'card.png',self.now)
        self.assertEqual(original,_garden(736,312).tobytes())

    def test_extreme_values_and_animation(self):
        self.pet.update(name='WWWWWWWWWWWW',coins=10**9,visits=10**7,xp=10**9)
        path = render_card(self.pet,self.root/'big.gif',self.now,animated=True)
        with Image.open(path) as im:
            self.assertEqual(im.size,CARD_SIZE); self.assertGreater(im.n_frames,1)
