#!/usr/bin/env python3
"""Minimal, from-scratch, READ-ONLY APFS raw structure reader, built against
the real ~27GB Golden Gate macOS system volume dmg. Verified working through:
  container superblock -> container object map -> volume superblock ->
  volume object map -> (TOC-based b-tree descent, IN PROGRESS beyond the
  volume-omap root -- see PHASE7_LOG.md "Attempt 3" for the exact known bug:
  child selection at a non-root omap node currently picks the wrong child).

Nothing here writes to the image. Do not add write support without extreme
care (Fletcher-64 node checksums, space-manager allocation, and B-tree TOC
updates are all still unverified/unimplemented) -- see PHASE7_LOG.md.

KEY LESSON (cost real debugging time, don't repeat it): for any b-tree node
with nkeys > 1, you MUST read the actual TOC (table of contents) array to
get correct key/value offsets and ORDER. Do not assume fixed-stride indexing
(key[i] at header_end+i*key_size) even for BTNODE_FIXED_KV_SIZE nodes -- that
only means keys/values have constant SIZE, not that they're stored in
sorted physical order. Reading without the TOC gives a plausible-LOOKING but
wrong key sequence for anything beyond the trivial 1-entry case.
"""
import struct

BS = 4096  # block size for this specific image; re-derive from nx_block_size if reusing elsewhere

OBJ_TYPE_OMAP = 0xb
OBJ_TYPE_BTREE = 0x2
OBJ_TYPE_BTREE_NODE = 0x3
OBJ_PHYSICAL = 0x40000000

BTNODE_ROOT = 0x1
BTNODE_LEAF = 0x2
BTNODE_FIXED_KV_SIZE = 0x4


