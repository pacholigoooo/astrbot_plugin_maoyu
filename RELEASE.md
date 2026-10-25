# 公开发布清单

这个目录可作为 GitHub 仓库根目录。建议仓库名为 `astrbot_plugin_maoyu`。

本次1.2.1按用户要求仅进行静态检查与打包，下列测试/联调步骤为今后经授权的发布验收建议，本次没有执行。

## 发布之前

1. 在 metadata.yaml 将 author 改成你希望公开署名的昵称；当前 pachi 是制作时的署名，不是真实姓名。
2. 创建你自己的仓库后，添加 `repo: 你的真实GitHub仓库URL`。本包未虚构地址。源码ZIP本地安装不依赖此字段，但市场提交应填写真实地址。
3. 保留 LICENSE、字体许可和同人/AI生成素材说明。根据实际用途核对东方Project二次创作规则；不将插件宣传为官方作品。
4. 在自己的实际聊天适配器上走一遍领养、购买、散步、睡觉、重启、图片和GIF发送。框架离线验证不等于QQ账号联调。
5. 运行 `python -m unittest discover -s tests -v`。
6. 可在装有 AstrBot 的独立测试环境运行 `python tools/framework_smoke.py`，不需要登录聊天账号。脚本创建临时数据目录，用真实加载器和真实消息对象测试；不启动WebUI或对外监听端口。
7. 运行 `python tools/build_release.py`，生成 dist/ 下的安装包及SHA256文件；脚本自动阻止超过16,000,000字节的包。
8. GitHub上传目录内容，不要把外层文件夹再套到仓库里。不要上传 dist、真实数据库、缓存或机器人配置。

## 分发方式

- GitHub Release：把生成的 ZIP 与 SHA256 文件附到 v1.2.1 Release。
- AstrBot 插件市场：先有公开 GitHub 仓库，再到官方发布入口提交。工具不会替你发布或创建账号。
- 已附 GitHub Actions CI，但尚未在你的GitHub仓库上运行；上传后才会触发。工作流只申请 contents:read 权限。

官方说明：https://docs.astrbot.app/dev/star/plugin-publish.html
官方发布入口：https://cloud.astrbot.app/

官方文档规定插件ZIP不超过16MB。构建脚本使用更保守的十进制上限，不依赖人工放行。

## 发布介绍建议

毛玉小院：一个离线、轻量的 AstrBot 东方同人宠物插件。领养一只毛玉，喂食、摸摸、散步、收集纪念品，换上六套东方主题外观。首套装饰免费，长期离线不会死亡，不接大模型，不需要API Key。支持独立群存档、成长成就、消息去重和本地自动备份。

素材说明：角色与小院背景由AI图像生成；代码仅负责游戏逻辑与UI排版。所有东方事件为同人原创。
