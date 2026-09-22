/*
 * Apple DCP (Display CoProcessor) endpoint emulation.
 *
 * The display stack binds:
 *   RTBuddy(DCP) -> RTBuddyEndpointService "DCPEndpoint24"
 *                -> AppleDCPLinkServiceSoC -> AppleCLCD2 on disp0
 *                -> IOMobileFramebuffer
 *
 * Endpoint 0x24 speaks AFK (Apple Firmware Kit): a ring-buffer transport in
 * shared memory, on top of which the IOMFB RPC runs. This models the
 * coprocessor side of AFK far enough to complete the transport handshake, and
 * logs the IOMFB traffic that then flows so the RPC can be decoded.
 *
 * AFK framing and field layout: Asahi Linux drivers/gpu/drm/apple/afk.c (GPL-2).
 * The roles are mirrored here: Asahi is the application processor, we are the
 * coprocessor, so sends/receives are swapped relative to that reference.
 *
 * dcp_console_feed() is a side-channel: it has nothing to do with AFK/IOMFB,
 * it just draws the guest's raw serial console bytes onto the same
 * framebuffer XNU's /vram node points at, using QEMU's bundled 8x16 VGA font,
 * so there's visible output before IOMFB's own RPC is decoded far enough to
 * drive real framebuffer swaps.
 */
#include "qemu/osdep.h"
#include "qemu/bitops.h"
#include "system/address-spaces.h"
#include "ui/vgafont.h"
#include "hw/arm/apple_rtkit.h"
#include "hw/arm/apple_dcp.h"

#define DCP_EP_MAIN     0x24    /* "DCPEndpoint24" */
#define DCP_EP_ALT      0x25
#define DCP_EP_EPIC     0x23

/* ---- AFK ring-buffer endpoint protocol (afk.c) ---- */
#define RBEP_TYPE_SHIFT   48
#define RBEP_TYPE_MASK    0xffffULL

#define RBEP_INIT         0x80
#define RBEP_INIT_ACK     0xa0
#define RBEP_GETBUF       0x89
#define RBEP_GETBUF_ACK   0xa1
#define RBEP_INIT_TX      0x8a
#define RBEP_INIT_RX      0x8b
#define RBEP_START        0xa3
#define RBEP_START_ACK    0xa4
#define RBEP_RECV         0x85
#define RBEP_SHUTDOWN     0xc0
#define RBEP_SHUTDOWN_ACK 0xc1

#define BLOCK_SHIFT       6
#define GETBUF_SIZE_SHIFT 16
#define GETBUF_SIZE_MASK  0xffffULL
#define GETBUF_TAG_MASK   0xffffULL
#define GETBUF_ACK_DVA_MASK 0xffffffffffffULL   /* GENMASK(47,0) */
#define INITRB_OFFSET_SHIFT 32
#define INITRB_SIZE_SHIFT   16

/* dcp_console_feed() text console geometry, matches ui/vgafont.h. */
#define DCP_CON_FONT_W  8
#define DCP_CON_FONT_H  16
#define DCP_CON_FG      0x00e0e0e0u   /* light gray, XRGB */
#define DCP_CON_BG      0x00101018u   /* near-black, XRGB */

typedef struct AppleDCPState {
    AppleRTKit *rtk;
    uint32_t width, height, stride;
    hwaddr fb_base;

    /* AFK transport state for endpoint 0x24. */
    bool afk_inited;
    uint64_t bfr_dva;        /* shared buffer the guest allocated for us */
    uint32_t bfr_size;
    bool tx_ready, rx_ready, started;

    uint64_t msgs;
    int trace;

    /* dcp_console_feed() text console state. */
    uint8_t *fb_ptr;         /* direct guest-RAM pointer to the framebuffer */
    int cols, rows;
    int cur_col, cur_row;
} AppleDCPState;

/* Only one DCP instance ever exists in this machine; dcp_console_feed() is
 * called from exynos4210_uart.c with just a raw byte, so it needs somewhere
 * to find the active console without threading an opaque pointer through the
 * UART model. */
static AppleDCPState *g_dcp_console;

static uint64_t rbep(uint64_t type)
{
    return type << RBEP_TYPE_SHIFT;
}

/*
 * AFK handshake, coprocessor side. The guest driver opens the endpoint by
 * sending RBEP_INIT; we then drive the ring-buffer setup: ack, request a
 * shared buffer, describe the TX and RX rings inside it, and start.
 */
