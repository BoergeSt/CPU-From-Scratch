#!/usr/bin/env python3
"""Hydrogen assembler CLI. Syntax reference: machines/hydrogen/docs/assembler.md.

Expects already-preprocessed source (see `just assemble`, which pipes the
source through `gcc -E -P` first) -- this script itself does no macro
expansion.
"""

import argparse
import logging
import sys
from dataclasses import dataclass

import isa

logger = logging.getLogger(__name__)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Assemble preprocessed Hydrogen source into a raw binary "
        "machine-code image."
    )
    parser.add_argument("input", help="source file to assemble, or '-' for stdin")
    parser.add_argument(
        "-o", "--output", required=True, help="path to write the assembled binary image to"
    )
    parser.add_argument(
        "-m",
        "--map",
        help="path to write a symbol map file to (label -> word address, sorted by address)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="increase log verbosity (-v for info, -vv for debug)",
    )
    return parser.parse_args(argv)


def setup_logging(verbosity):
    level = {0: logging.WARNING, 1: logging.INFO}.get(verbosity, logging.DEBUG)
    logging.basicConfig(stream=sys.stderr, level=level, format="%(levelname)s: %(message)s")
    logging.getLogger("isa").setLevel(level)


def read_source(path):
    if path == "-":
        return sys.stdin.read()
    with open(path) as f:
        return f.read()


# Placeholder base for addresses assigned during a floating `.org` region
# (see tokenize()) -- comfortably above any real Hydrogen address so real and
# placeholder addresses can never collide before the final remap.
FLOATING_BASE = 1 << 30


@dataclass
class Line:
    address: int
    text: str
    # Decoded byte payload for a `.ascii`/`.asciz` line, spanning
    # ceil(len(data) / 4) words from `address`. None for every other line
    # (`.word`, an instruction), which occupies exactly one word.
    data: bytes | None = None


def consume_labels(line, address, labels):
    """Strips and registers any number of leading `label:` tokens from `line`,
    all resolving to `address`, and returns whatever remains (possibly empty
    -- a label-only line -- or another label, a directive, or an
    instruction). Returns `None` on a malformed/duplicate/colliding label
    (error already logged).
    """
    while line:
        parts = line.split(None, 1)
        first = parts[0]
        if ":" not in first:
            break
        if not first.endswith(":"):
            logger.error("Invalid label definition: %s", line)
            return None
        label = first[:-1]
        if not label:
            logger.error("Empty label definition: %s", line)
            return None
        if label in labels:
            logger.error("Duplicate label definition: %s", label)
            return None
        if label in isa.registers:
            logger.error("Label name collides with a register name: %s", label)
            return None
        labels[label] = address
        line = parts[1].strip() if len(parts) > 1 else ""
    return line


def _scan_quoted(text):
    """Yields `(char, quoted)` for each character in `text`, where `quoted`
    is True while inside a "..." or '...' literal (either quote style,
    tracking `\\`-escapes so an escaped quote doesn't end the literal early).
    Shared by `split_statements` and `split_args` so both treat `.ascii`/
    `.asciz` string literals and `imm_set` character literals as opaque the
    same way.
    """
    quote = None
    escaped = False
    for ch in text:
        if quote:
            yield ch, True
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            yield ch, True
        else:
            yield ch, False


def split_statements(source):
    """Replaces every ';' outside a quoted literal with a newline, so ';'
    works as a statement separator anywhere a real newline would -- chiefly
    for macros (`#define`) that expand multiple instructions onto one output
    line, which the C preprocessor always does regardless of how the macro
    body's own definition is split across lines. A ';' inside a
    `.ascii`/`.asciz` string or an `imm_set` character literal is left
    untouched, since there it's just a character being packed/encoded, not a
    separator.
    """
    return "".join(
        "\n" if ch == ";" and not quoted else ch for ch, quoted in _scan_quoted(source)
    )


def split_args(args_str):
    """Splits an operand string on top-level ',' -- like `str.split(",")`,
    but a ',' inside a quoted literal (e.g. the `,` in a `','` character
    literal) is left untouched, since there it's operand content, not a
    separator.
    """
    args = []
    current = []
    for ch, quoted in _scan_quoted(args_str):
        if ch == "," and not quoted:
            args.append("".join(current))
            current = []
        else:
            current.append(ch)
    args.append("".join(current))
    return args


