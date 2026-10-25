import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import tempfile
import time
import unittest
from pathlib import Path
from PIL import Image,ImageDraw
from astrbot_plugin_maoyu.art import render_card,render_wardrobe,sprite,font
from astrbot_plugin_maoyu.game import Game,COSTUMES

class ArtTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.p=Path(self.tmp.name)
        self.now=time.time();self.g=Game(self.p/'db');self.pet=self.g.run('a','b','领养','一二三四五六七八九十十一')[1]
    def test_all_assets_alpha(self):
        for key in COSTUMES:
            with self.subTest(key=key):
                im=sprite(key);self.assertEqual(im.mode,'RGBA');self.assertEqual(im.getchannel('A').getextrema(),(0,255));self.assertGreater(im.width,500)
    def test_all_costumes_render(self):
        for key in COSTUMES:
            self.pet['costume']=key
            output=render_card(self.pet,self.p/(key+'.png'),self.now)
            with Image.open(output) as im:self.assertEqual(im.size,(800,1040));im.verify()
    def test_long_diary_and_name(self):
        self.pet['diary']=['魔法森林：'+'蘑菇'*100];render_card(self.pet,self.p/'long.png',self.now)
    def test_sleep_card(self):
        self.pet['sleep_until']=self.now+300;render_card(self.pet,self.p/'sleep.png',self.now)
    def test_hungry_card(self):
        self.pet['food']=15;render_card(self.pet,self.p/'hungry.png',self.now)
    def test_wardrobe(self):
        render_wardrobe(self.p/'wardrobe.png',self.pet)
        with Image.open(self.p/'wardrobe.png') as im:self.assertEqual(im.size,(800,1320))
    def test_animation(self):
        render_card(self.pet,self.p/'bounce.gif',self.now,animated=True)
        with Image.open(self.p/'bounce.gif') as im:self.assertGreater(im.n_frames,1)
