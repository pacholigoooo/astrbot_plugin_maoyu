import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import concurrent.futures
import json
import random
import sqlite3
import tempfile
import unittest
from astrbot_plugin_maoyu.game import Game,GameError,ACHIEVEMENTS

class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name);self.path=self.root/'save.sqlite3';self.now=1800000000.
        self.g=Game(self.path,clock=lambda:self.now,rng=random.Random(7));self.g.run('s','u','领养')
    def run_cmd(self,a='看看',arg='',mid=None):return self.g.run('s','u',a,arg,mid)
    def pet(self):return {k:v for k,v in self.run_cmd()[1].items() if not k.startswith('_display_')}
    def patch(self,**changes):
        p=self.pet();p.update(changes)
        with sqlite3.connect(self.path) as con:con.execute('UPDATE pets SET payload=?',(json.dumps(p),))
    def test_first_walk_achievement_once(self):
        text,p,_=self.run_cmd('散步');self.assertIn('初次出门',text);self.assertIn('first_walk',p['achievements'])
        before=p['coins'];self.now+=3601;_,p,_=self.run_cmd('散步');self.assertLessEqual(p['coins']-before,24)
    def test_wardrobe_achievement(self):
        self.patch(coins=1000)
        for key in ('灵梦','魔理沙','琪露诺'):text,p,_=self.run_cmd('购买',key)
        self.assertIn('wardrobe',p['achievements']);self.assertIn('换装爱好者',text)
    def test_read_only_never_rewards(self):
        self.patch(xp=800);before=self.pet()['coins'];self.run_cmd('成就');self.assertEqual(before,self.pet()['coins'])
    def test_level_milestone(self):
        self.patch(xp=800);text,p,_=self.run_cmd('摸摸');self.assertIn('熟悉的掌心',text);self.assertIn('companion',p['achievements'])
    def test_diary(self):self.assertIn('今天起',self.run_cmd('日记')[0])
    def test_achievement_list(self):self.assertEqual(len(ACHIEVEMENTS),6);self.assertIn('成长册',self.run_cmd('成就')[0])
    def test_hint_smart(self):
        self.assertIn('首套',self.run_cmd()[0]);self.run_cmd('购买','灵梦');self.patch(food=20);self.assertIn('点心',self.run_cmd()[0])
    def test_receipt_duplicate_after_restart(self):
        self.run_cmd('签到',mid='abc');self.now+=86400
        self.g=Game(self.path,clock=lambda:self.now)
        text,p,_=self.run_cmd('签到',mid='abc');self.assertIsNone(p);self.assertIn('已经处理',text);self.assertEqual(self.pet()['coins'],80)
    def test_receipt_failed_command_not_consumed(self):
        with self.assertRaises(GameError):self.run_cmd('换装','灵梦',mid='x')
        self.run_cmd('购买','灵梦');self.run_cmd('换装','灵梦',mid='x')
    def test_receipt_scope_isolation(self):
        self.run_cmd('签到',mid='x');self.g.run('other','u','领养');self.g.run('other','u','签到',message_id='x')
    def test_receipt_same_read_repeats(self):
        for _ in range(3):self.assertIsNotNone(self.run_cmd(mid='r')[1])
    def test_receipt_concurrency(self):
        def call(_):return self.run_cmd('购买','灵梦',mid='buy')[1] is not None
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:out=list(pool.map(call,range(20)))
        self.assertEqual(sum(out),1)
    def test_backup_valid_and_once(self):
        path=self.g.backup(self.root/'backups');stamp=path.stat().st_mtime_ns
        self.g.backup(self.root/'backups');self.assertEqual(stamp,path.stat().st_mtime_ns)
        with sqlite3.connect(path) as c:self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok');self.assertEqual(c.execute('SELECT COUNT(*) FROM pets').fetchone()[0],1)
    def test_backup_retention(self):
        for _ in range(12):self.g.backup(self.root/'backups');self.now+=86400
        self.assertEqual(len(list((self.root/'backups').glob('*.sqlite3'))),7)
    def test_backup_concurrent(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(lambda _:self.g.backup(self.root/'backups'),range(10)))
        self.assertEqual(len(list((self.root/'backups').glob('*.sqlite3'))),1);self.assertFalse(list((self.root/'backups').glob('*.pending')))
    def test_upgrade_v1_save_no_retroactive_currency(self):
        p=self.pet();p.pop('achievements');p['visits']=15;p['xp']=900
        with sqlite3.connect(self.path) as c:c.execute('UPDATE pets SET payload=?',(json.dumps(p),));c.execute('PRAGMA user_version=1')
        self.g=Game(self.path,clock=lambda:self.now)
        new=self.pet();self.assertEqual(new['coins'],p['coins']);self.assertIn('first_walk',new['achievements']);self.assertIn('companion',new['achievements'])
        before=self.path.with_name('save.pre-v1.1.sqlite3');self.assertTrue(before.exists())
        with sqlite3.connect(before) as c:self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],1)
    def test_future_schema_rejected(self):
        with sqlite3.connect(self.path) as c:c.execute('PRAGMA user_version=99')
        with self.assertRaises(RuntimeError):Game(self.path)
    def test_corrupt_save_preserved(self):
        with sqlite3.connect(self.path) as c:c.execute('UPDATE pets SET payload=?',('{bad json',))
        with self.assertRaises(ValueError):self.run_cmd()
        with sqlite3.connect(self.path) as c:self.assertEqual(c.execute('SELECT payload FROM pets').fetchone()[0],'{bad json')
    def test_invalid_numbers_preserved(self):
        self.patch(food=-5)
        with self.assertRaises(GameError):self.run_cmd()
    def test_unknown_costume_preserved(self):
        self.patch(costume='../../test')
        with self.assertRaises(GameError):self.run_cmd()
    def test_missing_fields_preserved(self):
        with sqlite3.connect(self.path) as c:c.execute('UPDATE pets SET payload=?',('{}',))
        with self.assertRaises(GameError):self.run_cmd()
    def test_random_play_invariants(self):
        rng=random.Random(55)
        for i in range(1200):
            self.now+=rng.randrange(1,10000)
            try:self.run_cmd(rng.choice(['喂食','摸摸','玩耍','散步','签到','睡觉','起床','衣柜','看看','图鉴']))
            except GameError:pass
            p=self.pet()
            for key in ('food','mood','energy'):self.assertGreaterEqual(p[key],0);self.assertLessEqual(p[key],100)
            self.assertGreaterEqual(p['coins'],0);self.assertEqual(len(set(p['owned'])),len(p['owned']));self.assertLessEqual(len(p['diary']),5)
