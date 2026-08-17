import logging
from enum import Enum

logger = logging.getLogger(__name__)

registers = {f"R{i}": i for i in range(8)}
registers.update({name.lower(): idx for name, idx in registers.items()})


class InstructionClass(Enum):
    IMM_SET = 0x1
    FLOW_CTL = 0x2
    LOAD_IMM = 0x3
    STORE_IMM = 0x4
    LOAD = 0x5
    STORE = 0x6
    ALU = 0x7


class AluOp(Enum):
    ADD = 0x0
    SUB = 0x1
    MUL = 0x2
    MULH = 0x3
    LSHIFT = 0x4
    RSHIFT = 0x5
    AND = 0x6
    OR = 0x7
    XOR = 0x8
    NOT = 0x9
    NAND = 0xA
    NOR = 0xB


class FlowCtlOp(Enum):
    NOP = 0x0
    LESS = 0x1
    LESS_EQUAL = 0x2
    GREATER = 0x3
    GREATER_EQUAL = 0x4
    ZERO = 0x5
    NOT_ZERO = 0x6
    EQUAL = 0x7
    NOT_EQUAL = 0x8
    ALWAYS = 0x9
    OVERFLOW = 0xA
    NOT_OVERFLOW = 0xB


# Bit layout per instruction class: field name -> (bit offset, width). Mirrors
# isa_pkg.sv's structs -- the single source of truth for field positions, so a
# layout change touches this table and this table alone. Values passed to
# pack_fields() must already be the unsigned bit pattern to place at that
# field (signed fields are the caller's responsibility to two's-complement-
# encode first, e.g. via to_twos_complement()).
FIELD_LAYOUT = {
    InstructionClass.IMM_SET: {
        "dest": (25, 3),
        "imm": (0, 25),
    },
    InstructionClass.LOAD_IMM: {
        "dest": (25, 3),
        "addr": (0, 25),
    },
    InstructionClass.STORE_IMM: {
        "addr": (3, 25),
        "src": (0, 3),
    },
    InstructionClass.LOAD: {
        "dest": (25, 3),
        "offset": (3, 22),
        "base": (0, 3),
    },
    InstructionClass.STORE: {
        "offset": (6, 22),
        "src": (3, 3),
        "base": (0, 3),
    },
    InstructionClass.ALU: {
        "dest": (25, 3),
        "alu_op": (21, 4),
        "is_imm_src1": (20, 1),
        "is_imm_src2": (19, 1),
        "imm": (6, 13),
        "src2_addr": (3, 3),
        "src1_addr": (0, 3),
    },
    InstructionClass.FLOW_CTL: {
        "r": (27, 1),
        "i": (26, 1),
        "op": (22, 4),
        "jump_to_addr": (6, 3),  # i=0 (register-indirect) mode
        "imm": (6, 16),  # i=1 (immediate) mode -- same offset, different width
        "val2_addr": (3, 3),
        "val1_addr": (0, 3),
    },
}


def to_twos_complement(x, bits):
    return x & ((1 << bits) - 1)


def check_signed_limit(value, bits):
    return -(2 ** (bits - 1)) <= value < 2 ** (bits - 1)


def parse_int(value_str):
    try:
        int_value = int(value_str, 0)
    except ValueError:
        return None
    return int_value


# `\xHH` (arbitrary byte) is handled separately below; these are the named
# single-character escapes, C's common subset.
_STRING_ESCAPES = {
    "n": 0x0A,
    "t": 0x09,
    "r": 0x0D,
    "0": 0x00,
    "a": 0x07,
    "b": 0x08,
    "f": 0x0C,
    "v": 0x0B,
    "\\": 0x5C,
    '"': 0x22,
    "'": 0x27,
}


def parse_string_literal(text):
    """Parses a double-quoted string literal starting at `text[0]` (which
    must be '"'), with C-style escapes (\\n \\t \\r \\0 \\a \\b \\f \\v \\\\
    \\" \\' and \\xHH for an arbitrary byte value). Returns `(data,
    remainder)` -- the decoded bytes, and whatever trailing text follows the
    closing quote (stripped) -- or `(None, None)` if `text` isn't a valid,
    terminated string literal.
    """
    if not text or text[0] != '"':
        return None, None
    data = bytearray()
    i = 1
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"':
            return bytes(data), text[i + 1 :].strip()
        if c == "\\":
            if i + 1 >= n:
                return None, None
            esc = text[i + 1]
            if esc == "x":
                hex_digits = text[i + 2 : i + 4]
                if len(hex_digits) != 2 or any(
                    ch not in "0123456789abcdefABCDEF" for ch in hex_digits
                ):
                    return None, None
                data.append(int(hex_digits, 16))
                i += 4
                continue
            if esc not in _STRING_ESCAPES:
                return None, None
            data.append(_STRING_ESCAPES[esc])
            i += 2
            continue
        if ord(c) > 0xFF:
            return None, None
        data.append(ord(c))
        i += 1
    return None, None


