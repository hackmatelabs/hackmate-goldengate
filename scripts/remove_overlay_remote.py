from pathlib import Path
import subprocess

root = Path.home() / 'goldengate/qemu-sptm-cl4-native'
p = root / 'hw/arm/darwin.c'
s = p.read_text()
start = s.index('typedef struct DarwinFB {')
end = s.index('static const GraphicHwOps darwin_fb_ops', start)
s = s[:start] + '''typedef struct DarwinFB {
    QemuConsole *con;
} DarwinFB;

static bool darwin_fb_update(void *opaque) {
    DarwinFB *fb = opaque;
    qemu_console_update_full(fb->con);
    return true;
}

''' + s[end:]
start = s.index('    fb->ram = ptr;')
end = s.index('    /* Route the display', start)
s = s[:start] + '''    fb->con = qemu_graphic_console_create(NULL, 0, &darwin_fb_ops, fb);
    qemu_console_set_surface(fb->con,
        qemu_create_displaysurface_from(info->fb_width, info->fb_height,
                                       PIXMAN_x8r8g8b8, info->fb_width * 4, ptr));

''' + s[end:]
assert 'DARWIN_FB_PPM' not in s and 'overlay' not in s
p.write_text(s)

p = root / 'hw/arm/apple_dcp.c'
s = p.read_text()
needle = '    MemoryRegionSection sec = memory_region_find(get_system_memory(), fb_base,'
assert s.count(needle) == 1
s = s.replace(needle, '''    /* Serial rendering is a diagnostic aid and must be explicitly requested.
     * Otherwise only guest framebuffer writes may produce visible pixels. */
    const char *console_mode = getenv("DARWIN_DCP_CONSOLE");
    if (!console_mode || strcmp(console_mode, "1")) {
        printf("[dcp] serial renderer disabled; framebuffer is guest-owned\\n");
        return;
    }

''' + needle)
p.write_text(s)
subprocess.run(['/usr/local/homebrew/Cellar/ninja/1.13.2/bin/ninja',
                'qemu-system-aarch64'], cwd=root/'build', check=True)
