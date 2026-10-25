'use strict'
const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const path = require('node:path')
const os = require('node:os')
const { Bridge } = require('./bridge.cjs')
async function fixture(t, sendImages = false) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'maoyu-koishi-'))
  const bridge = new Bridge({ python: process.env.MAOYU_PYTHON || 'python3', sendImages, autoBackup: true }, dir)
  t.after(async () => { await bridge.dispose(); await fs.rm(dir, { recursive: true, force: true }) })
  const call = (action, arg = '', extra = {}) => bridge.request({ scope: 's', owner: 'u', action, arg, ...extra })
  return { bridge, call, dir }
}
test('shared Python core: every command and restart persistence', async (t) => {
  const { call, bridge, dir } = await fixture(t)
  for (const [action, arg, expected] of [
    ['帮助', '', '领养'], ['领养', 'White Ball', '领养成功'], ['看看', '', 'White Ball'],
    ['改名', '糯米', '以后就叫'], ['衣柜', '', '毛玉衣柜'], ['购买', '帕琪', '首次赠礼'],
    ['换装', '原味', '穿好了'], ['喂食', '', '米糕'], ['摸摸', '', '呼噜'],
    ['玩耍', '', '线球'], ['散步', '', '新收藏'], ['签到', '', '+40'],
    ['日记', '', '毛玉手记'], ['图鉴', '', '散步收藏'], ['成就', '', '成长册'],
    ['睡觉', '', '睡成'], ['起床', '', '懒腰'], ['动图', '', 'Lv.'],
  ]) assert.ok((await call(action, arg)).text.includes(expected), action)
  await bridge.dispose()
  const next = new Bridge({ sendImages: false, python: process.env.MAOYU_PYTHON || 'python3' }, dir)
  try { assert.match((await next.request({ scope: 's', owner: 'u', action: '看看' })).text, /糯米/) }
  finally { await next.dispose() }
})
test('PNG, wardrobe and GIF rendered via shared assets', async (t) => {
  const { call, dir } = await fixture(t, true)
  for (const action of ['领养', '衣柜', '动图']) {
    const result = await call(action)
    assert.match(result.image, /^[a-f0-9]{32}\.(png|gif)$/)
    const bytes = await fs.readFile(path.join(dir, 'cards', result.image))
    assert.equal(bytes.subarray(action === '动图' ? 0 : 1, action === '动图' ? 3 : 4).toString(), action === '动图' ? 'GIF' : 'PNG')
  }
})
test('idempotence and cross-user/scope isolation', async (t) => {
  const { call } = await fixture(t)
  await call('领养')
  assert.match((await call('购买', '灵梦', { messageId: 'm1' })).text, /已获得/)
  assert.match((await call('购买', '灵梦', { messageId: 'm1' })).text, /已经处理过/)
  assert.match((await call('看看', '', { owner: 'other' })).text, /先领养/)
  assert.match((await call('看看', '', { scope: 'other' })).text, /先领养/)
})
test('burst admission rejects the 33rd request, including during startup', async (t) => {
  const { bridge, call } = await fixture(t)
  const pending = Array.from({ length: 32 }, () => call('帮助'))
  await assert.rejects(call('帮助'), /尚未执行/)
  assert.equal((await Promise.all(pending)).length, 32)
  assert.equal(bridge.pending.size, 0)
})
test('missing Python produces actionable error without hanging', async (t) => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'maoyu-no-python-'))
  const bridge = new Bridge({ python: path.join(dir, 'missing-python') }, dir)
  t.after(async () => { await bridge.dispose(); await fs.rm(dir, { recursive: true, force: true }) })
  await assert.rejects(bridge.request({ scope: 's', owner: 'u', action: '帮助' }), /Python/)
})
test('real Koishi registration, parsing, config and message output', async (t) => {
  const { Context } = require('koishi')
  const plugin = require('./index.cjs')
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'maoyu-koishi-app-'))
  const app = new Context(); app.baseDir = dir
  const config = plugin.Config({ python: process.env.MAOYU_PYTHON || 'python3' })
  const fork = app.plugin(plugin, config)
  t.after(async () => { await fork.dispose(); await app.stop(); await fs.rm(dir, { recursive: true, force: true }) })
  await app.start()
  const cmd = app.$commander.get('毛玉')
  assert.ok(cmd); assert.ok(app.$commander.get('养毛玉'))
  const sent = []
  const session = { app, userId: 'test-user', selfId: 'test-bot', platform: 'test', guildId: 'test-group', channelId: 'test-group', isDirect: false,
    messageId: 'adopt', send: async (msg) => { sent.push(String(msg)); return ['test-message'] } }
  const argv = cmd.parse('领养 糯米'); argv.session = session
  const result = await cmd._actions[0](argv, ...argv.args)
  assert.ok(sent.some(x => x.includes('领养成功')))
  assert.match(String(result), /<img/); assert.match(String(result), /data:image\/png;base64/)
  assert.match(String(await cmd._actions[0](argv, ...argv.args)), /两秒/)
})