def parse_char_literal(text):
    """Parses a single-quoted character literal (e.g. `'a'`, `'\\n'`,
    `'\\x41'`), using the same escapes as `parse_string_literal`. Returns the
    character's byte value, or `None` if `text` isn't a valid, fully-consumed
    char literal. An unescaped `'` or `\\` as the sole body character is
    rejected as ambiguous -- both must be written via their escape.
    """
    if len(text) < 3 or text[0] != "'" or text[-1] != "'":
        return None
    body = text[1:-1]
    if len(body) == 1:
        c = body
        if c in ("'", "\\") or ord(c) > 0xFF:
            return None
        return ord(c)
    if not body or body[0] != "\\":
        return None
    esc = body[1:]
    if len(esc) == 1:
        return _STRING_ESCAPES.get(esc)
    if len(esc) == 3 and esc[0] == "x":
        hex_digits = esc[1:]
        if any(ch not in "0123456789abcdefABCDEF" for ch in hex_digits):
            return None
        return int(hex_digits, 16)
    return None


def pack_bytes_little_endian(data):
    """Packs `data` into 32-bit words, 4 bytes per word, little-endian (a
    word's first byte sits in its least-significant byte position). The
    final word is zero-padded on its high end if `len(data)` isn't a
    multiple of 4.
    """
    return [
        int.from_bytes(data[i : i + 4].ljust(4, b"\x00"), byteorder="little")
        for i in range(0, len(data), 4)
    ]


def pack_fields(instr_class, values):
    layout = FIELD_LAYOUT[instr_class]
    word = instr_class.value << 28
    for name, value in values.items():
        offset, width = layout[name]
        if value < 0 or value >= (1 << width):
            raise ValueError(
                f"value {value} out of range for field '{name}' ({width} bits)"
            )
        word |= value << offset
    return word


def encode_imm_set(dest, imm, line_number, labels):
    if dest not in registers:
        logger.error(f"Invalid destination register for imm_set: {dest}")
        return None
    if imm.startswith("'"):
        value = parse_char_literal(imm)
        if value is None:
            logger.error(f"Invalid character literal for imm_set: {imm}")
            return None
    else:
        value = labels.get(imm)
        if value is None:
            value = parse_int(imm)
        if value is None:
            logger.error(f"Invalid immediate value for imm_set: {imm}")
            return None
    if value < 0 or value > 0x1FFFFFF:
        logger.error(f"Immediate value out of range for imm_set: {imm}")
        return None
    return pack_fields(
        InstructionClass.IMM_SET, {"dest": registers[dest], "imm": value}
    )


def encode_alu(alu_op, dest, src1, src2, line_number, labels):
    if dest not in registers:
        logger.error(f"Invalid destination register for ALU operation: {dest}")
        return None
    is_src1_imm = src1 not in registers
    is_src2_imm = src2 not in registers
    if is_src1_imm and is_src2_imm:
        logger.error(
            f"Both sources cannot be immediate values for ALU operation: {src1}, {src2}"
        )
        return None
    values = {
        "dest": registers[dest],
        "alu_op": alu_op.value,
        "is_imm_src1": int(is_src1_imm),
        "is_imm_src2": int(is_src2_imm),
    }
    if is_src1_imm or is_src2_imm:
        imm_token = src1 if is_src1_imm else src2
        imm = parse_int(imm_token)
        if imm is None:
            logger.error(f"Invalid immediate value for ALU operation: {imm_token}")
            return None
        if imm < 0 or imm > 2**13 - 1:
            logger.error(f"Immediate value out of range for ALU operation: {imm}")
            return None
        values["imm"] = imm
    values["src1_addr"] = registers[src1] if not is_src1_imm else 0
    values["src2_addr"] = registers[src2] if not is_src2_imm else 0
    return pack_fields(InstructionClass.ALU, values)


