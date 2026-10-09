# 输入法适配

微信在虚拟屏幕上运行时，输入法也必须运行在虚拟屏幕上：微信要能找到它，候选词窗口也要画在虚拟屏幕上，才能随投屏显示到你桌面上。下面是在 ibus 上踩过的坑，按一次按键经过的顺序排列。

## 一次按键的路径

```
你的键盘 → 投屏窗口 → xpra 服务端 → 微信（Qt 的 ibus 插件）
  → 读地址文件 ~/.config/ibus/bus/<machine-id>-unix-<display>
  → ibus-daemon → 输入法引擎（拼音 → 候选词）
  → 候选面板 ibus-ui-gtk3（画在虚拟屏幕上，随投屏显示）
  → 选中的字上屏到微信
```

## 坑 1：xpra 自己起了一个没有候选窗的 ibus

xpra 服务端默认会运行 `ibus-daemon --xim --panel=disable --desktop=xpra`，候选面板是关掉的，所以打字时看不到候选词。

**处理：** 服务端加 `--input-method=keep`，不让 xpra 管输入法；`wechat-iso` 会关掉 xpra 的那个 ibus，自己起一个带候选面板的。

## 坑 2：ibus 带着 Wayland 环境变量启动

在 WSLg 或 Wayland 桌面里，终端里通常有 `WAYLAND_DISPLAY`。带着它启动的 ibus 和候选面板会走 Wayland，画不到虚拟屏幕上。

**处理：** 启动 ibus 时去掉 `WAYLAND_DISPLAY`，设置 `DISPLAY=:100` 和 `GDK_BACKEND=x11`。

## 坑 3：微信找错了地址文件

Qt 的 ibus 插件按下面的规则找 ibus 的地址文件：

```
~/.config/ibus/bus/<machine-id>-unix-<名字>
```

`<名字>` 优先取 `WAYLAND_DISPLAY`，没有才取 `DISPLAY` 的编号。虚拟屏幕上的 ibus 写的是 `…-unix-100`。如果启动微信时带着 `WAYLAND_DISPLAY=wayland-0`，微信就会去读 `…-unix-wayland-0`，连到桌面上的那个 ibus，或者一个已经退出的 ibus。

**处理：**
- 默认情况下，`wechat-iso` 启动微信时去掉 `WAYLAND_DISPLAY`，不会遇到这个问题。
- 如果你的微信启动器强制设置了 `WAYLAND_DISPLAY`（比如通过 sudo 启动的代理或网络隔离启动器），在配置里设 `WX_IBUS_WAYLAND_ALIAS=1`。`wechat-iso` 会把 `…-unix-wayland-0` 做成软链接，指向 `…-unix-100`。副作用是：链接存在期间，桌面上其他 Linux 程序的输入法也会连到虚拟屏幕上的 ibus。`wechat-iso down` 会删除这个链接。

## 坑 4：启动顺序

微信只在启动时连一次输入法，连不上就不再重试。之后再修好 ibus，微信也不会恢复中文输入。

**处理：** `wechat-iso up` 先启动 ibus，等它写好地址文件，最后才启动微信。如果中途重启了 ibus，也要重启微信。

## 坑 5：没有选中引擎

ibus 刚启动时可能没有当前引擎，切换输入法的快捷键只会在“English”之间切换。

**处理：** 在配置里设置 `WX_IBUS_ENGINE`，`wechat-iso` 启动后会直接切到这个引擎。有的引擎进程起得慢，脚本会重试。用 `ibus list-engine` 查引擎名，常见的有：

| 输入法 | 引擎名 |
|---|---|
| 智能拼音 | `libpinyin` |
| 中州韵 Rime | `rime` |
| 水杉输入法 | `msime-linux` |

注意：引擎已经是中文时再按切换快捷键，会切回英文。

## 坑 6：候选面板一启用某些引擎就崩溃

Ubuntu 24.04 的 `ibus-ui-gtk3` 有一个 bug：引擎发来带样式的辅助文本（`update-auxiliary-text`）时，面板会把不认识的样式属性变成 NULL 交给 `pango_attr_list_change()`，pango 解引用 NULL 后崩溃。已知水杉输入法会触发，其他引擎也可能。

**处理：** `share/ime/ibus/pango-null-guard.c` 是一个很小的 `LD_PRELOAD` 库，遇到 NULL 属性就跳过，其余调用原样转给 pango。它只通过 `ibus-panel.sh` 加载给虚拟屏幕上的候选面板，不影响系统里的其他程序。不需要时可以设 `WX_IBUS_PANEL_GUARD=0`。

排查方法：如果候选窗一闪就没，看 `journalctl --user -u wx-ibus` 里面板是否反复退出，再用 `gdb -p <ibus-ui-gtk3 的 pid>` 抓崩溃时的调用栈。

## fcitx5（实验性）

`WX_IME=fcitx5` 会在虚拟屏幕上启动 `fcitx5 --replace`，并以 `QT_IM_MODULE=fcitx` 启动微信。这条路径**没有实测**。已知的限制是：fcitx5 通过 D-Bus 会话总线提供服务，同一个会话里只能有一个实例，所以它会和桌面上正在运行的 fcitx5 冲突。欢迎提交测试结果。
