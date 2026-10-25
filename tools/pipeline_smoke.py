"""Run with AstrBot installed; isolates all runtime data in a temporary folder.
Real loader, command parser, ProcessStage, StarRequestSubStage, Scheduler and RespondStage. Only final platform transport is recorded, not network-sent.
"""
import asyncio
import json
import inspect
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

async def main():
    source=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='maoyu-framework-') as root:
        os.environ['ASTRBOT_ROOT']=root
        os.chdir(root)
        sys.path.insert(0,root)
        target=Path(root)/'data'/'plugins'/source.name
        remote = '--remote' in sys.argv
        if not remote:
            shutil.copytree(source,target,ignore=shutil.ignore_patterns('__pycache__','*.pyc','node_modules','dist','.git','*.tgz'))
        (Path(root)/'data'/'config').mkdir(parents=True,exist_ok=True)
        from astrbot.core import db_helper,sp,astrbot_config
        from astrbot.api.star import Context
        from astrbot.core.star.star_manager import PluginManager as StarManager
        from astrbot.core.star.star import star_registry
        from astrbot.core.star.star_handler import star_handlers_registry
        from astrbot.core.star.filter.command import CommandFilter
        from astrbot.core.platform import AstrBotMessage,PlatformMetadata,MessageMember,MessageType
        from astrbot.api.event import AstrMessageEvent
        if hasattr(db_helper,'initialize'):
            await db_helper.initialize()
        kwargs={k:None for k in inspect.signature(Context).parameters}
        kwargs.update(event_queue=asyncio.Queue(),config=astrbot_config,db=db_helper)
        context=Context(**kwargs)
        manager=StarManager(context,astrbot_config)
        if remote:
            # Honor an explicitly configured trusted CA bundle; never disable TLS verification.
            if os.environ.get('SSL_CERT_FILE'):
                import ssl
                manager._updater = type(manager._updater)(verify=ssl.create_default_context(cafile=os.environ['SSL_CERT_FILE']))
            await manager._updater.install('https://github.com/pacholigoooo/astrbot_plugin_maoyu')
        ok,error=await manager.load(specified_dir_name=source.name)
        assert ok,error
        meta=next(s for s in star_registry if s.name=='astrbot_plugin_maoyu')
        plugin=meta.star_cls
        assert plugin is not None
        handlers=star_handlers_registry.get_handlers_by_module_name(meta.module_path)
        from types import SimpleNamespace
        from astrbot.core.pipeline.scheduler import PipelineScheduler
        from astrbot.core.pipeline.process_stage.stage import ProcessStage
        from astrbot.core.pipeline.process_stage.method.star_request import StarRequestSubStage
        from astrbot.core.pipeline.respond.stage import RespondStage
        pipeline_context = SimpleNamespace(astrbot_config=astrbot_config, plugin_manager=manager)
        process = ProcessStage()
        process.ctx = pipeline_context
        process.star_request_sub_stage = StarRequestSubStage()
        await process.star_request_sub_stage.initialize(pipeline_context)
        class NoLLM:
            async def process(self, event):
                raise AssertionError('A pet command must not invoke the default LLM')
                yield
        process.agent_sub_stage = NoLLM()
        respond = RespondStage()
        await respond.initialize(pipeline_context)
        scheduler = PipelineScheduler(pipeline_context)
        scheduler.stages = [process, respond]
        class RecordingEvent(AstrMessageEvent):
            async def send(self, message):
                self.delivered.append(message)
                self._has_send_oper = True
        def event_for(text,message_id=None):
            message=AstrBotMessage();message.type=MessageType.GROUP_MESSAGE
            message.self_id='test-bot';message.group_id='test-group';message.session_id='test-group'
            message.message_id=message_id or uuid.uuid4().hex
            message.sender=MessageMember('test-user','Tester');message.message=[]
            message.message_str=text;message.raw_message={}
            event=RecordingEvent(text,message,PlatformMetadata('test','offline smoke','test-instance'),'test-group')
            event.delivered=[]
            event.is_at_or_wake_command=True
            return event
        async def invoke(text,message_id=None):
            event=event_for(text,message_id);plugin._last_request.clear()
            for handler in handlers:
                commands=[f for f in handler.event_filters if isinstance(f,CommandFilter)]
                if commands and commands[0].filter(event,astrbot_config):
                    event.set_extra('activated_handlers',[handler])
                    event.set_extra('handlers_parsed_params',{handler.handler_full_name:event.get_extra('parsed_params')})
                    await scheduler._process_stages(event)
                    results=event.delivered
                    assert results,text
                    for r in results:
                        assert r.chain is not None
                        for component in r.chain:
                            file=getattr(component,'file',None)
                            if isinstance(file,str) and file.startswith('file://'):
                                from urllib.parse import unquote,urlparse
                                assert Path(unquote(urlparse(file).path)).is_file(),file
                    return results
            raise AssertionError('No matching real command filter: '+text)
        steps=['毛玉 帮助','毛玉 领养 糯米','毛玉','毛玉 改名 White Ball','毛玉 改名 糯米','毛玉 衣柜','毛玉 购买 帕秋莉','毛玉 看看',
               '毛玉 喂食','毛玉 摸摸','毛玉 玩耍','毛玉 散步','毛玉 签到',
               '毛玉 日记','毛玉 成就','毛玉 图鉴','毛玉 动图','毛玉 睡觉','毛玉 起床','养毛玉']
        for text in steps:
            results=await invoke(text)
            content=''.join(getattr(c,'text','') for r in results for c in r.chain)
            expected={'帮助':'养毛玉','领养':'领养成功','衣柜':'毛玉衣柜','购买':'已获得',
                      '看看':'Lv.','喂食':'米糕','摸摸':'呼噜','玩耍':'线球','散步':'散步 ·',
                      '签到':'点心钱 +40','日记':'毛玉手记','成就':'成长册','图鉴':'散步收藏',
                      '动图':'Lv.','睡觉':'睡成了一团','起床':'懒腰','改名':'以后就叫'}
            verb=text.split()[1] if len(text.split())>1 else ('帮助' if text=='养毛玉' else '看看')
            assert expected[verb] in content,(text,content)
            if verb not in ('帮助','日记','成就','图鉴'):
                from astrbot.core.message.components import Image
                assert any(isinstance(c,Image) for r in results for c in r.chain), ('MISSING_IMAGE_IN_REAL_PIPELINE',text,content)
            if 'White Ball' in text:assert 'White Ball' in content
            print('PASS',text,'components',sum(len(r.chain) for r in results))
        # A replay of the same source message remains idempotent even across a new plugin instance.
        message_id='duplicate-change-name'
        await invoke('毛玉 改名 白团',message_id)
        results=await invoke('毛玉 改名 白团',message_id)
        assert '已经处理过' in str(results)
        assert (plugin.data_dir/'backups').is_dir()
        if remote:
            saved = plugin.game.run(*plugin._identity(event_for('毛玉 看看')))[1]
            await manager.update_plugin('astrbot_plugin_maoyu')
            meta = next(s for s in star_registry if s.name == 'astrbot_plugin_maoyu')
            plugin = meta.star_cls
            handlers = star_handlers_registry.get_handlers_by_module_name(meta.module_path)
            results = await invoke('毛玉 看看')
            loaded = plugin.game.run(*plugin._identity(event_for('毛玉 看看')))[1]
            assert loaded['name'] == saved['name']
            assert loaded['coins'] == saved['coins']
            assert loaded['owned'] == saved['owned']
            print('REMOTE_INSTALL_UPDATE_OK: downloaded, reloaded, save preserved')
        print('REAL_PIPELINE_SMOKE_OK',len(steps),'commands; replay idempotence; backups')
        await plugin.terminate()
        if hasattr(sp,'close'):await sp.close()
        if hasattr(db_helper,'engine'):await db_helper.engine.dispose()

if __name__=='__main__':asyncio.run(main())
