# ORX v1 — Orion Executable Format

ORX is the native application container for UN_Orion. The first machine type is a sandboxed 64-bit register VM. A future native x86_64 machine type can be added without replacing the container format.

All integers are little-endian.

## Header

The header is exactly 96 bytes and begins with `ORX1`.

| Field | Type | Meaning |
|---|---:|---|
| magic | 4 bytes | `ORX1` |
| format_version | u16 | currently 1 |
| abi_version | u16 | Orion App ABI, currently 1 |
| machine | u16 | 1 = Orion VM64 |
| header_size | u16 | 96 |
| flags | u32 | GUI/console flags |
| permissions | u32 | capability bitmask |
| entry | u32 | byte offset inside code section |
| code_offset / code_size | u32/u32 | VM bytecode |
| rodata_offset / rodata_size | u32/u32 | immutable app data |
| meta_offset / meta_size | u32/u32 | UTF-8 JSON metadata |
| icon_offset / icon_size | u32/u32 | optional icon payload |
| file_size | u32 | complete ORX file size |
| payload_crc32 | u32 | CRC32 from byte 96 to EOF |
| stack_size | u32 | requested VM stack budget |
| heap_size | u32 | requested heap budget |
| min_os_version | u32 | minimum encoded Orion version |
| reserved | 5 x u32 | must be zero |

Sections are aligned to 16 bytes.

## Permission bits

- bit 0: `graphics`
- bit 1: `input`
- bit 2: `filesystem_read`
- bit 3: `filesystem_write`
- bit 4: `clipboard`
- bit 5: `network`
- bit 6: `audio`

The OS must deny syscalls outside the declared capability set.

## Orion VM64 instruction encoding

Every instruction is exactly 8 bytes:

`opcode:u8 a:u8 b:u8 c:u8 imm32:i32`

VM64 has eight 64-bit integer registers: `r0` through `r7`, plus a zero flag.

Initial opcodes:

- `nop`
- `halt`
- `movi rN, imm`
- `mov rA, rB`
- `add rA, rB`
- `addi rA, imm`
- `sub rA, rB`
- `cmp rA, rB`
- `jmp label`
- `jz label`
- `jnz label`
- `syscall name [, @rodata_label]`

Initial syscalls: `log`, `exit`, `window`, `clear`, `rect`, `text`, `present`, `event`, `sleep`.

The host ABI passes scalar syscall arguments in registers. String payloads use an immediate offset into the read-only data section.
