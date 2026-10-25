'use strict'
const { Schema, h } = require('koishi')
const fs = require('node:fs/promises')
const path = require('node:path')
const { Bridge } = require('./bridge.cjs')
exports.name = 'maoyu-courtyard'
exports.usage = '东方毛玉小院，18套装饰。需要 Node.js 18+、Python 3.10+ 和 Pillow；在 Koishi 所在环境安装 Python 依赖。发送「毛玉 帮助」。图片/GIF取决于消息适配器。'
exports.Config = Schema.object({
  python: Schema.string().default(process.platform === 'win32' ? 'python' : 'python3').description('Python可执行文件路径（不是shell命令）'),
  sendImages: Schema.boolean().default(true).description('发送像素卡和GIF'),
  cooldownScale: Schema.number().min(.1).max(10).default(1).description('互动冷却倍率'),
  utcOffset: Schema.number().min(-12).max(14).default(8).description('签到时区UTC偏移'),
  autoBackup: Schema.boolean().default(true).description('每日自动备份，保留7份'),
})
exports.apply = (ctx, config) => {
  const directory = path.resolve(ctx.baseDir || process.cwd(), 'data', 'maoyu-courtyard')
  const logger = ctx.logger('maoyu-courtyard')
  const bridge = new Bridge(config, directory, (text) => logger.warn(text))
  const recent = new Map()
  ctx.on('dispose', () => bridge.dispose())
  const handle = async (session, payload = '') => {
    if (!session || !session.userId || !session.platform || !session.selfId) return '平台没有提供完整用户/机器人标识，无法保存毛玉。'
    if (payload.length > 2048) return '指令太长，请发送「毛玉 帮助」。'
    const group = session.isDirect ? '' : (session.guildId || session.channelId)
    if (!session.isDirect && !group) return '平台没有提供群或频道标识，无法隔离存档。'
    const scope = JSON.stringify(['koishi', session.platform, session.selfId, group ? 'group' : 'private', group || session.userId])
    const key = JSON.stringify([scope, session.userId])
    const now = performance.now()
    if (recent.has(key) && now - recent.get(key) < 2000) return '慢一点呀，等两秒再来。'
    recent.delete(key); recent.set(key, now)
    while (recent.size > 4096) recent.delete(recent.keys().next().value)
    const match = payload.trim().match(/^(\S+)(?:\s+([\s\S]*))?$/)
    let result
    try {
      result = await bridge.request({ scope, owner: session.userId, action: match ? match[1] : '看看', arg: match?.[2] || '', messageId: session.messageId || null })
    } catch (error) { return h.text(error.message) }
    await session.send(h.text(result.text))
    if (!result.image) return
    if (!/^[a-f0-9]{32}\.(png|gif)$/.test(result.image)) return '图片文件名异常，操作结果以文字为准。'
    try {
      const bytes = await fs.readFile(path.join(directory, 'cards', result.image))
      return h.image(bytes, result.image.endsWith('.gif') ? 'image/gif' : 'image/png')
    } catch (error) {
      logger.warn(error)
      return '操作已保存，图片读取失败。可发送「毛玉 看看」。'
    }
  }
  ctx.command('毛玉 [payload:text]', '东方毛玉小院：领养和照顾像素毛玉').action(({ session }, payload) => handle(session, payload))
  ctx.command('养毛玉', '毛玉帮助菜单').action(({ session }) => handle(session, '帮助'))
}
