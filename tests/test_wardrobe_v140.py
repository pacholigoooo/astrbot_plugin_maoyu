import tempfile
import unittest
from pathlib import Path
from astrbot_plugin_maoyu.game import Game, GameError, COSTUMES
from astrbot_plugin_maoyu.art import render_wardrobe, WARDROBE_SIZE
from PIL import Image

class ExpandedWardrobe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.g = Game(self.root/'pet.sqlite3')
        self.g.run('s','u','领养')
    def test_eighteen_unique_costumes(self):
        self.assertEqual(len(COSTUMES)-1,18)
        self.assertEqual(len({v['name'] for v in COSTUMES.values()}),19)
    def test_three_pages_render_and_match_names(self):
        for page in range(1,4):
            text, pet, kind = self.g.run('s','u','衣柜',str(page))
            self.assertIn(f'第{page}/3页',text)
            self.assertEqual(pet['_wardrobe_page'],page)
            keys = list(COSTUMES)[1+(page-1)*6:1+page*6]
            for key in keys: self.assertIn(COSTUMES[key]['name'],text)
            output = render_wardrobe(self.root/f'page{page}.png',pet)
            with Image.open(output) as im:self.assertEqual(im.size,WARDROBE_SIZE)
    def test_bad_page_rejected(self):
        for value in ['0','4','abc','-1','1.5']:
            with self.subTest(value=value),self.assertRaises(GameError):
                self.g.run('s','u','衣柜',value)
    def test_first_new_costume_is_free(self):
        _,pet,_ = self.g.run('s','u','购买','芙兰')
        self.assertEqual(pet['coins'],40);self.assertEqual(pet['costume'],'flandre')
    def test_page_state_not_saved(self):
        self.g.run('s','u','衣柜','3')
        _,pet,_=self.g.run('s','u','看看')
        self.assertNotIn('_wardrobe_page',pet)
