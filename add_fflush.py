from pathlib import Path

p = Path.home()/'goldengate/qemu-sptm-cl4-native/hw/arm/xnuboot_sptm.c'
s = p.read_text()
needle = '    printf("SPTM base: 0x%016llX\\n", sptm_load);\n'
assert s.count(needle) == 1, f'expected exactly one match, found {s.count(needle)}'
s = s.replace(needle, needle + '    fflush(stdout);\n')
p.write_text(s)
print('patched', p)
