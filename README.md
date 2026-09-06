# Orion Executable Tools

Toolchain for building `.orx` applications for **UN_Orion**.

ORX is not just a renamed ELF file. ORX v1 is a small application container with its own header, Orion App ABI version, capability permissions, VM bytecode, immutable data, metadata, optional resources, and CRC32 integrity check.

## What works now

- `orx new` — create an application project
- `orx build` — assemble + package a `.orx`
- `orx inspect` — decode header/metadata/permissions
- `orx check` — validate bounds + ABI + CRC32
- `orx run` — run the app in a host-side reference VM
- tiny `oasm` assembler with labels, jumps, registers, rodata and syscalls
- examples and tests

Only Python 3.11+ is required.

## Quick start

```bash
python3 orx.py new "My App"
cd my-app
python3 ../orx.py build .
python3 ../orx.py inspect build/My_App.orx
python3 ../orx.py run build/My_App.orx
```

Build the included example:

```bash
python3 orx.py build examples/hello -o /tmp/hello.orx
python3 orx.py check /tmp/hello.orx
python3 orx.py run /tmp/hello.orx
```

## Project format

`app.toml`:

```toml
name = "Hello Orion"
id = "dev.orion.hello"
version = "0.1.0"
abi = 1
source = "main.oasm"
type = "gui"
permissions = ["graphics", "input"]
```

`main.oasm`:

```asm
.entry main
.section code
main:
    movi r0, 640
    movi r1, 360
    syscall window, @title
    syscall log, @message
    halt

.section rodata
title:
    .string "My ORX App"
message:
    .string "Hello from ORX"
```

See [`docs/ORX_FORMAT.md`](docs/ORX_FORMAT.md) for the binary format and VM ABI.

## Design direction

The VM machine type is intentional: it gives UN_Orion a small sandboxed application target before ring-3 processes and a native loader are complete. The ORX container is designed so a future native x86_64 machine type can coexist with VM64 apps.
