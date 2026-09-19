# local.potplayer

在影片详情页选择此播放源时, 网页内播放器仍可取流; 点「用 PotPlayer 打开」才用本机
[PotPlayer](https://potplayer.daum.net/) 打开已入库视频.

## 适用条件

- Amane 与 PotPlayer 运行在**同一台 Windows 本机** (桌面应用或本机直接运行的服务)
- 条目已关联本地媒体文件

远程 Docker / NAS 上的 Amane 进程无法拉起你电脑上的 PotPlayer.

## 安装

1. 将本目录打成 zip (根目录或单一顶层文件夹内须有 `plugin.py`)
2. 打开 Amane →「管理 → 插件」→ 上传 zip, 或填写本机路径后安装
3. 启用插件; 播放源不必写入内容路由

打包示例 (在仓库根目录):

```powershell
Compress-Archive -Path community\local.potplayer\plugin.py -DestinationPath community\local.potplayer.zip -Force
```

若希望 zip 内带顶层目录:

```powershell
Compress-Archive -Path community\local.potplayer -DestinationPath community\local.potplayer.zip -Force
```

安装后可删除 zip 内的 `REF-user-plugins.md` (仅开发参考, 不影响运行).

## 配置

| 项 | 说明 |
| --- | --- |
| `executable` | PotPlayer 可执行文件路径; 留空则探测常见安装目录与 PATH |
| `args` | 附加命令行参数 (可选) |
| `ignore_strm` | 忽略 `.strm` 指针文件 (默认开启) |

## 行为说明

- `probe` 列出该条目已索引的本地文件, 并为可播流声明 `open` 操作
- `resolve` 只返回 `file` 目标供网页播放器取流, **不**启动 PotPlayer
- 用户点击「用 PotPlayer 打开」时调用 `action`, 才启动外部程序

## 参考

- 用户文档快照: `REF-user-plugins.md`
- 线上文档: https://sqzw-x.github.io/amane/user/plugins/
