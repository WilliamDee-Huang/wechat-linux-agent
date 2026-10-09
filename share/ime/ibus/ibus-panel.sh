#!/bin/sh
# 虚拟屏幕专用的 ibus 候选面板：预加载 pango-null-guard.so，
# 避免引擎发来的辅助文本（update-auxiliary-text）让 Ubuntu 24.04 的 ibus-ui-gtk3 崩溃。
HERE="$(cd "$(dirname "$0")" && pwd)"
for p in /usr/libexec/ibus-ui-gtk3 /usr/lib/ibus/ibus-ui-gtk3 /usr/lib/x86_64-linux-gnu/ibus/ibus-ui-gtk3; do
  [ -x "$p" ] && PANEL="$p" && break
done
LD_PRELOAD="$HERE/pango-null-guard.so${LD_PRELOAD:+:$LD_PRELOAD}" exec "${PANEL:-/usr/libexec/ibus-ui-gtk3}" "$@"