def tokenize(source):
    """Splits source into (Line(address, text[, data]), labels).

    `.org <address>` moves the address cursor to an anchored address; a bare
    `.org` (no operand) instead switches into *floating* placement -- lines
    that follow aren't assigned a real address yet, only a placeholder one
    that preserves their relative order, and get remapped at the end of this
    function to sit, in encounter order, immediately after the highest
    address any anchored region in the file used. This lets library code
    (`.org` with no operand, then its definitions) live anywhere in the
    source -- e.g. `#include`d above `main` -- without colliding with
    anchored placement elsewhere in the file. Any number of leading `label:`
    tokens on a line (alone, or ahead of another label/directive/instruction
    on the same line) resolve to the address of whatever follows them; every
    remaining non-blank line becomes a `Line` at the current address. A
    `.ascii`/`.asciz` line carries its decoded bytes in `Line.data` and
    advances the address by however many words that packs into; every other
    line advances by exactly one word. Returns (None, None) on a malformed
    directive/label (error already logged).
    """
    lines = []
    labels = {}
    address = 0x10
    floating_address = FLOATING_BASE
    floating = False
    max_anchored_end = 0x10 - 1
    for raw_line in split_statements(source).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        cursor = floating_address if floating else address
        line = consume_labels(line, cursor, labels)
        if line is None:
            return None, None
        if not line:
            continue
        if line.lower().startswith(".org"):
            split_line = line.split()
            if len(split_line) == 1:
                floating = True
                continue
            if len(split_line) != 2:
                logger.error("Invalid .org directive: %s", line)
                return None, None
            offset = isa.parse_int(split_line[1])
            if offset is None:
                logger.error("Invalid .org offset: %s", line)
                return None, None
            address = offset
            floating = False
            continue
        directive = line.split(None, 1)[0].lower()
        if directive in (".ascii", ".asciz"):
            split_line = line.split(None, 1)
            operand = split_line[1].strip() if len(split_line) == 2 else ""
            data, remainder = isa.parse_string_literal(operand)
            if data is None or remainder:
                logger.error("Invalid %s directive: %s", directive, line)
                return None, None
            if directive == ".asciz":
                data += b"\x00"
            word_count = (len(data) + 3) // 4
        else:
            data = None
            word_count = 1
        lines.append(Line(address=cursor, text=line, data=data))
        if floating:
            floating_address += word_count
        else:
            address += word_count
            max_anchored_end = max(max_anchored_end, address - 1)

    floating_offset = max_anchored_end + 1 - FLOATING_BASE
    for line in lines:
        if line.address >= FLOATING_BASE:
            line.address += floating_offset
    for label, addr in labels.items():
        if addr >= FLOATING_BASE:
            labels[label] = addr + floating_offset
    return lines, labels


def encode_line(line, labels):
    text = line.text
    if text.lower().startswith(".word"):
        parts = text.split(None, 1)
        if len(parts) != 2:
            logger.error("Invalid .word directive: %s", text)
            return None
        value = isa.parse_int(parts[1].strip())
        if value is None:
            logger.error("Invalid .word value: %s", text)
            return None
        if value >= 2**32 or value < -(2**31):
            logger.error("Value out of range for .word directive: %s", text)
            return None
        return isa.to_twos_complement(value, 32)

    parts = text.split(None, 1)
    opcode = parts[0].lower()
    args_str = parts[1].strip() if len(parts) > 1 else ""
    args = [arg.strip() for arg in split_args(args_str)] if args_str else []
    if opcode not in isa.INSTRUCTIONS:
        logger.error("Unknown opcode: %s", opcode)
        return None
    bytecode = isa.encode_instruction(opcode, args, line.address, labels)
    if bytecode is None:
        logger.error("Failed to generate bytecode for line: %s", text)
        return None
    return bytecode


def encode_lines(lines, labels):
    """Encodes every Line into its word(s), keyed by address.

    Two words resolving to the same address (overlapping `.org` ranges, or a
    multi-word `.ascii`/`.asciz` payload running into a following line) is
    detected here directly, as a dict-key collision, rather than as a
    separate range-overlap check.
    """
    words = {}
    for line in lines:
        if line.data is not None:
            word_list = isa.pack_bytes_little_endian(line.data)
        else:
            bytecode = encode_line(line, labels)
            if bytecode is None:
                return None
            word_list = [bytecode]
        for offset, word in enumerate(word_list):
            address = line.address + offset
            if address in words:
                logger.error(
                    "Address collision at word 0x%X (overlapping .org ranges): %s",
                    address,
                    line.text,
                )
                return None
            logger.debug("0x%X: %s -> 0x%08X", address, line.text, word)
            words[address] = word
    return words


def pack_image(words):
    if not words:
        return bytearray()
    lo, hi = min(words), max(words)
    image = bytearray()
    for address in range(lo, hi + 1):
        image += words.get(address, 0).to_bytes(4, byteorder="little")
    return image


def format_map_file(labels):
    """Renders a symbol map as text, one `address  label` line per symbol,
    sorted by address then name.
    """
    lines = [
        f"0x{address:08X}  {label}"
        for label, address in sorted(labels.items(), key=lambda item: (item[1], item[0]))
    ]
    return "".join(f"{line}\n" for line in lines)


def lex_source(source):
    lines, labels = tokenize(source)
    if lines is None:
        return None, None
    logger.debug("Tokenized into %d lines and %d labels", len(lines), len(labels))
    logger.debug("Labels: %s", labels)

    words = encode_lines(lines, labels)
    if words is None:
        return None, None

    return pack_image(words), labels


def main(argv=None):
    args = parse_args(argv)
    setup_logging(args.verbose)

    logger.debug("reading source from %s", "stdin" if args.input == "-" else args.input)
    try:
        source = read_source(args.input)
    except OSError as exc:
        logger.error("could not read %s: %s", args.input, exc)
        return 1

    logger.info("read %d bytes", len(source))

    image, labels = lex_source(source)
    if image is None:
        return 1

    if args.output == "-":
        sys.stdout.buffer.write(image)
    else:
        with open(args.output, "wb") as f:
            f.write(image)

    if args.map:
        with open(args.map, "w") as f:
            f.write(format_map_file(labels))
        logger.info("wrote %d symbols to %s", len(labels), args.map)

    return 0


if __name__ == "__main__":
    sys.exit(main())