static bool dcp_ep_handler(AppleRTKit *rtk, uint32_t ep, uint64_t msg,
                           void *opaque)
{
    AppleDCPState *s = opaque;
    uint64_t type = (msg >> RBEP_TYPE_SHIFT) & RBEP_TYPE_MASK;

    s->msgs++;
    if (s->trace > 0) {
        s->trace--;
        printf("[dcp] ep=0x%02x afk-type=0x%llx msg=0x%016llx (#%llu)\n",
               ep, (unsigned long long)type, (unsigned long long)msg,
               (unsigned long long)s->msgs);
        fflush(stdout);
    }

    switch (type) {
    case RBEP_INIT:
        /* Ack, then ask the guest to allocate a shared buffer for the rings.
         * One 0x1000-byte block is plenty for the handshake. */
        apple_rtkit_send(rtk, ep, rbep(RBEP_INIT_ACK));
        apple_rtkit_send(rtk, ep,
                         rbep(RBEP_GETBUF) |
                         ((uint64_t)(0x1000 >> BLOCK_SHIFT) << GETBUF_SIZE_SHIFT) |
                         0x1 /* tag */);
        printf("[dcp] AFK INIT -> INIT_ACK + GETBUF\n");
        fflush(stdout);
        return true;

    case RBEP_GETBUF_ACK:
        s->bfr_dva = msg & GETBUF_ACK_DVA_MASK;
        printf("[dcp] AFK GETBUF_ACK: buffer dva 0x%llx\n",
               (unsigned long long)s->bfr_dva);
        /* Describe TX and RX rings within the buffer (first/second halves). */
        apple_rtkit_send(rtk, ep,
                         rbep(RBEP_INIT_TX) |
                         ((uint64_t)0 << INITRB_OFFSET_SHIFT) |
                         ((uint64_t)(0x800 >> BLOCK_SHIFT) << INITRB_SIZE_SHIFT) |
                         0x1);
        apple_rtkit_send(rtk, ep,
                         rbep(RBEP_INIT_RX) |
                         ((uint64_t)(0x800 >> BLOCK_SHIFT) << INITRB_OFFSET_SHIFT) |
                         ((uint64_t)(0x800 >> BLOCK_SHIFT) << INITRB_SIZE_SHIFT) |
                         0x2);
        apple_rtkit_send(rtk, ep, rbep(RBEP_START));
        s->afk_inited = true;
        fflush(stdout);
        return true;

    case RBEP_START_ACK:
        s->started = true;
        printf("[dcp] AFK transport up on endpoint 0x%02x -- IOMFB can flow\n", ep);
        fflush(stdout);
        return true;

    case RBEP_RECV: {
        /* The guest signalled it wrote into the TX ring (from its own
         * perspective -- the region we called INIT_TX when we set up the
         * rings). Dump the raw bytes: this DART model doesn't actually
         * translate addresses (see hw/arm/darwin.c's DART comment), so
         * bfr_dva should be usable directly as a guest-RAM address, same as
         * fb_base already is elsewhere in this file. */
        printf("[dcp] AFK RECV: guest posted an IOMFB message (ring at dva 0x%llx)\n",
               (unsigned long long)s->bfr_dva);
        MemoryRegionSection sec = memory_region_find(get_system_memory(),
                                                       s->bfr_dva, 0x800);
        if (sec.mr) {
            uint8_t *ring = (uint8_t *)memory_region_get_ram_ptr(sec.mr) +
                             sec.offset_within_region;
            printf("[dcp] ring bytes (first 256 of TX half):\n");
            for (int i = 0; i < 256; i += 16) {
                printf("[dcp]  +0x%03x:", i);
                for (int j = 0; j < 16; j++) {
                    printf(" %02x", ring[i + j]);
                }
                printf("\n");
            }
        } else {
            printf("[dcp] ring dump: no RAM found at dva 0x%llx\n",
                   (unsigned long long)s->bfr_dva);
        }
        fflush(stdout);
        return true;
    }

    default:
        printf("[dcp] AFK unhandled type 0x%llx msg 0x%016llx\n",
               (unsigned long long)type, (unsigned long long)msg);
        fflush(stdout);
        return true;
    }
}

