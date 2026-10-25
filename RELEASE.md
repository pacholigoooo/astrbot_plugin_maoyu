# 公开发布清单

这个目录可作为 GitHub 仓库根目录。建议仓库名为 `astrbot_plugin_maoyu`。

本次1.4.0已按用户新授权运行测试，详见 TEST_REPORT.md。

## 发布前与后续维护

仓库已设为 https://github.com/pacholigoooo/astrbot_plugin_maoyu ，metadata.yaml 的 repo 与之对应。

- 运行 Python 单元测试、Koishi 测试和真实框架冒烟脚本；详细命令见 README 与 TEST_REPORT。
- `python tools/framework_smoke.py --remote` 在临时目录验证GitHub下载、更新和存档保留（适用AstrBot 4.29.1）。
- `python tools/build_release.py` 生成白名单ZIP；`npm pack` 生成Koishi包。提交仅包含白名单文件，不包括node_modules、凭据或数据。
- 发布新版本时同步修改 version.py、metadata.yaml 与 package.json，更新锁文件与CHANGELOG，然后重新验证。
- GitHub远程安装不等于官方市场上架；本次未提交AstrBot市场审核或发布npm注册表。

## 分发方式

- GitHub Release：把生成的 ZIP 与 SHA256 文件附到 v1.4.0 Release。
- AstrBot 插件市场：先有公开 GitHub 仓库，再到官方发布入口提交。工具不会替你发布或创建账号。
- 已附 GitHub Actions CI，但尚未在你的GitHub仓库上运行；上传后才会触发。工作流只申请 contents:read 权限。

官方说明：https://docs.astrbot.app/dev/star/plugin-publish.html
官方发布入口：https://cloud.astrbot.app/

官方文档规定插件ZIP不超过16MB。构建脚本使用更保守的十进制上限，不依赖人工放行。

## 发布介绍建议

毛玉小院：一个离线、轻量的 AstrBot 东方同人宠物插件。领养一只毛玉，喂食、摸摸、散步、收集纪念品，换上六套东方主题外观。首套装饰免费，长期离线不会死亡，不接大模型，不需要API Key。支持独立群存档、成长成就、消息去重和本地自动备份。

素材说明：角色与小院背景由AI图像生成；代码仅负责游戏逻辑与UI排版。所有东方事件为同人原创。
