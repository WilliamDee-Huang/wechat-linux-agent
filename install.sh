#!/bin/bash
# 安装到 ~/.local：脚本放 ~/.local/bin，辅助文件放 ~/.local/share/wechat-iso
set -euo pipefail
cd "$(dirname "$0")"
make -C share/ime/ibus >/dev/null
mkdir -p ~/.local/bin ~/.local/share/wechat-iso "${XDG_CONFIG_HOME:-$HOME/.config}/wechat-iso"
cp -r share/. ~/.local/share/wechat-iso/
install -m 755 bin/wechat-iso ~/.local/bin/wechat-iso
cfg="${XDG_CONFIG_HOME:-$HOME/.config}/wechat-iso/config.sh"
[ -f "$cfg" ] || cp examples/config.sh "$cfg"
echo "已安装：~/.local/bin/wechat-iso"
echo "配置文件：$cfg（先按你的输入法和启动方式改一下）"
