#!/usr/bin/env python3
import struct
import argparse

'''
Structs from xnu-8796.101.5 headers (see EXTERNAL_HEADERS/TrustCache)

#define CCSHA1_OUTPUT_SIZE  20
#define kTCEntryHashSize CCSHA1_OUTPUT_SIZE
#define kUUIDSize 16

typedef struct _TrustCacheModule1 {
    uint32_t                version;            /* Must be 1 */
    uint8_t                 uuid[kUUIDSize];
    uint32_t                numEntries;
    TrustCacheEntry1_t      entries[0];
} __attribute__((packed)) TrustCacheModule1_t;

typedef struct _TrustCacheEntry1 {
    uint8_t                 CDHash[kTCEntryHashSize];
    uint8_t                 hashType;
    uint8_t                 flags;
} __attribute__((packed)) TrustCacheEntry1_t;
'''

def make_trustcache(i,o):
  hashes = sorted(i.read().splitlines())

  for h in hashes: assert str == type(h) and 40 == len(h)

  tc=b''

  # TrustCacheModule1_t
  tc+=struct.pack("<I", 1)           # version
  tc+=b'A'*16                        # uuid
  tc+=struct.pack("<I", len(hashes)) # numEntries

  # TrustCacheEntry1_t entries
  for h in hashes:
    tc+=bytes.fromhex(h)    # CDHash
    tc+=struct.pack("B", 2) # hashType
    tc+=struct.pack("B", 0) # flags

  o.write(tc)

def main():
  p = argparse.ArgumentParser(prog='build_tc')
  p.add_argument('hashlist', type=argparse.FileType('r'))
  p.add_argument('out', type=argparse.FileType('wb', 0))
  args = p.parse_args()
  make_trustcache(args.hashlist, args.out)

if __name__=="__main__":
  main()
