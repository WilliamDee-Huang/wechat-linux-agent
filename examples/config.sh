# wechat-iso 配置示例。复制到 ~/.config/wechat-iso/config.sh 后按需修改。

# 微信启动命令。官方 deb 包装在 /opt/wechat/wechat；如果你有自己的启动器（代理、网络隔离等），写在这里
WX_CMD=/opt/wechat/wechat
WX_ARGS="-platform xcb"

# 虚拟屏幕
WX_DISPLAY=:100
WX_SCREEN=1600x1000x24

# 输入法：ibus | fcitx5 | none
WX_IME=ibus
# 启动后切到哪个 ibus 引擎。用 `ibus list-engine` 查名字，例如：
#   libpinyin（智能拼音） rime（中州韵） msime-linux（水杉）
WX_IBUS_ENGINE=libpinyin

# 你的启动器如果强制设置了 WAYLAND_DISPLAY=wayland-0（WSLg 下常见），设为 1
WX_IBUS_WAYLAND_ALIAS=0

# 微信跑在独立网络命名空间（netns）里时，连不上抽象 X socket，需要设为 1（会用到 sudo mount）
WX_X11_OVERLAY=0