def parse_flow_target(dest, line_number, labels):
    if dest[0] == "[" and dest[-1] == "]":
        dest = dest[1:-1].strip()
        relative = False
    elif dest in registers:
        relative = False
    else:
        relative = True
    fields = {"r": int(relative)}
    if dest in registers:
        fields["i"] = 0
        fields["jump_to_addr"] = registers[dest]
        return fields
    fields["i"] = 1
    if dest in labels:
        target = labels[dest]
    else:
        target = parse_int(dest)
        if target is None:
            logger.error(f"Invalid flow-control target: {dest}")
            return None
    if relative:
        offset = target - line_number if dest in labels else target
        if not check_signed_limit(offset, 16):
            logger.error(f"Relative jump to {dest} is out of range: {offset}")
            return None
        fields["imm"] = to_twos_complement(offset, 16)
    else:
        if target < 0 or target > 2**16 - 1:
            logger.error(f"Absolute jump to {dest} is out of range: {target}")
            return None
        fields["imm"] = target
    return fields


def encode_flowctl(flow_op, target, val1, val2, line_number, labels):
    target_fields = parse_flow_target(target, line_number, labels)
    if target_fields is None:
        return None
    if val1 not in registers:
        logger.error(
            f"Invalid source register for {flow_op.name.lower()} flow-control instruction: {val1}"
        )
        return None
    if val2 not in registers:
        logger.error(
            f"Invalid source register for {flow_op.name.lower()} flow-control instruction: {val2}"
        )
        return None
    values = {
        "op": flow_op.value,
        "val1_addr": registers[val1],
        "val2_addr": registers[val2],
    }
    values.update(target_fields)
    return pack_fields(InstructionClass.FLOW_CTL, values)


def parse_memory_operand(address, labels):
    """Parses a `[...]` load/store address expression.

    Returns `("immediate", addr)` for a fixed address (literal or label), or
    `("indirect", base_reg, offset)` for register+offset addressing. Returns
    `None` (with an error already logged) if `address` is malformed.
    """
    if address[0] != "[" or address[-1] != "]":
        logger.error(f"Address must be absolute: {address}")
        return None
    address = address[1:-1].strip()
    address_int = parse_int(address)
    if address_int is None and address in labels:
        address_int = labels[address]
    if address_int is not None:
        if address_int < 0 or address_int >= 2**25:
            logger.error(f"Address out of range: {address}")
            return None
        return ("immediate", address_int)
    if "+" in address:
        operands = address.split("+")
        negate = False
    elif "-" in address:
        operands = address.split("-")
        negate = True
    else:
        operands = [address, "0"]
        negate = False
    if len(operands) != 2:
        logger.error(f"Unexpected address expression: {address}")
        return None
    operands = [operand.strip() for operand in operands]
    if operands[0] not in registers:
        logger.error(f"Invalid base register: {address}")
        return None
    base_reg = registers[operands[0]]
    offset = parse_int(operands[1])
    if offset is None:
        logger.error(f"Invalid offset: {address}")
        return None
    if negate:
        offset = -offset
    if offset > 2**21 - 1 or offset < -(2**21):
        logger.error(f"Offset is out of bounds: {address}")
        return None
    return ("indirect", base_reg, offset)


def encode_load(dest, address, line_number, labels):
    if dest not in registers:
        logger.error(f"Load destination invalid: {dest}")
        return None
    operand = parse_memory_operand(address, labels)
    if operand is None:
        return None
    if operand[0] == "immediate":
        _, addr = operand
        return pack_fields(
            InstructionClass.LOAD_IMM, {"dest": registers[dest], "addr": addr}
        )
    _, base_reg, offset = operand
    return pack_fields(
        InstructionClass.LOAD,
        {
            "dest": registers[dest],
            "offset": to_twos_complement(offset, 22),
            "base": base_reg,
        },
    )


def encode_store(address, src, line_number, labels):
    if src not in registers:
        logger.error(f"Store source invalid: {src}")
        return None
    operand = parse_memory_operand(address, labels)
    if operand is None:
        return None
    if operand[0] == "immediate":
        _, addr = operand
        return pack_fields(
            InstructionClass.STORE_IMM, {"addr": addr, "src": registers[src]}
        )
    _, base_reg, offset = operand
    return pack_fields(
        InstructionClass.STORE,
        {
            "offset": to_twos_complement(offset, 22),
            "src": registers[src],
            "base": base_reg,
        },
    )


