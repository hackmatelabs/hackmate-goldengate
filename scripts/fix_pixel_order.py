from pathlib import Path
p=Path('~/goldengate/qemu-sptm-cl4-native/hw/arm/darwin.c').expanduser()
s=p.read_text()
old='''            dst[di + 0] = fb->overlay[si + 0];
            dst[di + 1] = fb->overlay[si + 1];
            dst[di + 2] = fb->overlay[si + 2];'''
new='''            /* PIXMAN_x8r8g8b8 is stored as B,G,R,X on little-endian hosts. */
            dst[di + 0] = fb->overlay[si + 2];
            dst[di + 1] = fb->overlay[si + 1];
            dst[di + 2] = fb->overlay[si + 0];'''
if old not in s: raise SystemExit('pixel block missing')
p.write_text(s.replace(old,new,1))
