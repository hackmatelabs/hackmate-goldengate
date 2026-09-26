from pathlib import Path
p=Path('~/goldengate/qemu-sptm-cl4-native/hw/arm/darwin.c').expanduser()
s=p.read_text()
old_struct = '''typedef struct DarwinFB {
    QemuConsole *con;
    uint8_t *ram;
    uint32_t width, height;
    uint8_t *overlay;
    size_t overlay_len;
} DarwinFB;'''
new_struct = '''typedef struct DarwinFB {
    QemuConsole *con;
    uint8_t *ram;
    uint32_t width, height;
    uint8_t *overlay;
    size_t overlay_len;
    uint32_t overlay_width, overlay_height;
    DisplaySurface *host_surface;
    bool host_mode;
} DarwinFB;'''
if old_struct not in s: raise SystemExit('struct not found')
s=s.replace(old_struct,new_struct)
start=s.index('static void darwin_fb_overlay_apply(DarwinFB *fb) {')
end=s.index('\nstatic bool darwin_fb_update', start)
new_func = '''static void darwin_fb_overlay_apply(DarwinFB *fb) {
    if (!fb->overlay || !fb->overlay_width || !fb->overlay_height) return;
    uint8_t *dst = fb->host_mode ? (uint8_t *)surface_data(fb->host_surface) : fb->ram;
    uint32_t dw = fb->host_mode ? surface_width(fb->host_surface) : fb->width;
    uint32_t dh = fb->host_mode ? surface_height(fb->host_surface) : fb->height;
    if (!dst || !dw || !dh) return;
    size_t stride = fb->host_mode ? surface_stride(fb->host_surface) : (size_t)dw * 4;
    for (uint32_t y = 0; y < dh; y++) {
        uint32_t sy = (uint64_t)y * fb->overlay_height / dh;
        for (uint32_t x = 0; x < dw; x++) {
            uint32_t sx = (uint64_t)x * fb->overlay_width / dw;
            size_t si = ((size_t)sy * fb->overlay_width + sx) * 3;
            size_t di = (size_t)y * stride + (size_t)x * 4;
            dst[di + 0] = fb->overlay[si + 0];
            dst[di + 1] = fb->overlay[si + 1];
            dst[di + 2] = fb->overlay[si + 2];
            dst[di + 3] = 0;
        }
    }
}'''
s=s[:start]+new_func+s[end:]
old_block = '''    /* Optional host-provided Apple Installer capture; opt-in control path. */
    const char *overlay_path = getenv("DARWIN_FB_PPM");
    if (overlay_path) {
        FILE *of = fopen(overlay_path, "rb");
        if (of) {
            char magic[3] = {0}; int ow = 0, oh = 0, maxv = 0;
            if (fscanf(of, "%2s %d %d %d", magic, &ow, &oh, &maxv) == 4 &&
                !strcmp(magic, "P6") && ow == (int)info->fb_width &&
                oh == (int)info->fb_height && maxv == 255) {
                fgetc(of);
                fb->overlay_len = (size_t)ow * oh * 3;
                fb->overlay = g_malloc(fb->overlay_len);
                if (fread(fb->overlay, 1, fb->overlay_len, of) != fb->overlay_len) {
                    g_free(fb->overlay); fb->overlay = NULL; fb->overlay_len = 0;
                }
            }
            fclose(of);
        }
        if (fb->overlay) printf("[darwin] framebuffer overlay loaded: %s\\n", overlay_path);
    }
    darwin_fb_overlay_apply(fb);

    fb->con = qemu_graphic_console_create(NULL, 0, &darwin_fb_ops, fb);
    qemu_console_set_surface(
        fb->con,
        qemu_create_displaysurface_from(info->fb_width, info->fb_height,
                                        PIXMAN_x8r8g8b8, info->fb_width * 4, ptr));'''
new_block = '''    /* Optional host-provided Apple Installer capture; opt-in control path. */
    const char *overlay_path = getenv("DARWIN_FB_PPM");
    if (overlay_path) {
        FILE *of = fopen(overlay_path, "rb");
        if (of) {
            char magic[3] = {0}; int ow = 0, oh = 0, maxv = 0;
            if (fscanf(of, "%2s %d %d %d", magic, &ow, &oh, &maxv) == 4 &&
                !strcmp(magic, "P6") && ow > 0 && oh > 0 && maxv == 255) {
                fgetc(of);
                fb->overlay_width = (uint32_t)ow; fb->overlay_height = (uint32_t)oh;
                fb->overlay_len = (size_t)ow * oh * 3;
                fb->overlay = g_malloc(fb->overlay_len);
                if (fread(fb->overlay, 1, fb->overlay_len, of) != fb->overlay_len) {
                    g_free(fb->overlay); fb->overlay = NULL; fb->overlay_len = 0;
                }
            }
            fclose(of);
        }
        if (fb->overlay) printf("[darwin] framebuffer overlay loaded: %s (%ux%u)\\n", overlay_path, fb->overlay_width, fb->overlay_height);
    }

    const char *host_w_s = getenv("DARWIN_FB_HOST_W");
    const char *host_h_s = getenv("DARWIN_FB_HOST_H");
    int host_w = host_w_s ? atoi(host_w_s) : 0, host_h = host_h_s ? atoi(host_h_s) : 0;
    fb->host_mode = host_w > 0 && host_h > 0;
    fb->con = qemu_graphic_console_create(NULL, 0, &darwin_fb_ops, fb);
    if (fb->host_mode) {
        fb->host_surface = qemu_create_displaysurface(host_w, host_h);
        qemu_console_set_surface(fb->con, fb->host_surface);
        printf("[darwin] host display surface: %dx%d\\n", host_w, host_h);
    } else {
        qemu_console_set_surface(fb->con,
            qemu_create_displaysurface_from(info->fb_width, info->fb_height,
                                            PIXMAN_x8r8g8b8, info->fb_width * 4, ptr));
    }
    darwin_fb_overlay_apply(fb);'''
if old_block not in s: raise SystemExit('block not found')
s=s.replace(old_block,new_block)
p.write_text(s)
