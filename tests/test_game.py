import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import concurrent.futures
import json
import random
import sqlite3
import tempfile
import unittest
from pathlib import Path
from astrbot_plugin_maoyu.game import Game,GameError,COSTUMES,WALKS,level,clean_name

class Clock:
    def __init__(self): self.now=1792656000.0
    def __call__(self):return self.now
    def add(self,seconds):self.now+=seconds

class GameTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'pets.db';self.clock=Clock()
        self.g=Game(self.path,clock=self.clock,rng=random.Random(0))
        self.g.run('group-a','u1','领养','小白')
    def run_action(self,action='看看',arg='',scope='group-a',owner='u1'):
        return self.g.run(scope,owner,action,arg)
    def pet(self):return {k:v for k,v in self.run_action()[1].items() if not k.startswith('_display_')}
    def patch(self,**values):
        p=self.pet();p.update(values)
        with sqlite3.connect(self.path) as con:con.execute('UPDATE pets SET payload=? WHERE scope=? AND owner=?',(json.dumps(p),'group-a','u1'))
    def test_adopt_duplicate(self):
        with self.assertRaises(GameError):self.run_action('领养','另一个')
        self.assertEqual(self.pet()['name'],'小白')
    def test_no_pet(self):
        with self.assertRaises(GameError):self.run_action(owner='u2')
    def test_help_no_pet(self):self.assertIn('领养',self.run_action('帮助',owner='u2')[0])
    def test_names(self):
        for name in ('a'*13,'','a\nb','a\x00b','[CQ:at]','x\u202ey'):
            with self.subTest(name=name), self.assertRaises(GameError):clean_name(name)
        self.assertEqual(clean_name('　白团　'),'白团')
    def test_name_sql_safe(self):
        self.run_action('改名',"';DROP--");self.assertEqual(self.pet()['name'],"';DROP--")
    def test_group_isolation(self):
        self.run_action('领养','小黑',scope='group-b');self.assertEqual(self.pet()['name'],'小白')
        self.assertEqual(self.run_action(scope='group-b')[1]['name'],'小黑')
    def test_owner_isolation(self):
        self.run_action('领养','小黄',owner='u2');self.assertEqual(self.pet()['name'],'小白')
    def test_restart(self):
        self.run_action('购买','帕秋莉')
        g=Game(self.path,clock=self.clock);self.assertEqual(g.run('group-a','u1')[1]['costume'],'patchouli')
    def test_first_costume_gift(self):
        self.run_action('购买','诹访子');p=self.pet();self.assertFalse(p['gift']);self.assertEqual(p['coins'],40)
        self.assertEqual(p['costume'],'suwako')
    def test_duplicate_purchase_no_charge(self):
        self.run_action('购买','灵梦');p=self.pet()
        with self.assertRaises(GameError):self.run_action('购买','灵梦')
        self.assertEqual(self.pet(),p)
    def test_purchase_insufficient_atomic(self):
        self.run_action('购买','灵梦');p=self.pet()
        with self.assertRaises(GameError):self.run_action('购买','魔理沙')
        self.assertEqual(self.pet(),p)
    def test_paid_purchase(self):
        self.run_action('购买','灵梦');self.patch(coins=120)
        self.run_action('购买','蕾米');self.assertEqual(self.pet()['coins'],0)
    def test_cannot_equip_unowned(self):
        with self.assertRaises(GameError):self.run_action('换装','魔理沙')
    def test_take_off_and_alias(self):
        self.run_action('购买','帕琪');self.run_action('换装','原味');self.assertEqual(self.pet()['costume'],'plain')
    def test_unknown_costume(self):
        with self.assertRaises(GameError):self.run_action('购买','../x')
    def test_feed_free_and_cap(self):
        self.run_action('喂食');p=self.pet();self.assertEqual(p['food'],100);self.assertEqual(p['coins'],40)
    def test_feed_full(self):
        self.patch(food=100)
        with self.assertRaises(GameError):self.run_action('喂食')
    def test_feed_cooldown(self):
        self.patch(food=30);self.run_action('喂食')
        with self.assertRaises(GameError):self.run_action('喂食')
        self.clock.add(901);self.run_action('喂食')
    def test_pet_cooldown(self):
        self.run_action('摸摸')
        with self.assertRaises(GameError):self.run_action('摸摸')
        self.clock.add(601);self.run_action('摸摸');self.assertEqual(self.pet()['xp'],6)
    def test_play_costs(self):
        self.run_action('玩耍');p=self.pet();self.assertEqual(p['energy'],75);self.assertEqual(p['xp'],12)
    def test_low_energy_play(self):
        self.patch(energy=10)
        with self.assertRaises(GameError):self.run_action('玩耍')
    def test_low_food_walk(self):
        self.patch(food=20)
        with self.assertRaises(GameError):self.run_action('散步')
    def test_walk_rewards(self):
        self.run_action('散步');p=self.pet();self.assertEqual(p['visits'],1);self.assertEqual(len(p['souvenirs']),1);self.assertGreater(p['coins'],40)
    def test_walk_cooldown(self):
        self.run_action('散步')
        with self.assertRaises(GameError):self.run_action('散步')
    def test_collection_unique_diary_bound(self):
        for i in range(100):
            self.patch(energy=100,food=100);self.clock.add(3601);self.run_action('散步')
        p=self.pet();self.assertEqual(len(p['souvenirs']),12);self.assertLessEqual(len(p['diary']),5)
    def test_sleep_blocks_interactions(self):
        self.run_action('睡觉')
        for a in ('喂食','摸摸','玩耍','散步','睡觉'):
            with self.subTest(a=a),self.assertRaises(GameError):self.run_action(a)
    def test_sleep_recovery(self):
        self.patch(energy=0);self.run_action('睡觉');self.clock.add(3600)
        self.assertEqual(self.pet()['energy'],24);self.run_action('起床');self.assertEqual(self.pet()['sleep_until'],0)
    def test_sleep_auto_wake(self):
        self.patch(energy=0);self.run_action('睡觉');self.clock.add(4*3600);self.assertEqual(self.pet()['energy'],96);self.run_action('摸摸')
    def test_long_absence(self):
        self.clock.add(365*86400);p=self.pet();self.assertGreaterEqual(p['food'],15);self.assertGreaterEqual(p['mood'],20)
        self.assertEqual(p['name'],'小白');self.assertEqual(p['energy'],100)
    def test_local_daily_boundary(self):
        # 15:59:59 UTC == 23:59:59 Beijing
        self.clock.now=1792670400-1
        # derive boundary independently
        from datetime import datetime,timezone
        self.clock.now=datetime(2026,10,22,15,59,59,tzinfo=timezone.utc).timestamp()
        self.run_action('签到');self.clock.add(2);self.run_action('签到');self.assertEqual(self.pet()['coins'],120)
    def test_daily_duplicate(self):
        self.run_action('签到')
        with self.assertRaises(GameError):self.run_action('签到')
    def test_clock_rollback(self):
        self.run_action('签到');self.run_action('摸摸');p=self.pet();self.clock.add(-86400)
        with self.assertRaises(GameError):self.run_action('签到')
        with self.assertRaises(GameError):self.run_action('摸摸')
        self.assertEqual(p,self.pet())
    def test_invalid_action_atomic(self):
        p=self.pet()
        with self.assertRaises(GameError):self.run_action('不存在')
        self.assertEqual(self.pet(),p)
    def test_concurrent_daily_once(self):
        def claim(_):
            try:self.run_action('签到');return True
            except GameError:return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool: results=list(pool.map(claim,range(30)))
        self.assertEqual(sum(results),1);self.assertEqual(self.pet()['coins'],80)
    def test_concurrent_purchase_once(self):
        def buy(_):
            try:self.run_action('购买','灵梦');return True
            except GameError:return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:results=list(pool.map(buy,range(20)))
        self.assertEqual(sum(results),1);self.assertEqual(self.pet()['owned'],['plain','reimu'])
    def test_level_thresholds(self):
        self.assertEqual([level(x) for x in (0,49,50,199,200,450)],[1,1,2,2,3,4])
    def test_wardrobe_catalog(self):
        text,p,kind=self.run_action('衣柜');self.assertEqual(kind,'wardrobe');self.assertIn('灵梦',text)
    def test_all_costumes_obtainable(self):
        self.patch(coins=10000)
        for key in list(COSTUMES)[1:]:self.run_action('购买',key)
        self.assertEqual(len(self.pet()['owned']),len(COSTUMES))
    def test_database_integrity(self):
        with sqlite3.connect(self.path) as c:self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')

if __name__=='__main__':unittest.main()
