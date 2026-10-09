"""在指定 X 屏幕上对一个外部窗口执行 GDK 窗口操作：winstate.py <窗口 id> unmaximize|maximize|deiconify|iconify"""
import sys, gi; gi.require_version('Gdk','3.0'); gi.require_version('GdkX11','3.0')
from gi.repository import Gdk, GdkX11
d=Gdk.Display.get_default(); w=GdkX11.X11Window.foreign_new_for_display(d,int(sys.argv[1]))
getattr(w, sys.argv[2])(); d.flush()
