# Learnings from Hydrogen

Running list of things learned while designing, implementing, and writing
software for **hydrogen** (H, first machine generation) that should inform a
*future* machine generation's ISA/RTL design — not proposals to retrofit
into hydrogen itself. Per `CLAUDE.md`'s codename convention, generations
aren't a strict version chain, so nothing here is a commitment, just a
backlog to revisit when the next generation's design starts.

- **Flow control has no compare-against-immediate.** `FLOW_CTL` conditions
  (`flow_ctl.md`) only compare two registers — a bound like a loop counter
  needs an extra `imm_set` every time. A future ISA could let `FLOW_CTL` take
  a small immediate directly as one operand.
- **8 general-purpose registers is tight.** `RET_REG`/`STACK_REG` are
  permanently reserved (`calling_convention.h`), and callee-saved regs need
  explicit `PUSH`/`POP` around every nested `CALL` (e.g. `Print`'s 4-deep
  save/restore in `uart.S`). A future ISA should consider more GPRs.
- **Read access to the PC could be useful.** `flow_ctl` keeps the PC
  internal (`flow_ctl.md`), so `CALL`/`RETURN` (`calling_convention.h`) have
  the caller compute the return address itself (`imm_set RET_REG,
  return_label`). Readable PC would also enable position-independent code.
- **Hardware-backed push/pop and call might be worth it.** `PUSH`/`POP`/
  `CALL`/`RETURN` (`calling_convention.h`) are all multi-instruction software
  macros today, invoked constantly. Dedicated hardware (combined
  decrement/increment + load/store, a `CALL` that captures its own return
  address) could cut the overhead.
- **A hardware register-swap instruction might be worth it.** The 3-instruction
  XOR swap (`xor a,a,b; xor b,a,b; xor a,a,b`) works but a single `swap Ra,
  Rb` would collapse it to one.
- **Rotate instructions could be useful.** The ALU has `lshift`/`rshift`
  (`isa.py`) but no `rol`/`ror` — shifted-off bits are lost instead of
  wrapping.
- **A store with an immediate *value* (not just address) could be worth it.**
  `STORE_IMM` (`isa.md`) only makes the address immediate — the value still
  has to be materialized into a register first (`imm_set`, same gap as the
  `FLOW_CTL` point above). A future ISA could let a store take a small
  immediate directly as the data operand, useful for initializing a
  memory-mapped control/status register to a fixed value.
- **Sub-word (byte/halfword) memory access would help.** `load`/`store` only
  address whole 32-bit words (`isa.py`), so byte-granular data (`.ascii`
  strings, lookup tables — see `uart.S`'s `Print`, printf's hex-digit table)
  needs manual `rshift`/`and`/`or` to isolate a byte. A future ISA could add
  byte/halfword-addressed load/store variants.
