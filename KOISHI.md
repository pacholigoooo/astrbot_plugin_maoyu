# Koishi 安装与更新

本仓库根目录同时是 AstrBot 插件和 npm 兼容插件目录，分别由 main.py 和 koishi/index.cjs 载入。

## 环境

- Koishi 4.18+、Node.js 18+。
- 同一运行环境/容器内有 Python 3.10+ 和 Pillow 10～12。
- 不需要安装 AstrBot，不调用大模型，不需要API Key。
- Docker宿主机装Python不等于容器内有Python；应在镜像构建时安装，不在插件运行时自动下载。

## 安装

在 Koishi 应用目录执行：

```
npm install git+https://github.com/pacholigoooo/astrbot_plugin_maoyu.git#main
python3 -m pip install -r node_modules/koishi-plugin-maoyu-courtyard/requirements.txt
```

Windows 可把 python3 换成 python。对于系统管理的Python，使用虚拟环境安装依赖，并将插件配置的 python 字段设置为该环境解释器的绝对路径；不要使用 --break-system-packages。

在 Koishi 控制台添加并启用 maoyu-courtyard。python 配置只能是可执行文件路径，不要填写带参数的shell命令。发送「毛玉 帮助」「毛玉 领养 糯米」。命令前缀由 Koishi 自己的设置决定。

## 更新

备份数据并停止实例，在应用目录重新执行：

```
npm install git+https://github.com/pacholigoooo/astrbot_plugin_maoyu.git#main
```

然后重启。锁文件会记录Git提交；如npm保持旧提交，可先卸载本插件包再重新安装同一地址，数据目录不在node_modules中。不要删除数据目录。

数据：应用目录/data/maoyu-courtyard/，包含SQLite、7份每日备份和图片缓存。按平台、机器人账号、群/私聊、用户隔离。不会与AstrBot存档自动合并。

## 边界

本版采用本机子进程复用Python核心，未实现纯JavaScript引擎，不适合不能运行Python子进程的浏览器版/沙箱版Koishi。

最多接收32个在途请求，单Python工作进程顺序执行，超出即提示未执行。请求超时/进程异常时不会自动重试扣币操作，会提示先检查状态；已接纳任务可能已经保存。禁用插件时等待已接纳工作结束，30秒仍不能结束才终止。

使用 Koishi 的图片消息元素发送PNG/GIF，实际上传能力仍取决于适配器。本版不承诺所有平台均支持GIF。

当前分发渠道为GitHub安装，不是npm注册表发布，也不声称可以在Koishi插件市场搜索到。