static void dcp_con_fill_row(AppleDCPState *s, int row, uint32_t color)
{
    int y0 = row * DCP_CON_FONT_H;
    for (int y = 0; y < DCP_CON_FONT_H; y++) {
        uint32_t *line = (uint32_t *)(s->fb_ptr + (hwaddr)(y0 + y) * s->stride);
        for (int x = 0; x < s->width; x++) {
            line[x] = color;
        }
    }
}

static void dcp_con_scroll(AppleDCPState *s)
{
    size_t row_bytes = (size_t)s->stride * DCP_CON_FONT_H;
    memmove(s->fb_ptr, s->fb_ptr + row_bytes,
            (size_t)s->stride * s->height - row_bytes);
    dcp_con_fill_row(s, s->rows - 1, DCP_CON_BG);
}

static void dcp_con_draw_glyph(AppleDCPState *s, int row, int col, uint8_t ch)
{
    const uint8_t *glyph = &vgafont16[(int)ch * DCP_CON_FONT_H];
    int x0 = col * DCP_CON_FONT_W;
    int y0 = row * DCP_CON_FONT_H;

    for (int y = 0; y < DCP_CON_FONT_H; y++) {
        uint8_t bits = glyph[y];
        uint32_t *line = (uint32_t *)(s->fb_ptr + (hwaddr)(y0 + y) * s->stride);
        for (int x = 0; x < DCP_CON_FONT_W; x++) {
            line[x0 + x] = (bits & (0x80 >> x)) ? DCP_CON_FG : DCP_CON_BG;
        }
    }
}

void dcp_console_feed(const uint8_t *buf, int len)
{
    AppleDCPState *s = g_dcp_console;
    if (!s || !s->fb_ptr) {
        return;
    }

    for (int i = 0; i < len; i++) {
        uint8_t ch = buf[i];

        if (ch == '\r') {
            continue;
        }
        if (ch == '\n') {
            s->cur_col = 0;
            s->cur_row++;
        } else if (ch == '\b') {
            if (s->cur_col > 0) {
                s->cur_col--;
                dcp_con_draw_glyph(s, s->cur_row, s->cur_col, ' ');
            }
            continue;
        } else if (ch < 0x20 || ch >= 0x80) {
            continue;
        } else {
            dcp_con_draw_glyph(s, s->cur_row, s->cur_col, ch);
            s->cur_col++;
        }

        if (s->cur_col >= s->cols) {
            s->cur_col = 0;
            s->cur_row++;
        }
        if (s->cur_row >= s->rows) {
            dcp_con_scroll(s);
            s->cur_row = s->rows - 1;
        }
    }
}

void apple_dcp_attach(AppleRTKit *rtk, uint32_t width, uint32_t height,
                      hwaddr fb_base)
{
    AppleDCPState *s = g_new0(AppleDCPState, 1);

    s->rtk = rtk;
    s->width = width;
    s->height = height;
    s->stride = width * 4;
    s->fb_base = fb_base;
    s->trace = 400;

    apple_rtkit_add_endpoint(rtk, DCP_EP_EPIC,  "dcp-epic", dcp_ep_handler, s);
    apple_rtkit_add_endpoint(rtk, DCP_EP_MAIN,  "DCPEndpoint24", dcp_ep_handler, s);
    apple_rtkit_add_endpoint(rtk, DCP_EP_ALT,   "DCPEndpoint25", dcp_ep_handler, s);

    MemoryRegionSection sec = memory_region_find(get_system_memory(), fb_base,
                                                  (hwaddr)height * width * 4);
    if (sec.mr) {
        s->fb_ptr = (uint8_t *)memory_region_get_ram_ptr(sec.mr) +
                    sec.offset_within_region;
        s->cols = width / DCP_CON_FONT_W;
        s->rows = height / DCP_CON_FONT_H;
        s->cur_col = 0;
        s->cur_row = 0;
        for (int r = 0; r < s->rows; r++) {
            dcp_con_fill_row(s, r, DCP_CON_BG);
        }
        g_dcp_console = s;
        printf("[dcp] console feed attached: %dx%d chars on %ux%u fb\n",
               s->cols, s->rows, width, height);
    } else {
        printf("[dcp] console feed: no RAM at fb 0x%llx, text console disabled\n",
               (unsigned long long)fb_base);
    }

    printf("[dcp] AFK endpoints 0x%02x/0x%02x/0x%02x, %ux%u fb at 0x%llx\n",
           DCP_EP_EPIC, DCP_EP_MAIN, DCP_EP_ALT, width, height,
           (unsigned long long)fb_base);
    fflush(stdout);
}