class APFSImage:
    def __init__(self, path):
        self.f = open(path, "rb")

    def read_block(self, n):
        self.f.seek(n * BS)
        return self.f.read(BS)

    def obj_type(self, block):
        return struct.unpack_from("<I", block, 24)[0]

    # ---- container level ----

    def read_container_superblock(self):
        nxsb = self.read_block(0)
        assert nxsb[32:36] == b"NXSB"
        block_size, block_count = struct.unpack_from("<IQ", nxsb, 36)
        nx_next_oid, nx_next_xid = struct.unpack_from("<QQ", nxsb, 88)
        nx_spaceman_oid, nx_omap_oid, nx_reaper_oid = struct.unpack_from("<QQQ", nxsb, 152)
        nx_fs_oid = struct.unpack_from("<100Q", nxsb, 184)
        return dict(
            block_size=block_size, block_count=block_count,
            next_oid=nx_next_oid, next_xid=nx_next_xid,
            spaceman_oid=nx_spaceman_oid, omap_oid=nx_omap_oid,
            reaper_oid=nx_reaper_oid, fs_oid=[o for o in nx_fs_oid if o],
        )

    def read_omap_header(self, omap_block_num):
        b = self.read_block(omap_block_num)
        assert self.obj_type(b) == (OBJ_PHYSICAL | OBJ_TYPE_OMAP), hex(self.obj_type(b))
        om_tree_oid = struct.unpack_from("<Q", b, 48)[0]
        return om_tree_oid

    # ---- generic b-tree node parsing (the part that MUST use the TOC) ----

    def node_header(self, b):
        btn_flags, btn_level = struct.unpack_from("<HH", b, 32)
        btn_nkeys = struct.unpack_from("<I", b, 36)[0]
        table_off, table_len = struct.unpack_from("<HH", b, 40)
        is_root = bool(btn_flags & BTNODE_ROOT)
        is_leaf = bool(btn_flags & BTNODE_LEAF)
        return dict(flags=btn_flags, level=btn_level, nkeys=btn_nkeys,
                    table_off=table_off, table_len=table_len,
                    is_root=is_root, is_leaf=is_leaf)

    def toc_entry(self, b, hdr, i):
        """Returns (k_off, v_off) for TOC index i (0-based, in TOC/logical order)."""
        return struct.unpack_from("<HH", b, 56 + hdr["table_off"] + i * 4)

    def key_bytes(self, b, hdr, k_off, key_size):
        key_area = 56 + hdr["table_len"]
        return b[key_area + k_off: key_area + k_off + key_size]

    def val_bytes(self, b, hdr, v_off, val_size):
        trailer = 40 if hdr["is_root"] else 0
        val_area_end = BS - trailer
        start = val_area_end - v_off
        return b[start: start + val_size]

    def omap_entry(self, b, hdr, i):
        """For an omap-style node (16-byte key {oid,xid}, and either a
        16-byte omap_val_t {flags,size,paddr} if leaf, or an 8-byte child
        oid if not)."""
        k_off, v_off = self.toc_entry(b, hdr, i)
        oid, xid = struct.unpack_from("<QQ", self.key_bytes(b, hdr, k_off, 16))
        if hdr["is_leaf"]:
            vflags, vsize, paddr = struct.unpack_from("<IIQ", self.val_bytes(b, hdr, v_off, 16))
            return oid, xid, ("leaf", vflags, vsize, paddr)
        else:
            child = struct.unpack_from("<Q", self.val_bytes(b, hdr, v_off, 8))[0]
            return oid, xid, ("node", child)

    def resolve_omap(self, root_block, target_oid, max_xid=None):
        """Descend an omap b-tree (container- or volume-level) to find the
        paddr for target_oid. Fixed two bugs (see PHASE7_LOG.md): (1)
        val_bytes had an extra spurious `- val_size` term, which silently
        shifted every non-leaf child pointer to the WRONG table slot by a
        constant, self-consistent offset -- looked plausible (valid
        BTREE_NODE object types) but pointed at the wrong subtree entirely;
        (2) child selection now scans the whole TOC (entries are in sorted
        key order) and picks the LAST entry whose oid <= target, which is
        the standard b+tree invariant (key[i] equals the smallest oid
        present in child[i]'s subtree)."""
        node_block = root_block
        while True:
            b = self.read_block(node_block)
            hdr = self.node_header(b)
            entries = [self.omap_entry(b, hdr, i) for i in range(hdr["nkeys"])]
            if hdr["is_leaf"]:
                best = None
                for oid, xid, val in entries:
                    if oid == target_oid and (max_xid is None or xid <= max_xid):
                        if best is None or xid > best[1]:
                            best = (oid, xid, val)
                return best[2][3] if best else None  # paddr
            else:
                child = None
                for oid, xid, val in entries:
                    if oid <= target_oid:
                        child = val[1]
                if child is None:
                    child = entries[0][2][1]
                node_block = child

    # ---- filesystem (catalog) b-tree: variable-length kvloc_t entries ----
    # j_key_t: low 60 bits = object id, top 4 bits = record type.
    APFS_TYPE_INODE = 3
    APFS_TYPE_FILE_EXTENT = 8
    APFS_TYPE_DIR_REC = 9
    OBJ_ID_MASK = (1 << 60) - 1
    LEN_MASK = (1 << 56) - 1

    def toc_entry_var(self, b, hdr, i):
        """kvloc_t: (k_off, k_len, v_off, v_len), used when the node is NOT
        BTNODE_FIXED_KV_SIZE (catalog/fs-tree nodes have variable-length
        keys and values, unlike the fixed-size omap nodes)."""
        return struct.unpack_from("<HHHH", b, 56 + hdr["table_off"] + i * 8)

    def fs_entry(self, b, hdr, i):
        """Returns (obj_id, rec_type, key_bytes, val_bytes) for a catalog
        node entry, whether leaf or non-leaf. Non-leaf values are 8-byte
        child block numbers; leaf values are raw j_inode_val_t / j_drec_val_t
        etc bytes the caller interprets based on rec_type."""
        k_off, k_len, v_off, v_len = self.toc_entry_var(b, hdr, i)
        kb = self.key_bytes(b, hdr, k_off, k_len)
        oid_and_type = struct.unpack_from("<Q", kb, 0)[0]
        obj_id = oid_and_type & self.OBJ_ID_MASK
        rec_type = oid_and_type >> 60
        if hdr["is_leaf"]:
            vb = self.val_bytes(b, hdr, v_off, v_len)
        else:
            vb = self.val_bytes(b, hdr, v_off, 8)
        return obj_id, rec_type, kb, vb

    def fs_node_entries(self, block_num):
        b = self.read_block(block_num)
        hdr = self.node_header(b)
        n = hdr["nkeys"]
        entries = [self.fs_entry(b, hdr, i) for i in range(n)]
        return b, hdr, entries

    def descend_fs_tree(self, root_block, target_obj_id, target_type, vol_om_tree_oid=None):
        """Descend a catalog b-tree to the leaf node that would contain
        (target_obj_id, target_type), using the same 'last key <= target'
        invariant as the omap descent, comparing (obj_id, rec_type) as a
        combined sort key (matches on-disk j_key_t ordering).

        IMPORTANT: this fs (root) tree's apfs_superblock root_tree_type is
        0x2 (OBJECT_TYPE_BTREE with NO storage-type bit set, i.e. storage
        type OBJ_VIRTUAL == 0). That means every non-leaf child "pointer"
        in this tree is itself a virtual OID, not a physical block number
        -- it must be re-resolved through the volume omap on every hop,
        exactly like the top-level root_tree_oid was. Treating child values
        as direct block numbers gives block numbers that happen to be
        in-range but point at unrelated/garbage physical blocks (found by
        checking obj_type() on the "child" -- none matched a valid
        BTREE/BTREE_NODE type). vol_om_tree_oid must be passed for any
        non-leaf descent beyond the (already-resolved) root_block."""
        node_block = root_block
        target_key = (target_obj_id, target_type)
        while True:
            b, hdr, entries = self.fs_node_entries(node_block)
            if hdr["is_leaf"]:
                return b, hdr, entries
            child_oid = None
            for obj_id, rec_type, kb, vb in entries:
                if (obj_id, rec_type) <= target_key:
                    child_oid = struct.unpack_from("<Q", vb, 0)[0]
            if child_oid is None:
                child_oid = struct.unpack_from("<Q", entries[0][3], 0)[0]
            assert vol_om_tree_oid is not None, "need vol_om_tree_oid to resolve virtual fs-tree child"
            node_block = self.resolve_omap(vol_om_tree_oid, child_oid)
            assert node_block is not None, f"omap resolve failed for child oid {child_oid}"

    def find_dir_rec(self, root_block, parent_obj_id, name, vol_om_tree_oid=None):
        """Find a APFS_TYPE_DIR_REC entry named `name` inside directory
        parent_obj_id. Dir-rec keys are hashed (name-hash + length packed
        with the name string), so we can't binary-search by name directly
        without reimplementing the hash -- instead descend to the right
        leaf via the (obj_id, DIR_REC) prefix, then linear-scan leaf(s)
        for a matching name. Returns (target_obj_id, raw value bytes) or
        None."""
        name_b = name.encode() + b"\x00"
        b, hdr, entries = self.descend_fs_tree(root_block, parent_obj_id, self.APFS_TYPE_DIR_REC, vol_om_tree_oid)
        for obj_id, rec_type, kb, vb in entries:
            if obj_id != parent_obj_id or rec_type != self.APFS_TYPE_DIR_REC:
                continue
            # j_drec_hashed_key_t: u64 obj_id_and_type, then u32 name_len_and_hash, then name[]
            name_len_and_hash = struct.unpack_from("<I", kb, 8)[0]
            name_len = name_len_and_hash & 0x3FF
            rec_name = kb[12:12 + name_len]
            if rec_name == name_b or rec_name == name_b[:-1]:
                # j_drec_val_t: u64 file_id, u64 date_added, u16 flags, then xfields
                file_id, date_added, flags = struct.unpack_from("<QQH", vb, 0)
                return file_id, vb
        return None

    def find_inode(self, root_block, obj_id, vol_om_tree_oid=None):
        """Find the APFS_TYPE_INODE record for obj_id. Returns (b, val_off,
        val_bytes) so the caller can compute the absolute file offset to
        patch in place."""
        b, hdr, entries = self.descend_fs_tree(root_block, obj_id, self.APFS_TYPE_INODE, vol_om_tree_oid)
        for i, (oid, rec_type, kb, vb) in enumerate(entries):
            if oid == obj_id and rec_type == self.APFS_TYPE_INODE:
                k_off, k_len, v_off, v_len = self.toc_entry_var(b, hdr, i)
                return b, hdr, k_off, k_len, v_off, v_len, vb
        return None

    def find_file_extents(self, root_block, private_id, vol_om_tree_oid=None):
        """Returns [(logical_offset, length, phys_block_num), ...] for a
        file's private_id (private_id from its inode record, NOT its
        catalog obj_id -- APFS_TYPE_FILE_EXTENT keys are indexed by the
        file's private_id). j_file_extent_key_t: obj_id_and_type(8) then
        logical_addr(8). j_file_extent_val_t: len_and_flags(8, low 56 bits
        = length in bytes) then phys_block_num(8) then crypto_id(8)."""
        b, hdr, entries = img_entries = self.descend_fs_tree(
            root_block, private_id, self.APFS_TYPE_FILE_EXTENT, vol_om_tree_oid)
        out = []
        for i, (obj_id, rec_type, kb, vb) in enumerate(entries):
            if obj_id != private_id or rec_type != self.APFS_TYPE_FILE_EXTENT:
                continue
            k_off, k_len, v_off, v_len = self.toc_entry_var(b, hdr, i)
            logical_addr = struct.unpack_from("<Q", kb, 8)[0]
            len_and_flags, phys_block_num = struct.unpack_from("<QQ", vb, 0)
            length = len_and_flags & self.LEN_MASK
            out.append((logical_addr, length, phys_block_num))
        out.sort()
        return out

    def read_file(self, root_block, obj_id, vol_om_tree_oid=None):
        """Read a regular file's full contents by resolving its inode (for
        private_id + uncompressed_size) then its extents."""
        inode = self.find_inode(root_block, obj_id, vol_om_tree_oid)
        if inode is None:
            return None
        b, hdr, k_off, k_len, v_off, v_len, vb = inode
        private_id = struct.unpack_from("<Q", vb, 8)[0]
        size = struct.unpack_from("<Q", vb, 84)[0]
        extents = self.find_file_extents(root_block, private_id, vol_om_tree_oid)
        data = bytearray()
        for logical_addr, length, phys_block_num in extents:
            self.f.seek(phys_block_num * BS)
            data += self.f.read(length)
        return bytes(data[:size])

    # ---- volume level ----

    def read_volume_superblock(self, paddr):
        vol = self.read_block(paddr)
        assert vol[32:36] == b"APSB"
        # wrapped_meta_crypto_state_t is 20 bytes, at offset 96 -> ends 116
        root_tree_type, extentref_tree_type, snap_meta_tree_type = struct.unpack_from("<III", vol, 116)
        omap_oid, root_tree_oid, extentref_tree_oid, snap_meta_tree_oid = struct.unpack_from("<QQQQ", vol, 128)
        return dict(omap_oid=omap_oid, root_tree_oid=root_tree_oid,
                    extentref_tree_oid=extentref_tree_oid,
                    snap_meta_tree_oid=snap_meta_tree_oid)


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "/Users/raahimsyed/goldengate/system_volume/26A428__MacOS/decrypted/043-70867-635.dmg"
    img = APFSImage(path)
    nxsb = img.read_container_superblock()
    print("container superblock:", nxsb)
    om_tree_oid = img.read_omap_header(nxsb["omap_oid"])
    print("container omap tree_oid:", om_tree_oid)
    vol_paddr = img.resolve_omap(om_tree_oid, nxsb["fs_oid"][0])
    print("volume superblock paddr:", vol_paddr)
    vsb = img.read_volume_superblock(vol_paddr)
    print("volume superblock:", vsb)
    vol_om_tree_oid = img.read_omap_header(vsb["omap_oid"])
    print("volume omap tree_oid:", vol_om_tree_oid)
    fs_root_paddr = img.resolve_omap(vol_om_tree_oid, vsb["root_tree_oid"])
    print("fs tree root paddr (BUGGY until child-selection is fixed):", fs_root_paddr)
