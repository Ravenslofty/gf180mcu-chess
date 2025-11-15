# SPDX-FileCopyrightText: © 2025 Project Template Contributors
# SPDX-License-Identifier: Apache-2.0

from enum import Enum
import os
import random
import logging
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Timer, Edge, RisingEdge, FallingEdge, ClockCycles
from cocotb_tools.runner import get_runner

class Command(Enum):
    SET_WTM        = 0b0000_0000
    SET_SS1_VALID  = 0b0000_0100
    SET_SS2_VALID  = 0b0000_0110
    SET_MASK_MODE  = 0b0000_1000
    SET_STATE_MODE = 0b0001_0000
    SET_WRITE_BUS  = 0b0010_0000

    GET_WTM        = 0b0100_0000
    GET_STATUS     = 0b0100_0010
    GET_SS1_VALID  = 0b0100_0100
    GET_SS1        = 0b0100_0101
    GET_SS2_VALID  = 0b0100_0110
    GET_SS2        = 0b0100_0111
    GET_MASK_MODE  = 0b0100_1000
    GET_STATE_MODE = 0b0101_0000
    GET_WRITE_BUS  = 0b0110_0000

    SET_SS1        = 0b1000_0000
    SET_SS2        = 0b1100_0000

class Colour(Enum):
    WHITE = 0
    BLACK = 1

class MaskMode(Enum):
    EAV_EAA   = 0b00
    DV_EAA    = 0b01
    DA        = 0b10
    NO_CHANGE = 0b11

class StateMode(Enum):
    FV   = 0b000
    FP   = 0b001
    FA   = 0b010
    IDLE = 0b100
    DAAA = 0b101
    W    = 0b110
    WD   = 0b111

sim = os.getenv("SIM", "verilator")
pdk_root = os.getenv("PDK_ROOT", Path("~/.ciel").expanduser())
pdk = os.getenv("PDK", "gf180mcuD")
scl = os.getenv("SCL", "gf180mcu_fd_sc_mcu7t5v0")
gl = os.getenv("GL", False)

hdl_toplevel = "chip_core"

def get_packed_field(handle, start, stop=None):
    full_value = handle.value
    if stop is None:
        return full_value[start]
    else:
        return full_value[start:stop]

def set_packed_field(handle, start, stop=None, *, value):
    full_value = handle.value
    if stop is None:
        full_value[start] = value
    else:
        full_value[start:stop] = value
    handle.value = full_value