# Declarative mnemonic table: mnemonic -> (family encoder, fixed kwargs,
# user-supplied operand names in source order, defaults for operands the
# mnemonic doesn't expose). Adding a mnemonic for an existing instruction
# family (a new ALU op, a new FLOW_CTL condition) is a one-line entry here --
# no new function needed. A genuinely new instruction family (e.g. a future
# DIV/MOD or sub-word load/store opcode) needs a new encode_* function, same
# as it needs a new RTL module on the hardware side.
INSTRUCTIONS = {
    "imm_set": (encode_imm_set, {}, ["dest", "imm"], {}),
    "nop": (
        encode_flowctl,
        {"flow_op": FlowCtlOp.NOP},
        [],
        {"target": "R0", "val1": "R0", "val2": "R0"},
    ),
    "always": (
        encode_flowctl,
        {"flow_op": FlowCtlOp.ALWAYS},
        ["target"],
        {"val1": "R0", "val2": "R0"},
    ),
    "l": (encode_flowctl, {"flow_op": FlowCtlOp.LESS}, ["target", "val1", "val2"], {}),
    "le": (
        encode_flowctl,
        {"flow_op": FlowCtlOp.LESS_EQUAL},
        ["target", "val1", "val2"],
        {},
    ),
    "g": (
        encode_flowctl,
        {"flow_op": FlowCtlOp.GREATER},
        ["target", "val1", "val2"],
        {},
    ),
    "ge": (
        encode_flowctl,
        {"flow_op": FlowCtlOp.GREATER_EQUAL},
        ["target", "val1", "val2"],
        {},
    ),
    "z": (
        encode_flowctl,
        {"flow_op": FlowCtlOp.ZERO},
        ["target", "val1"],
        {"val2": "R0"},
    ),
    "nz": (
        encode_flowctl,
        {"flow_op": FlowCtlOp.NOT_ZERO},
        ["target", "val1"],
        {"val2": "R0"},
    ),
    "eq": (
        encode_flowctl,
        {"flow_op": FlowCtlOp.EQUAL},
        ["target", "val1", "val2"],
        {},
    ),
    "neq": (
        encode_flowctl,
        {"flow_op": FlowCtlOp.NOT_EQUAL},
        ["target", "val1", "val2"],
        {},
    ),
    "overflow": (
        encode_flowctl,
        {"flow_op": FlowCtlOp.OVERFLOW},
        ["target"],
        {"val1": "R0", "val2": "R0"},
    ),
    "not_overflow": (
        encode_flowctl,
        {"flow_op": FlowCtlOp.NOT_OVERFLOW},
        ["target"],
        {"val1": "R0", "val2": "R0"},
    ),
    "add": (encode_alu, {"alu_op": AluOp.ADD}, ["dest", "src1", "src2"], {}),
    "sub": (encode_alu, {"alu_op": AluOp.SUB}, ["dest", "src1", "src2"], {}),
    "mul": (encode_alu, {"alu_op": AluOp.MUL}, ["dest", "src1", "src2"], {}),
    "mulh": (encode_alu, {"alu_op": AluOp.MULH}, ["dest", "src1", "src2"], {}),
    "lshift": (encode_alu, {"alu_op": AluOp.LSHIFT}, ["dest", "src1", "src2"], {}),
    "rshift": (encode_alu, {"alu_op": AluOp.RSHIFT}, ["dest", "src1", "src2"], {}),
    "and": (encode_alu, {"alu_op": AluOp.AND}, ["dest", "src1", "src2"], {}),
    "or": (encode_alu, {"alu_op": AluOp.OR}, ["dest", "src1", "src2"], {}),
    "xor": (encode_alu, {"alu_op": AluOp.XOR}, ["dest", "src1", "src2"], {}),
    "not": (encode_alu, {"alu_op": AluOp.NOT}, ["dest", "src1"], {"src2": "R0"}),
    "nand": (encode_alu, {"alu_op": AluOp.NAND}, ["dest", "src1", "src2"], {}),
    "nor": (encode_alu, {"alu_op": AluOp.NOR}, ["dest", "src1", "src2"], {}),
    "load": (encode_load, {}, ["dest", "address"], {}),
    "store": (encode_store, {}, ["address", "src"], {}),
}


def encode_instruction(mnemonic, args, line_number, labels):
    encoder, fixed, operand_names, defaults = INSTRUCTIONS[mnemonic]
    if len(args) != len(operand_names):
        logger.error(
            f"'{mnemonic}' expects {len(operand_names)} operand(s), got {len(args)}: {args}"
        )
        return None
    operands = dict(zip(operand_names, args))
    operands.update(defaults)
    try:
        return encoder(line_number=line_number, labels=labels, **fixed, **operands)
    except IndexError as exc:
        logger.error(f"Malformed operand for '{mnemonic}': {exc}")
        return None
