'use strict'
const { spawn } = require('node:child_process')
const { createInterface } = require('node:readline')
const path = require('node:path')

class Bridge {
  constructor(config, directory, log = () => {}) {
    this.config = config
    this.directory = directory
    this.log = log
    this.pending = new Map()
    this.sequence = 0
    this.closed = false
    this.ready = null
    this.child = null
  }
  start() {
    if (this.closed) return Promise.reject(new Error('小院已停止，请重载插件。'))
    if (this.ready) return this.ready
    this.ready = new Promise((resolve, reject) => {
      const child = this.child = spawn(this.config.python || 'python3',
        ['-u', path.join(__dirname, 'worker.py'), this.directory],
        { stdio: ['pipe', 'pipe', 'pipe'], shell: false, windowsHide: true })
      let settled = false
      const timer = setTimeout(() => this.fail(new Error('Python 启动超时，请检查运行环境。')), 30000)
      this.rejectStartup = reject
      this.startTimer = timer
      const lines = createInterface({ input: child.stdout })
      let stderr = ''
      child.stderr.on('data', (chunk) => { stderr = (stderr + chunk.toString()).slice(-8192) })
      lines.on('line', (line) => {
        try {
          const message = JSON.parse(line)
          if (message.ready === true && !settled) {
            settled = true; clearTimeout(timer); resolve(); return
          }
          const entry = this.pending.get(message.id)
          if (!entry) return
          this.pending.delete(message.id); clearTimeout(entry.timer)
          entry.resolve(message)
        } catch (error) { this.fail(new Error('Python 通信异常，请重载插件并查看日志。')) }
      })
      child.on('error', () => this.fail(new Error('无法启动 Python，请设置 python 路径并安装 Pillow。')))
      child.stdin.on('error', () => this.fail(new Error('Python 通道已关闭，请检查插件日志。')))
      child.on('exit', (code) => {
        if (stderr) this.log(stderr)
        if (!this.closed || this.pending.size) this.fail(new Error('Python 已退出；结果未确认，请重载后先查看状态。'))
        clearTimeout(timer)
        if (!settled) reject(new Error('Python 启动失败，请检查 Python 3.10+ 与 Pillow。'))
      })
      child.stdin.write(JSON.stringify(this.config) + '\n')
    })
    return this.ready
  }
  fail(error) {
    this.closed = true
    clearTimeout(this.startTimer)
    if (this.rejectStartup) this.rejectStartup(error)
    for (const entry of this.pending.values()) { clearTimeout(entry.timer); entry.reject(error) }
    this.pending.clear()
    if (this.child) this.child.kill()
  }
  async request(data) {
    // Admission is synchronous before awaiting startup, so bursts cannot bypass the cap.
    if (this.closed) throw new Error('小院已停止，请重载插件。')
    if (this.pending.size >= 32) throw new Error('小院请求较多，本条操作尚未执行，请稍后再试。')
    const id = ++this.sequence
    let entry
    const answer = new Promise((resolve, reject) => { entry = { resolve, reject, timer: null } })
    // Observe rejection immediately, including errors while startup is pending.
    answer.catch(() => {})
    this.pending.set(id, entry)
    try {
      await this.start()
      if (this.closed) throw new Error('小院正在停止，本条操作尚未发送。')
      entry.timer = setTimeout(() => this.fail(new Error('处理超时，结果未确认；请重载后先查看状态，不要重复购买。')), 120000)
      this.child.stdin.write(JSON.stringify({ ...data, id }) + '\n')
    } catch (error) {
      this.pending.delete(id); clearTimeout(entry.timer); entry.reject(error)
    }
    return answer
  }
  async dispose() {
    this.closed = true
    if (!this.child || this.child.exitCode !== null) return
    const child = this.child
    // EOF drains accepted work before exit; force termination only if shutdown stalls.
    await new Promise((resolve) => {
      const timer = setTimeout(() => { this.fail(new Error('小院关闭超时，未完成操作结果不确定。')); resolve() }, 30000)
      child.once('exit', () => { clearTimeout(timer); resolve() })
      child.stdin.end()
    })
  }
}
module.exports = { Bridge }
