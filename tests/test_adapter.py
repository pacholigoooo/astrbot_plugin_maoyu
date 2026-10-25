import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
"""Framework API-contract tests with stubs, not live QQ integration."""
import asyncio
import importlib
import logging
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock

class Event:
    def __init__(self,owner='1',group='a',platform='bot-a'):
        self.owner=owner;self.group=group;self.platform=platform;self.stopped=False
    def get_platform_id(self):return self.platform
    def get_group_id(self):return self.group
    def get_sender_id(self):return self.owner
    def stop_event(self):self.stopped=True
    def plain_result(self,text):return ('text',text)
    def image_result(self,path):return ('image',path)

class AdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.modules={}
        names=['astrbot','astrbot.api','astrbot.api.event','astrbot.api.star','astrbot.core','astrbot.core.star','astrbot.core.star.filter','astrbot.core.star.filter.command','astrbot.core.utils','astrbot.core.utils.astrbot_path']
        for name in names:self.modules[name]=types.ModuleType(name)
        self.modules['astrbot.core.star.filter.command'].GreedyStr=str
        self.modules['astrbot.api'].AstrBotConfig=dict
        self.modules['astrbot.api'].logger=logging.getLogger('maoyu-test')
        self.modules['astrbot.api.event'].AstrMessageEvent=Event
        self.modules['astrbot.api.event'].filter=types.SimpleNamespace(command=lambda name:lambda fn:fn)
        class Star:
            def __init__(self,context):self.context=context
        self.modules['astrbot.api.star'].Star=Star
        self.modules['astrbot.api.star'].Context=object
        self.modules['astrbot.core.utils.astrbot_path'].get_astrbot_data_path=lambda:self.tmp.name
        self.mock=patch.dict(sys.modules,self.modules);self.mock.start();self.addCleanup(self.mock.stop)
        sys.modules.pop('astrbot_plugin_maoyu.main',None)
        self.mod=importlib.import_module('astrbot_plugin_maoyu.main')
        self.plugin=self.mod.MaoyuPlugin(object(),{'send_images':False})
        self.addAsyncCleanup(self.plugin.terminate)
    async def call(self,action='看看',arg='',event=None):
        event=event or Event();self.plugin._last_request.clear()
        return [x async for x in self.plugin.maoyu(event,action+' '+arg)]
    async def test_help(self):self.assertIn('领养',(await self.call('帮助'))[0][1])
    async def test_default_no_adoption(self):self.assertIn('先领养',(await self.call())[0][1])
    async def test_adopt_and_restart(self):
        await self.call('领养','白白');await self.plugin.terminate();self.plugin=self.mod.MaoyuPlugin(object(),{'send_images':False});self.addAsyncCleanup(self.plugin.terminate)
        self.assertIn('白白',(await self.call())[0][1])
    async def test_stops_llm(self):
        e=Event();await self.call('帮助',event=e);self.assertTrue(e.stopped)
    async def test_identity_separates_bots_groups_and_users(self):
        ids=[self.plugin._identity(e) for e in [Event(),Event(platform='bot-b'),Event(group='b'),Event(owner='2'),Event(group='')]]
        self.assertEqual(len(set(ids)),5)
    async def test_no_sender(self):self.assertIn('用户标识',(await self.call(event=Event(owner='')))[0][1])
    async def test_spam_throttle(self):
        await self.call('帮助');out=[x async for x in self.plugin.maoyu(Event(),'帮助')]
        self.assertIn('两秒',out[0][1])
    async def test_image_render_and_unique_cache(self):
        self.plugin.config['send_images']=True
        a=await self.call('领养','糯米');b=await self.call()
        self.assertEqual(a[1][0],'image');self.assertTrue(Path(a[1][1]).is_file());self.assertNotEqual(a[1][1],b[1][1])
    async def test_image_failure_does_not_repeat_reward(self):
        await self.call('领养');self.plugin.config['send_images']=True
        with patch.object(self.plugin,'_render',side_effect=OSError('simulated')),self.assertLogs('maoyu-test',level='ERROR'):
            out=await self.call('签到')
        self.assertIn('已保存',out[-1][1])
        scope,owner=self.plugin._identity(Event())
        self.assertEqual(self.plugin.game.run(scope,owner)[1]['coins'],80)
    async def test_gif(self):
        await self.call('领养');self.plugin.config['send_images']=True
        out=await self.call('动图');self.assertTrue(out[-1][1].endswith('.gif'))
    async def test_storage_error_friendly(self):
        with patch.object(self.plugin.game,'run',side_effect=self.mod.sqlite3.OperationalError('locked')),self.assertLogs('maoyu-test',level='ERROR'):
            out=await self.call()
        self.assertIn('不要删除数据库',out[0][1])
    async def test_wardrobe(self):
        await self.call('领养');self.plugin.config['send_images']=True
        out=await self.call('衣柜');self.assertEqual(out[-1][0],'image')

    async def test_multiword_name(self):
        out=await self.call('领养','White Ball')
        self.assertIn('White Ball',out[0][1])
    async def test_no_silent_purchase_extra_args(self):
        await self.call('领养');out=await self.call('购买','灵梦 100')
        self.assertIn('没有这套',out[0][1])
        scope,owner=self.plugin._identity(Event());self.assertTrue(self.plugin.game.run(scope,owner)[1]['gift'])
    async def test_backup_failure_keeps_success(self):
        with patch.object(self.plugin.game,'backup',side_effect=OSError('full')),self.assertLogs('maoyu-test',level='ERROR'):
            out=await self.call('领养')
        self.assertIn('领养成功',out[0][1])
    async def test_busy_render_falls_back(self):
        self.plugin.config['send_images']=True
        with patch.object(self.plugin._image_workers, 'run', new=AsyncMock(side_effect=self.mod.WorkBusy())):
            out=await self.call('领养')
        self.assertIn('操作已保存',out[-1][1])
    async def test_bad_numeric_config_defaults(self):
        self.plugin.config['cooldown_scale']='not numeric';self.assertEqual(self.plugin._number('cooldown_scale',1,.1,10),1)
        self.plugin.config['cooldown_scale']=float('nan');self.assertEqual(self.plugin._number('cooldown_scale',1,.1,10),1)
