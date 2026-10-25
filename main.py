"""AstrBot adapter: all gameplay and art stay offline."""
import asyncio
import json
import math
import threading
from collections import OrderedDict
import sqlite3
import time
import uuid
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.star.filter.command import GreedyStr
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from .game import Game, GameError
from .art import render_card, render_wardrobe
from .workers import BoundedWorkers, WorkBusy


class MaoyuPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.data_dir = Path(get_astrbot_data_path()) / 'plugin_data' / 'astrbot_plugin_maoyu'
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache = self.data_dir / 'cards'
        self.cache.mkdir(exist_ok=True)
        self.game = Game(self.data_dir / 'maoyu.sqlite3',
                         cooldown_scale=self._number('cooldown_scale', 1, .1, 10),
                         utc_offset=self._number('utc_offset', 8, -12, 14))
        self._db_workers = BoundedWorkers(1, 32, 'maoyu-db')
        self._image_workers = BoundedWorkers(2, 4, 'maoyu-image')
        self._closing = False
        self._last_request = OrderedDict()
        self._cleanup_lock = threading.Lock()
        self._last_cleanup = 0.0

    async def terminate(self):
        self._closing = True
        self._db_workers.close()
        self._image_workers.close()
        await asyncio.gather(self._db_workers.shutdown(), self._image_workers.shutdown())

    def _run_command(self, scope, owner, action, arg, message_id):
        result = self.game.run(scope, owner, action, arg, message_id)
        if result[1] is not None and self.config.get('auto_backup', True):
            try:
                self.game.backup(self.data_dir / 'backups')
            except Exception:
                logger.exception('Maoyu backup failed; committed save is intact')
        return result

    def _number(self, name, default, low, high):
        try:
            value=float(self.config.get(name,default))
            return max(low,min(high,value)) if math.isfinite(value) else default
        except (TypeError,ValueError):
            return default

    def _identity(self, event):
        platform = str(event.get_platform_id())
        group = str(event.get_group_id() or '')
        owner = str(event.get_sender_id() or '')
        if not owner:
            raise GameError('当前平台没有提供用户标识，暂时无法保存毛玉。')
        # JSON encoding prevents delimiter collisions and cross-account/group leaks.
        scope = json.dumps([platform, 'group' if group else 'private', group or owner],ensure_ascii=False)
        return scope, owner

    def _render(self, pet, kind):
        # Unique file per response avoids concurrent overwrite / wrong-user cards.
        now=time.time()
        if now-self._last_cleanup>3600 and self._cleanup_lock.acquire(blocking=False):
            try:
                self._last_cleanup=now
                files=[]
                for file in self.cache.iterdir():
                    try:
                        if file.suffix in ('.png','.gif'):
                            stamp=file.stat().st_mtime
                            if now-stamp>86400:file.unlink()
                            else:files.append((stamp,file))
                    except OSError:pass
                # Preserve all very recent files; a platform may still be uploading them.
                for stamp,file in sorted(files)[:-512]:
                    if now-stamp>600:
                        try:file.unlink()
                        except OSError:pass
            finally:self._cleanup_lock.release()
        path=self.cache/(uuid.uuid4().hex+('.gif' if kind=='gif' else '.png'))
        if kind=='wardrobe':
            return render_wardrobe(path,pet)
        return render_card(pet,path,now,animated=kind=='gif')

    @filter.command('毛玉')
    async def maoyu(self,event: AstrMessageEvent,payload: GreedyStr):
        """领养与照顾像素毛玉。发送 /毛玉 帮助 查看全部指令。"""
        parts=str(payload).strip().split(maxsplit=1)
        action=parts[0] if parts else '看看'
        arg=parts[1] if len(parts)>1 else ''
        async for result in self._handle(event,action,arg):
            yield result

    @filter.command('养毛玉')
    async def welcome(self,event: AstrMessageEvent):
        """打开养毛玉帮助。"""
        async for result in self._handle(event,'帮助',''):
            yield result

    async def _handle(self,event,action,arg):
        event.stop_event()  # Commands must not also trigger the LLM.
        if self._closing:
            yield event.plain_result('毛玉小院正在重载，请稍后再试。')
            return
        try:
            scope, owner = self._identity(event)
            key=(scope,owner);now=time.monotonic()
            last=self._last_request.get(key)
            if last is not None and now-last<2:
                yield event.plain_result('慢一点呀，等两秒再来。')
                return
            self._last_request[key]=now
            self._last_request.move_to_end(key)
            while len(self._last_request)>4096:
                self._last_request.popitem(last=False)
            gif=action=='动图'
            message_id=getattr(getattr(event,'message_obj',None),'message_id',None)
            message_id=str(message_id) if message_id not in (None,'') else None
            text, pet, kind = await self._db_workers.run(
                self._run_command, scope, owner, '看看' if gif else action, arg, message_id)
            if gif:
                kind = 'gif'
        except WorkBusy:
            yield event.plain_result('小院请求较多或正在重载，本条操作尚未执行，请稍后再试。')
            return
        except GameError as exc:
            yield event.plain_result(str(exc));return
        except (sqlite3.Error,ValueError,KeyError,TypeError):
            logger.exception('Maoyu storage operation failed')
            yield event.plain_result('毛玉存档暂时读取失败，请联系管理员查看日志；不要删除数据库。');return
        # Game commit precedes rendering. Never repeat a purchase after image failure.
        yield event.plain_result(text)
        if pet is not None and kind!='text' and self.config.get('send_images',True):
            try:
                path = await self._image_workers.run(self._render, pet, kind)
                yield event.image_result(str(path))
            except WorkBusy:
                yield event.plain_result('图片排队较多或正在重载，本次先显示文字，操作已保存。')
            except Exception:
                logger.exception('Maoyu card render failed; game operation already committed')
                yield event.plain_result('本次操作已保存，图片暂时生成失败。可用 /毛玉 看看 查看文字状态。')