@cocotb.test()
async def test_project(dut):
    moves = 0

    WKNIGHT = 1
    WBISHOP = 2
    WROOK = 3
    WQUEEN = 4
    WKING = 5

    TCK = 2
    TMS = 3
    TDO = 4
    TDI = 5

    async def jtag_tck(tms=None, tdi=None):
        tms = tms or 0
        tdi = tdi or 0

        set_packed_field(dut.bidir_in, TDI, TCK, value=0 | (tms << 1) | (tdi << 3))
        await ClockCycles(dut.clk60, 8)
        set_packed_field(dut.bidir_in, TDI, TCK, value=1 | (tms << 1) | (tdi << 3))
        tdo = int(dut.bidir_out.value[TDO])
        await ClockCycles(dut.clk60, 8)
        set_packed_field(dut.bidir_in, TDI, TCK, value=0 | (tms << 1) | (tdi << 3))

        #print(f"tdi={tdi} tdo={tdo}")
        return tdo

    async def transfer_jtag_ir(ir: int):
        #print(f"# IR = {ir:3}")
        set_packed_field(dut.bidir_in, TDI, value=0)
        
        #print("# Test-Logic-Reset")

        # Test-Logic-Reset -> Run-Test/Idle: TMS = 0
        await jtag_tck(tms=0)

        #print("# Run-Test/Idle")
        
        # Run-Test/Idle -> Select-DR-Scan: TMS = 1
        await jtag_tck(tms=1)

        #print("# Select-DR-Scan")

        # Select-DR-Scan -> Select-IR-Scan: TMS = 1
        await jtag_tck(tms=1)

        #print("# Select-IR-Scan")

        # Select-IR-Scan -> Capture-IR: TMS = 0
        await jtag_tck(tms=0)

        #print("# Capture-IR")

        # Capture-IR -> Shift-IR: TMS = 0
        await jtag_tck(tms=0)

        #print("# Shift-IR")

        # Shift-IR (x7):        TMS = 0
        # Shift-IR -> Exit1-IR: TMS = 1
        value_out = 0
        for x in range(8):
            bit = await jtag_tck(tms=0 if x != 7 else 1, tdi=ir&1)
            ir >>= 1
            value_out |= bit << x

        #print("# Exit1-IR")

        # Exit1-IR -> Update-IR: TMS = 1
        await jtag_tck(tms=1)

        #print("# Update-IR")

        # Update-IR -> Run-Test/Idle
        await jtag_tck(tms=0)

        #print("# Run-Test/Idle")

        #print(f"#   => {value_out:3}")

        return value_out

    async def transfer_jtag_dr(dr: int, cycles=8):
        #print(f"# DR = {dr:3}; cycles={cycles}")

        set_packed_field(dut.bidir_in, TDI, value=0)
        
        # Test-Logic-Reset -> Run-Test/Idle: TMS = 0
        await jtag_tck(tms=0)

        # Run-Test/Idle -> Select-DR-Scan: TMS = 1
        await jtag_tck(tms=1)

        # Select-DR-Scan -> Capture-DR: TMS = 0
        await jtag_tck(tms=0)

        # Capture-DR -> Shift-DR: TMS = 0
        await jtag_tck(tms=0)

        # Shift-DR: TMS = 0
        # Shift-DR -> Exit1-DR: TMS = 1
        value_out = 0
        for x in range(cycles):
            bit = await jtag_tck(tms=0 if x != cycles-1 else 1, tdi=dr&1)
            dr >>= 1
            value_out |= bit << x

        # Exit1-DR -> Update-DR: TMS = 1
        await jtag_tck(tms=1)

        # Update-DR -> Run-Test/Idle: TMS = 0
        await jtag_tck(tms=0)

        #print(f"#   => {value_out:3}")

        return value_out

    async def set_state_mode(state_mode: StateMode):
        #print(f"SET-STATE-MODE {state_mode}")
        await transfer_jtag_ir(65)
        await transfer_jtag_dr(state_mode.value, cycles=3)

    async def set_mask_mode(mask_mode: MaskMode):
        #print(f"SET-MASK-MODE {mask_mode}")
        await transfer_jtag_ir(66)
        await transfer_jtag_dr(mask_mode.value, cycles=2)

    async def set_wtm(colour: Colour):
        #print(f"SET-WTM {colour}")
        await transfer_jtag_ir(67)
        await transfer_jtag_dr(colour.value, cycles=1)

    async def set_write_bus(write_bus: int):
        #print(f"SET-WRITE-BUS {write_bus}")
        await transfer_jtag_ir(68)
        await transfer_jtag_dr(write_bus, cycles=4)

    async def set_ss1(square: int):
        #print(f"SET-SS1 {square}")
        await transfer_jtag_ir(69)
        await transfer_jtag_dr(0x40 | square, cycles=7)

    async def set_ss2(square: int):
        #print(f"SET-SS2 {square}")
        await transfer_jtag_ir(70)
        await transfer_jtag_dr(0x40 | square, cycles=7)

    async def get_status():
        #print(f"GET-STATUS")
        await transfer_jtag_ir(71)
        return (await transfer_jtag_dr(0))

    async def find_aggressor(sq=None):
        #print("FIND AGGRESSOR [{}]".format(sq))
        if sq is not None:
            await set_ss1(sq)
        await set_state_mode(StateMode.FA)
        return (await get_status())

    async def find_victim():
        #print("FIND VICTIM")
        await set_state_mode(StateMode.FV)
        return (await get_status())

    async def enable_all():
        #print("ENABLE ALL")
        await set_mask_mode(MaskMode.EAV_EAA)
        await set_mask_mode(MaskMode.NO_CHANGE)

    async def set_piece(sq, value):
        await set_ss1(sq)
        await set_write_bus(value)
        await set_state_mode(StateMode.W)

    async def disable_aggressor(sq=None):
        if sq is not None:
            await set_ss1(sq)
        await set_mask_mode(MaskMode.DA)
        await set_mask_mode(MaskMode.NO_CHANGE)

    async def enable_friendly(sq=None):
        if sq is not None:
            await set_ss1(sq)
        await set_mask_mode(MaskMode.DV_EAA)

    async def white_to_move():
        await set_wtm(Colour.WHITE)

    async def black_to_move():
        await set_wtm(Colour.BLACK)

    async def tb_square_loop():
        await enable_all()
        squares = []
        while True:
            dst = await find_victim()
            # cocotb.pass_test()
            assert not (dst & 128)
            if dst & 64:
                break
            #print("dst: {}{}".format(chr(ord('a')+(dst%8)), chr(ord('1')+(dst//8))))
            while True:
                src = await find_aggressor(dst)
                assert not (src & 128)
                if src & 64:
                    break
                #print("  src: {}{}".format(chr(ord('a')+(src%8)), chr(ord('1')+(src//8))))
                squares.append(dst)
                await disable_aggressor(src)
            await enable_friendly()

        return squares

    dut._log.info("Start")

    clock = Clock(dut.clk60, 2)
    cocotb.start_soon(clock.start())

    if gl:
        dut.VDD.value = 1
        dut.VSS.value = 0

    dut.rst_ext_n.value = 0
    dut.bidir_in.value = 0
    dut.bidir_out.value = 0
    await ClockCycles(dut.clk60, 2)
    dut.rst_ext_n.value = 1
    await ClockCycles(dut.clk60, 10)

    # hold TMS high for five TCKs to reset TAP
    for _ in range(5):
        await jtag_tck(tms=1)

    # Run-Test/Idle for the TAP to take control
    await jtag_tck(tms=0)

    await transfer_jtag_ir(0xFE) # IDCODE
    idcode = (await transfer_jtag_dr(0x00, cycles=32))
    assert idcode == 0x1392001d, hex(idcode)

    dut._log.info("king on empty board")

    for sq in range(128):
        if sq & 0x88:
            continue

        expected = []
        for offset in [1, 15, 16, 17, -1, -15, -16, -17]:
            offset += sq
            if offset & 0x88:
                continue
            expected.append((offset + (offset & 7)) >> 1)
        expected.sort()

        sq = (sq + (sq & 7)) >> 1

        await set_piece(sq, WKING)
        await white_to_move()
        actual = await tb_square_loop()
        actual.sort()
        print(sq, expected, actual)
        assert actual == expected
        await set_piece(sq, WKING + 8)
        await black_to_move()
        actual = await tb_square_loop()
        actual.sort()
        print(sq, expected, actual)
        assert actual == expected

        await set_piece(sq, 0xF)

        moves += len(actual)

    dut._log.info("queen on empty board")

    for sq in range(128):
        if sq & 0x88:
            continue

        expected = []
        for offset in [1, 15, 16, 17, -1, -15, -16, -17]:
            s = sq
            while True:
                s += offset
                if s & 0x88:
                    break
                expected.append((s + (s & 7)) >> 1)
        expected.sort()

        sq = (sq + (sq & 7)) >> 1

        await set_piece(sq, WQUEEN)
        await white_to_move()
        actual = await tb_square_loop()
        actual.sort()
        print(sq, expected, actual)
        assert actual == expected
        await set_piece(sq, WQUEEN + 8)
        await black_to_move()
        actual = await tb_square_loop()
        actual.sort()
        print(sq, expected, actual)
        assert actual == expected
        await set_piece(sq, 0xF)

        moves += len(actual)

    dut._log.info("rook on empty board")

    for sq in range(128):
        if sq & 0x88:
            continue

        expected = []
        for offset in [1, 16, -1, -16]:
            s = sq
            while True:
                s += offset
                if s & 0x88:
                    break
                expected.append((s + (s & 7)) >> 1)
        expected.sort()

        sq = (sq + (sq & 7)) >> 1

        await set_piece(sq, WROOK)
        await white_to_move()
        actual = await tb_square_loop()
        actual.sort()
        print(sq, expected, actual)
        assert actual == expected
        await set_piece(sq, WROOK + 8)
        await black_to_move()
        actual = await tb_square_loop()
        actual.sort()
        print(sq, expected, actual)
        assert actual == expected
        await set_piece(sq, 0xF)

        moves += len(actual)

    dut._log.info("bishop on empty board")

    for sq in range(128):
        if sq & 0x88:
            continue

        expected = []
        for offset in [15, 17, -15, -17]:
            s = sq
            while True:
                s += offset
                if s & 0x88:
                    break
                expected.append((s + (s & 7)) >> 1)
        expected.sort()

        sq = (sq + (sq & 7)) >> 1

        await set_piece(sq, WBISHOP)
        await white_to_move()
        actual = await tb_square_loop()
        actual.sort()
        print(sq, expected, actual)
        assert actual == expected
        await set_piece(sq, WBISHOP + 8)
        await black_to_move()
        actual = await tb_square_loop()
        actual.sort()
        print(sq, expected, actual)
        assert actual == expected
        await set_piece(sq, 0xF)

        moves += len(actual)

    dut._log.info("knight on empty board")

    for sq in range(128):
        if sq & 0x88:
            continue

        expected = []
        for offset in [33, 18, -18, -33, -31, -14, 14, 31]:
            offset += sq
            if offset & 0x88:
                continue
            expected.append((offset + (offset & 7)) >> 1)
        expected.sort()

        sq = (sq + (sq & 7)) >> 1

        await set_piece(sq, WKNIGHT)
        await white_to_move()
        actual = await tb_square_loop()
        actual.sort()
        print(sq, expected, actual)
        assert actual == expected
        await set_piece(sq, WKNIGHT + 8)
        await black_to_move()
        actual = await tb_square_loop()
        actual.sort()
        print(sq, expected, actual)
        assert actual == expected
        await set_piece(sq, 0xF)

        moves += len(actual)

    dut._log.info("computed {} moves".format(moves))


