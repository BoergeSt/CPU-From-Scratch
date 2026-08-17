# Hydrogen Assembler — v1 Specification

Machine generation: **hydrogen** (H, atomic number 1 — first machine
generation, per the codename convention in `CLAUDE.md`).

Status: **specified — not yet implemented.**

## Overview

Text-based assembly language for Hydrogen. Source is run through the C
preprocessor before assembly, so standard C preprocessor directives
(`#define`, `#include`, `#ifdef`, ...) are available for constants and
conditional inclusion. Mnemonics, opcode encoding, and operand semantics are
defined in `isa.md`; this document covers only the text syntax for writing
them.

## Usage

```
just assemble <file>
```

Preprocesses the file, then assembles it into a raw binary machine-code
image.

## Comments

C-style: `//` for the rest of the line, `/* ... */` for a block. Stripped
during preprocessing.

## Case sensitivity

Mnemonics, directives, and register names are case-insensitive (`add`,
`ADD`, and `Add` are the same instruction) — written lowercase by
convention throughout this document. Labels and preprocessor-defined names
(`#define`) are case-sensitive, matching the C preprocessor underneath,
which can't be anything else.

## Constants and macros

Standard C preprocessor directives apply directly:

```
#define UART_BASE 0x2000
...
load R1, [UART_BASE]
```

## Statement separator

`;` is equivalent to a newline anywhere outside a `"..."` string or `'...'`
character literal -- it splits one physical line into multiple statements,
each parsed exactly as if it were on its own line (its own label(s), its own
instruction or directive):

```
imm_set R1, 1 ; imm_set R2, 2
```

This exists for macros: the C preprocessor always expands a multi-line
`#define` onto a single output line, regardless of how the macro body
itself is split across lines with `\` continuations, so a macro emitting
more than one instruction needs `;` to separate them once expanded. An
empty statement (`;;`, or a label with nothing after the final `;`) is
legal and simply contributes nothing, same as a blank line. A `;` inside a
`.ascii`/`.asciz` string or an `imm_set` character literal (e.g. `';'`) is
left untouched -- there it's a character being packed/encoded, not a
separator. The same holds for `,` inside a character literal (e.g. `','`)
against the comma that separates an instruction's operands.

## Numbers

| Form | Example | Meaning |
|------|---------|---------|
| Decimal | `26` | plain decimal |
| Hex | `0x1A` | same value |
| Binary | `0b11010` | same value |

A bare number is always an immediate/address literal — register operands
are always one of the names below, so no prefix (`#`, `$`, ...) is needed to
disambiguate.

## Character literals

`'<char>'` is a single ASCII character, usable anywhere a plain number is
currently accepted (`imm_set` only, for now):

```
imm_set R2, '\n'
imm_set R3, 'A'
```

Same escapes as `.ascii`/`.asciz` string literals (see Strings below): `\n`
`\t` `\r` `\0` `\a` `\b` `\f` `\v` `\\` `\"` `\'`, and `\xHH` for an
arbitrary byte value.

## Registers

`R0`–`R7`. See `isa.md` for the register file's architectural contract.

## Instructions

General form: `mnemonic dest, operand, operand` — the destination (or, for
branches, the jump target) always comes first. Mnemonics and their meaning
are defined in `isa.md`; only syntax is shown below.

### ALU operations

```
add  R1, R2, R3    ; R1 = R2 + R3
add  R1, R2, 5      ; either operand may be an immediate, not both
not  R1, R2         ; unary -- no third operand
```

### `imm_set`

```
imm_set R1, 0x1234
imm_set R2, '\n'   ; character literal -- see above
```

### Memory access

One mnemonic each for load/store; the operand's form selects the
fixed-address vs. register-indirect encoding:

```
load  R1, [0x1000]     ; fixed address
load  R1, [R2]         ; register-indirect, offset 0
load  R1, [R2 + 8]     ; register-indirect + offset
store [0x1000], R1
store [R2 - 8], R1
```

### Jumps and branches

