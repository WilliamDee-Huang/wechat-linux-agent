/*
 * 只给虚拟屏幕上的 ibus 候选面板（ibus-ui-gtk3）预加载。
 * Ubuntu 24.04 的 ibus-ui-gtk3 在处理部分引擎（已知：水杉 msime-linux）发来的辅助文本时，会把不认识的文本属性
 * 转成 NULL 再交给 pango_attr_list_change()，pango 解引用 NULL 后崩溃。
 * 这里只是跳过 NULL 属性，其余调用原样转给真正的 pango。
 * 编译: gcc -shared -fPIC -O2 -o pango-null-guard.so pango-null-guard.c -ldl
 */
#define _GNU_SOURCE
#include <dlfcn.h>

typedef void (*attr_fn)(void *list, void *attr);

static attr_fn real(const char *name)
{
    return (attr_fn)dlsym(RTLD_NEXT, name);
}

void pango_attr_list_change(void *list, void *attr)
{
    static attr_fn fn;
    if (!attr)
        return;
    if (!fn)
        fn = real("pango_attr_list_change");
    fn(list, attr);
}

void pango_attr_list_insert(void *list, void *attr)
{
    static attr_fn fn;
    if (!attr)
        return;
    if (!fn)
        fn = real("pango_attr_list_insert");
    fn(list, attr);
}

void pango_attr_list_insert_before(void *list, void *attr)
{
    static attr_fn fn;
    if (!attr)
        return;
    if (!fn)
        fn = real("pango_attr_list_insert_before");
    fn(list, attr);
}