def chip_top_runner():

    proj_path = Path(__file__).resolve().parent

    sources = []
    defines = {}
    includes = []

    if gl:
        # SCL models
        sources.append(Path(pdk_root) / pdk / "libs.ref" / scl / "verilog" / f"{scl}.v")
        sources.append(Path(pdk_root) / pdk / "libs.ref" / scl / "verilog" / "primitives.v")

        # We use the powered netlist
        sources.append(proj_path / f"../final/pnl/{hdl_toplevel}.pnl.v")

        defines = {"FUNCTIONAL": True, "USE_POWER_PINS": True}
    else:
        sources.append(proj_path / "../src/chip_core.sv")
        sources.append(proj_path / "../src/arb.sv")
        sources.append(proj_path / "../src/board.sv")
        sources.append(proj_path / "../src/square.sv")
        sources.append(proj_path / "../src/usb.v")
        sources.append(proj_path / "../src/jtag.sv")

        includes.append(proj_path / "../src")

    build_args = []

    if sim == "icarus":
        # For debugging
        # build_args = ["-Winfloop", "-pfileline=1"]
        pass

    if sim == "verilator":
        build_args = ["--timing", "--trace", "--trace-fst", "--trace-structs", "--x-initial-edge"]

    runner = get_runner(sim)
    runner.build(
        sources=sources,
        hdl_toplevel=hdl_toplevel,
        defines=defines,
        always=True,
        includes=includes,
        build_args=build_args,
        waves=True,
    )

    plusargs = []

    runner.test(
        hdl_toplevel=hdl_toplevel,
        test_module="chip_core_tb,",
        plusargs=plusargs,
        waves=True,
    )


if __name__ == "__main__":
    chip_top_runner()
