from __future__ import annotations

import binascii
import json
import struct
from dataclasses import dataclass
from pathlib import Path

MAGIC = b"ORX1"
FORMAT_VERSION = 1
ABI_VERSION = 1
MACHINE_VM64 = 1
HEADER_SIZE = 96
HEADER = struct.Struct("<4sHHHH21I")

PERMISSIONS = {
    "graphics": 1 << 0,
    "input": 1 << 1,
    "filesystem_read": 1 << 2,
    "filesystem_write": 1 << 3,
    "clipboard": 1 << 4,
    "network": 1 << 5,
    "audio": 1 << 6,
}
KNOWN_PERMISSION_MASK = sum(PERMISSIONS.values())

FLAG_GUI = 1 << 0
FLAG_CONSOLE = 1 << 1
KNOWN_FLAG_MASK = FLAG_GUI | FLAG_CONSOLE


def align(value: int, alignment: int = 16) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


def permission_mask(names: list[str]) -> int:
    mask = 0
    for name in names:
        try:
            mask |= PERMISSIONS[name]
        except KeyError as exc:
            raise ValueError(f"unknown ORX permission: {name}") from exc
    return mask


def permission_names(mask: int) -> list[str]:
    if mask & ~KNOWN_PERMISSION_MASK:
        raise ValueError(f"unknown ORX permission bits: 0x{mask & ~KNOWN_PERMISSION_MASK:x}")
    return [name for name, bit in PERMISSIONS.items() if mask & bit]


@dataclass(frozen=True)
class OrxHeader:
    format_version: int
    abi_version: int
    machine: int
    header_size: int
    flags: int
    permissions: int
    entry: int
    code_offset: int
    code_size: int
    rodata_offset: int
    rodata_size: int
    meta_offset: int
    meta_size: int
    icon_offset: int
    icon_size: int
    file_size: int
    payload_crc32: int
    stack_size: int
    heap_size: int
    min_os_version: int

    @classmethod
    def unpack_from(cls, data: bytes) -> "OrxHeader":
        if len(data) < HEADER_SIZE:
            raise ValueError("file is smaller than the ORX header")
        vals = HEADER.unpack_from(data)
        magic, fmt, abi, machine, hsize, *ints = vals
        if magic != MAGIC:
            raise ValueError(f"bad ORX magic: {magic!r}")
        if hsize != HEADER_SIZE:
            raise ValueError(f"unsupported ORX header size: {hsize}")
        return cls(fmt, abi, machine, hsize, *ints[:16])

    def validate(self, data: bytes) -> None:
        if self.format_version != FORMAT_VERSION:
            raise ValueError(f"unsupported ORX format version {self.format_version}")
        if self.abi_version != ABI_VERSION:
            raise ValueError(f"unsupported Orion App ABI {self.abi_version}")
        if self.machine != MACHINE_VM64:
            raise ValueError(f"unsupported ORX machine {self.machine}")
        if self.flags & ~KNOWN_FLAG_MASK:
            raise ValueError(f"unknown ORX flag bits: 0x{self.flags & ~KNOWN_FLAG_MASK:x}")
        if self.permissions & ~KNOWN_PERMISSION_MASK:
            raise ValueError(f"unknown ORX permission bits: 0x{self.permissions & ~KNOWN_PERMISSION_MASK:x}")
        if self.file_size != len(data):
            raise ValueError(f"file size mismatch: header={self.file_size} actual={len(data)}")
        if not self.code_size or self.code_size % 8:
            raise ValueError("code section must be a non-empty multiple of 8 bytes")

        intervals: list[tuple[int, int, str]] = []
        for name, off, size in (
            ("code", self.code_offset, self.code_size),
            ("rodata", self.rodata_offset, self.rodata_size),
            ("metadata", self.meta_offset, self.meta_size),
            ("icon", self.icon_offset, self.icon_size),
        ):
            if size == 0:
                continue
            if off < HEADER_SIZE or off > len(data) or size > len(data) - off:
                raise ValueError(f"{name} section is out of file bounds")
            if off % 16:
                raise ValueError(f"{name} section is not 16-byte aligned")
            intervals.append((off, off + size, name))
        intervals.sort()
        for (_, previous_end, previous_name), (off, _, name) in zip(intervals, intervals[1:]):
            if off < previous_end:
                raise ValueError(f"{name} section overlaps {previous_name} section")

        if self.entry >= self.code_size or self.entry % 8:
            raise ValueError("entry point is outside code or not instruction-aligned")
        payload = data[HEADER_SIZE:]
        crc = binascii.crc32(payload) & 0xFFFFFFFF
        if crc != self.payload_crc32:
            raise ValueError(f"payload CRC32 mismatch: expected {self.payload_crc32:08x}, got {crc:08x}")


def pack_orx(*, code: bytes, rodata: bytes, metadata: dict, entry: int,
             permissions: int, flags: int, icon: bytes = b"",
             stack_size: int = 64 * 1024, heap_size: int = 256 * 1024,
             min_os_version: int = 0x00000400) -> bytes:
    if not code or len(code) % 8:
        raise ValueError("ORX VM code must be a non-empty multiple of 8 bytes")
    if entry < 0 or entry >= len(code) or entry % 8:
        raise ValueError("invalid ORX entry point")
    if permissions & ~KNOWN_PERMISSION_MASK:
        raise ValueError(f"unknown ORX permission bits: 0x{permissions & ~KNOWN_PERMISSION_MASK:x}")
    if flags & ~KNOWN_FLAG_MASK:
        raise ValueError(f"unknown ORX flag bits: 0x{flags & ~KNOWN_FLAG_MASK:x}")
    meta = json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    code_off = align(HEADER_SIZE)
    rodata_off = align(code_off + len(code))
    meta_off = align(rodata_off + len(rodata))
    icon_off = align(meta_off + len(meta)) if icon else 0
    file_size = align((icon_off + len(icon)) if icon else (meta_off + len(meta)))
    blob = bytearray(file_size)
    blob[code_off:code_off + len(code)] = code
    blob[rodata_off:rodata_off + len(rodata)] = rodata
    blob[meta_off:meta_off + len(meta)] = meta
    if icon:
        blob[icon_off:icon_off + len(icon)] = icon

    crc = binascii.crc32(blob[HEADER_SIZE:]) & 0xFFFFFFFF
    fields = [
        flags, permissions, entry,
        code_off, len(code), rodata_off, len(rodata),
        meta_off, len(meta), icon_off, len(icon),
        file_size, crc, stack_size, heap_size, min_os_version,
        0, 0, 0, 0, 0,
    ]
    blob[:HEADER_SIZE] = HEADER.pack(
        MAGIC, FORMAT_VERSION, ABI_VERSION, MACHINE_VM64, HEADER_SIZE, *fields
    )
    return bytes(blob)


def load_orx(path: str | Path) -> tuple[OrxHeader, bytes, dict]:
    data = Path(path).read_bytes()
    header = OrxHeader.unpack_from(data)
    header.validate(data)
    meta_raw = data[header.meta_offset:header.meta_offset + header.meta_size]
    meta = json.loads(meta_raw.decode("utf-8")) if meta_raw else {}
    return header, data, meta