Condition mnemonics (`l`, `le`, `g`, `ge`, `z`, `nz`, `eq`, `neq`, `always`,
`overflow`, `not_overflow`, `nop`) and which comparison operands each one
uses are defined in `isa.md`. Target first, then the comparison operands the
condition needs — 0, 1, or 2 registers depending on the condition (the same
variable-arity pattern the ALU's `not` already uses):

```
eq     loop, R1, R2   ; relative -- l/le/g/ge/eq/neq take val1 and val2
z      loop, R1        ; z/nz take val1 only
always loop             ; always/overflow/not_overflow/nop take no operands
```

Target forms:

| Syntax | Meaning |
|--------|---------|
| `label` | relative — pc-relative signed offset to `label` |
| `[label]` / `[0x1000]` | absolute — target is the literal word address |
| `R3` | absolute, register-indirect — target is `R3`'s value |

## Labels

`label:` defines a label at the current address. Referenced as:

- a `FLOW_CTL` target: per the table above (bare = relative, `[...]` =
  absolute).
- everywhere else (`imm_set`, `load`/`store`'s fixed-address form):
  resolves directly to its absolute word address — these opcodes have no
  relative mode.

Any number of labels may share a line, and a line's labels may be followed by
an instruction on the same line — all of them resolve to that instruction's
address:

```
loop:                  ; a label alone, on its own line
entry: reset:          ; multiple labels, same address, no instruction
loop: add R0, R0, R0   ; a label immediately ahead of an instruction
```

A label must still be its own whitespace-separated token (`label:`, no space
before the colon) at the start of the line — content after the label(s) is
either more labels or a single instruction, never a label trailing after one.

## Placement

`.org <address>` sets the word address for what follows. Hydrogen's two
fixed vectors (`isa.md`) are placed this way:

```
.org 0x0
    ; exception handler -- must fit before 0x10
.org 0x10
main:
    ...
```

`.word <value>` emits one literal 32-bit word at the current address.

A bare `.org` (no address) switches into **floating placement**: code that
follows isn't pinned to a fixed address — it's placed, in encounter order,
immediately after the highest address any anchored (`.org <address>`)
region in the file used, once the whole file has been scanned. This is
meant for library code that shouldn't have to know or care where it ends
up in memory — write it anywhere in the source (e.g. `#include`d above
`main`) with a bare `.org` in front, and it's placed after everything
anchored, regardless of where it appears textually:

```
.org
    ; library functions -- position doesn't matter, textually or in memory
my_func:
    ...

.org 0x0
    ; exception handler
.org 0x10
main:
    always [my_func]   ; forward reference into floating code -- fine
```

`.org <address>` switches back to anchored placement at that address, so
floating and anchored regions can also interleave more than once in the
same file — every floating region shares one placement, in the order it was
written, regardless of how many times the source switches back to anchored
placement in between.

## Strings

`.ascii "<text>"` and `.asciz "<text>"` emit `<text>` as packed bytes
starting at the current address — `.asciz` additionally appends a
terminating NUL byte, `.ascii` does not. Both pack 4 bytes per word,
little-endian (the string's first byte sits in the word's
least-significant byte), and zero-pad the final word's high end if the
byte count isn't a multiple of 4:

```
msg: .asciz "Hi\n"   ; word 0: 0x000A6948 ('H' 'i' '\n' <NUL>)
```

A label placed right after a string directive resolves to the word
following its packed bytes, same as any other directive. Since memory has
no sub-word load (see below), reading individual characters back out of a
word — e.g. to print each one to the UART — is software's job: shift and
mask the packed word yourself.

Supported escapes inside the string: `\n` `\t` `\r` `\0` `\a` `\b` `\f`
`\v` `\\` `\"` `\'`, and `\xHH` for an arbitrary byte value (e.g. `\xa0`).

## Calling convention

Hydrogen's core has no hardware stack or call/return support (`isa.md`) —
calls, returns, and the stack are a pure software convention built from
ordinary instructions, provided as C preprocessor macros in
`software/examples/calling_convention.h` rather than assembler syntax.

### Register roles

| Register | Role |
|----------|------|
| `R7` | Return address |
| `R6` | Stack pointer |
| `R2`–`R5` | Callee-saved — save/restore before use, if used |
| `R0`, `R1` | Caller-saved — arguments and return values, free to clobber |

No frame-pointer register is reserved. A fixed offset from `R6` is only
valid at a point in a function's body where the net push/pop count since
entry is statically known; a function whose own body pushes/pops a
variable amount before referencing a local (a loop, a conditional push) is
responsible for tracking its own base pointer, if it needs one.

### Stack

Full descending: grows downward, `R6` points at the last pushed word.
`PUSH` decrements `R6` before storing, so `R6` must be initialized to one
past the top of usable memory (`0x1000` for the default 4096-word BRAM,
`bram.md`) before the first `PUSH`, not to the top word itself.

### Macros (`calling_convention.h`)

| Macro | Behavior |
|-------|----------|
| `PUSH(reg)` | Push `reg` onto the stack |
| `POP(reg)` | Pop the top of the stack into `reg` |
| `CALL(func)` | Set `R7` to a return address, jump to `func` |
| `RETURN` | Jump to the address in `R7` |

`CALL` generates a fresh, unique return-address label per invocation (via
`__COUNTER__`), so nested/repeated `CALL`s in the same file don't collide.
Saving `R7` around a nested `CALL` (so it survives the inner call) is the
calling function's own responsibility, same as any other callee-saved
register it uses.

## Not yet supported

- True multi-file linking — every file is still one `#include`d translation
  unit assembled as a whole (see Usage above); floating `.org` (above) only
  solves *placement within* that unit, not assembling/linking separate
  object files.
- Sub-word (byte/halfword) literals outside of `.ascii`/`.asciz` — Hydrogen
  memory is word-addressed with no sub-word load/store yet (`isa.md`).
