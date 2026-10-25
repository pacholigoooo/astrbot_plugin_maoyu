"""Regression specifications for 1.2.1. Added but NOT executed for this release."""
import asyncio
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from astrbot_plugin_maoyu.game import Game, GameError, presentation
from astrbot_plugin_maoyu.workers import BoundedWorkers, WorkBusy


class StorageHardening(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'save.sqlite3'
        self.now = 1800000000.0
        self.game = Game(self.path, clock=lambda: self.now)
        self.game.run('s', 'u', '领养')

    def payload(self):
        with sqlite3.connect(self.path) as db:
            return db.execute('SELECT payload FROM pets').fetchone()[0]

    def test_queries_do_not_write_decay(self):
        before = self.payload()
        self.now += 3600
        for action in ('看看', '衣柜', '图鉴', '日记', '成就'):
            self.game.run('s', 'u', action)
        self.assertEqual(before, self.payload())
        self.game.run('s', 'u', '摸摸')
        self.assertNotEqual(before, self.payload())
        self.assertNotIn('_display_', self.payload())

    def test_expired_receipt_without_other_writes(self):
        self.game.run('s', 'u', '签到', message_id='reused')
        self.now += 7 * 86400 + 1
        _, pet, _ = self.game.run('s', 'u', '签到', message_id='reused')
        self.assertEqual(pet['coins'], 120)

    def test_corrupt_relations_preserved(self):
        original = self.payload()
        for changes in (
            {'gift': 'false'}, {'owned': ['plain', 'plain']},
            {'owned': []}, {'costume': 'reimu'}, {'coins': 1.5},
            {'souvenirs': ['不存在']}, {'daily': '2026-99-99'},
            {'cooldowns': {'摸摸': True}}, {'achievements': ['first_walk', 'first_walk']},
        ):
            with self.subTest(changes=changes):
                pet = json.loads(original); pet.update(changes)
                raw = json.dumps(pet, ensure_ascii=False)
                with sqlite3.connect(self.path) as db:
                    db.execute('UPDATE pets SET payload=?', (raw,))
                with self.assertRaises(GameError):
                    self.game.run('s', 'u')
                self.assertEqual(raw, self.payload())

    def test_shared_view_uses_game_timezone(self):
        _, pet, _ = self.game.run('s', 'u')
        pet['energy'] = 10
        view = presentation(pet, self.now, self.game.tz)
        self.assertIn(view['state'], self.game.status(pet, self.now))
        self.assertEqual(view['care'], self.game.hint(pet, self.now))


class WorkerHardening(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_does_not_free_actual_capacity(self):
        workers = BoundedWorkers(1, 1, 'maoyu-regression')
        entered = threading.Event(); release = threading.Event()
        def blocked():
            entered.set()
            release.wait(5)
        task = asyncio.create_task(workers.run(blocked))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            with self.assertRaises(WorkBusy):
                await workers.run(lambda: None)
        finally:
            release.set()
            await workers.shutdown()

    async def test_closed_workers_reject_new_work(self):
        workers = BoundedWorkers(1, 1, 'maoyu-closed')
        await workers.shutdown()
        with self.assertRaises(WorkBusy):
            await workers.run(lambda: None)
