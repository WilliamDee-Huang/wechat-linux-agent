# 排错记录

## 投屏窗口突然消失，过十几分钟又一次

**现象：** `wechat-iso status` 显示 `wx-xpra` 和 `wx-attach` 都是 inactive，`journalctl --user -u wx-xpra` 里有 `code=dumped, status=7/BUS`。微信和 Xvfb 都还在运行。

**原因：** xpra 客户端默认用一块固定 2GB 的共享内存（mmap）传画面，文件放在 `$XDG_RUNTIME_DIR/xpra`。这个目录通常是一个只有内存 10% 大小的 tmpfs（8GB 内存时是 781MB）。2GB 的文件开始时是稀疏的，写到超出 tmpfs 实际空间的位置时，进程收到 SIGBUS。

**处理：** `wechat-iso attach` 通过环境变量 `XPRA_MMAP_MIN_SIZE` / `XPRA_MMAP_MAX_SIZE` 把它限制到 256MB（配置项 `WX_MMAP_SIZE`）。注意读写两块各占一份，要小于 tmpfs 大小的一半。

**不要**用 `--mmap=no` 关掉共享内存：xpra 6.5.4 会在服务端抛 `ModuleNotFoundError: No module named 'xpra.net.mmap.common'`，拒绝连接。关掉 mmap 后画面会改走 H.264 编码，打字也会明显变慢。

确认 mmap 生效：

```bash
xpra info :100 | grep -E 'window\.[0-9]+\.encoding='   # 应为 encoding=mmap
```

## 投屏后打字有延迟

先按上面的方法确认 `encoding=mmap`。如果显示的是 `h264`、`webp` 等，说明共享内存没有生效，每一帧都在压缩和解压。`--desktop-scaling=off` 也能省掉一次缩放。

## 窗口最大化以后还原不了，最小化按钮没反应

WSLg 的窗口管理器会执行投屏窗口的最大化请求，但不理会还原和最小化请求。微信标题栏上的按钮请求经过“微信 → xpra 服务端 → 投屏窗口 → WSLg”，在最后一步被忽略了。

**处理：** `wechat-iso normal`。它在虚拟屏幕一侧用 `xpra control :100 map <窗口>` 取消最小化，再发送 unmaximize。

## 不要用 systemctl 停掉投屏

`systemctl --user stop wx-attach` 或 `restart` 会让投屏客户端在退出时请求关闭窗口，xpra 随即结束微信进程，需要重新登录。断开投屏只用 `wechat-iso detach`（即 `xpra detach`）。`xpra stop :100` 只停服务端，不会结束微信（服务端用了 `--exit-with-children=no`）。

## 桌面上一个 Linux 窗口都不显示

如果连 `xeyes` 都不显示，或者 Alt+Tab 一直转圈，说明是 WSLg 本身卡住了，跟这个项目无关。在 Windows 的 PowerShell 里运行 `wsl --shutdown`，再重新打开终端，执行 `wechat-iso up`。

## 微信在独立网络命名空间里时连不上虚拟屏幕

Xvfb 默认同时监听抽象 socket（`@/tmp/.X11-unix/X100`）和文件 socket。抽象 socket 绑定在网络命名空间上，所以跑在独立 netns 里的微信只能用文件 socket。WSLg 下 `/tmp/.X11-unix` 是只读挂载，Xvfb 写不进文件 socket。

**处理：** 设 `WX_X11_OVERLAY=1`。`wechat-iso` 会在 `/tmp/.X11-unix` 上叠一层可写的 tmpfs，需要 sudo。

注意：WSLg 的 `/tmp/.X11-unix` 和 `/mnt/wslg/.X11-unix` 是 shared mount，直接叠 tmpfs 会把桌面的 `X0` 也盖住，桌面上所有新开的图形程序都会失败。必须先执行 `mount --make-private /tmp/.X11-unix` 断开联动，脚本已经这样做了。

## agent 读不到界面

- 微信要带 `QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1` 启动，否则不会注册到 AT-SPI。
- 用自己的启动器时，确认它把这个变量传给了微信：`tr '\0' '\n' < /proc/$(pgrep -x wechat)/environ | grep ACCESS`。
- 微信停在登录窗口时，只能读到很少的元素。

## Ubuntu 自带的 xpra 3.1.5 用不了

它的剪贴板模块和客户端在 Python 3.12 上会报错，投屏连不上。请按 xpra.org 的说明安装 6.x。
