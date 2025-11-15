/*
 * Copyright (c) 2025 Hannah Ravensloft
 * SPDX-License-Identifier: Apache-2.0
 *
 * This is based on https://github.com/dragonmux/remiru and used with permission.
 */

`default_nettype none

`define RESET      0
`define IDLE       1
`define SELECT_DR  2
`define CAPTURE_DR 3
`define SHIFT_DR   4
`define EXIT1_DR   5
`define PAUSE_DR   6
`define EXIT2_DR   7
`define UPDATE_DR  8
`define SELECT_IR  9
`define CAPTURE_IR 10
`define SHIFT_IR   11
`define EXIT1_IR   12
`define PAUSE_IR   13
`define EXIT2_IR   14
`define UPDATE_IR  15

`define IDCODE     8'hFE
`define BYPASS     8'hFF

`define MY_IDCODE  32'h1392001D // Motorola MPA1100, if you were wondering.

module jtag_tap(
    input  wire      clk,
    input  wire      rst_n,
    input  wire      tck,
    input  wire      tms,
    input  wire      tdi,
    output reg       tdo,
    output reg [7:0] insn,
    output wire      active,

    output wire      user_tdi,
    input  wire      user_tdo,
    output wire      user_capture,
    output wire      user_shift,
    output wire      user_update
);

reg        tck_last;
reg [3:0]  state;

reg        capture_ir;
reg        shift_ir;
reg        update_ir;
reg        capture_dr;
reg        shift_dr;
reg        update_dr;

reg        bypass;
reg [31:0] idcode;

reg [7:0]  insn_shift_reg;

wire       tck_rising  = tck && !tck_last;
wire       tck_falling = !tck && tck_last;

assign active       = state != `RESET;

assign user_capture = capture_dr && tck_rising;
assign user_shift   = shift_dr && tck_rising;
assign user_update  = update_dr && tck_rising;

// IR values:
// 1-64: square A1-H8, RW, {mask:1, color:1, piece:3}
// 65:   state mode,   RW, {state_mode:3}
// 66:   mask mode,    RW, {mask_mode:2}
// 67:   white to move RW, {wtm:1}
// 68:   write bus     RW, {write_bus:4}
// 69:   square sel 1  RW, {ss1_valid:1, ss1:6}
// 70:   square sel 2  RW, {ss2_valid:1, ss2:6}
// 71:   board data    RO, {illegal:1, empty:1, square:6}
// 72:   core select   RW, {core:3}

always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        state    <= 4'b0;
        insn     <= 8'b0;
        tdo      <= 1'b0;
        shift_dr <= 1'b0;
        tck_last <= 1'b0;
    end else begin
        tck_last <= tck;
        if (tck_rising) begin
            casez (state)
            `RESET:
                if (!tms) begin
                    shift_dr <= 1'b0;
                    shift_ir <= 1'b0;
                    insn     <= `IDCODE;
                    state    <= `IDLE;
                end
            `IDLE:
                if (tms)
                    state <= `SELECT_DR;
            `SELECT_DR:
                if (tms)
                    state <= `SELECT_IR;
                else
                    state <= `CAPTURE_DR;
            `CAPTURE_DR:
                if (tms)
                    state <= `EXIT1_DR;
                else begin
                    shift_dr <= 1'b1;
                    state    <= `SHIFT_DR;
                end
            `SHIFT_DR:
                if (tms) begin
                    shift_dr <= 1'b0;
                    state    <= `EXIT1_DR;
                end
            `EXIT1_DR:
                if (tms)
                    state <= `UPDATE_DR;
                else
                    state <= `PAUSE_DR;
            `PAUSE_DR:
                if (tms)
                    state <= `EXIT2_DR;
            `EXIT2_DR:
                if (tms)
                    state <= `UPDATE_DR;
                else
                    state <= `SHIFT_DR;
            `UPDATE_DR:
                if (tms)
                    state <= `SELECT_DR;
                else
                    state <= `IDLE;
            `SELECT_IR:
                if (tms)
                    state  <= `RESET;
                else
                    state <= `CAPTURE_IR;
            `CAPTURE_IR:
                if (tms)
                    state <= `EXIT1_IR;
                else begin
                    shift_ir <= 1'b1;
                    state    <= `SHIFT_IR;
                end
            `SHIFT_IR:
                if (tms) begin
                    shift_ir <= 1'b0;
                    state    <= `EXIT1_IR;
                end
            `EXIT1_IR:
                if (tms)
                    state <= `UPDATE_IR;
                else
                    state <= `PAUSE_IR;
            `PAUSE_IR:
                if (tms)
                    state <= `EXIT2_IR;
            `EXIT2_IR:
                if (tms)
                    state <= `UPDATE_IR;
                else
                    state <= `SHIFT_IR;
            `UPDATE_IR:
                if (tms)
                    state <= `SELECT_DR;
                else
                    state <= `IDLE;
            endcase

            if (capture_ir)
                insn_shift_reg <= insn;
            else if (shift_ir) begin
                insn_shift_reg <= {tdi, insn_shift_reg[7:1]};
            end else if (update_ir)
                insn           <= insn_shift_reg;

            else if (capture_dr) begin
                casez (insn)
                `IDCODE:
                    idcode <= `MY_IDCODE;
                default:
                    ;
                endcase
            end else if (shift_dr) begin
                casez (insn)
                `IDCODE: begin
                    idcode <= {tdi, idcode[31:1]};
                end
                8'b0???????: begin
                    ;
                end
                default: begin
                    bypass <= tdi;
                end
                endcase
            end else if (update_dr) begin
                ;
            end
        end else if (tck_falling) begin
            if (capture_ir)
                ;
            else if (shift_ir) begin
                tdo            <= insn_shift_reg[0];
            end else if (update_ir)
                ;

            else if (capture_dr) begin
                ;
            end else if (shift_dr) begin
                casez (insn)
                `IDCODE: begin
                    tdo    <= idcode[0];
                end
                8'b0???????: begin
                    tdo    <= user_tdo;
                end
                default: begin
                    tdo    <= bypass;
                end
                endcase
            end else if (update_dr) begin
                ;
            end
        end
    end
end

always_comb begin
    // Ensure the update signals are kept low at all times other than when they're pulsed by the JTAG TAP
    capture_dr = 1'b0;
    capture_ir = 1'b0;
    update_dr  = 1'b0;
    update_ir  = 1'b0;

    casez (state)
    `CAPTURE_DR:
        if (!tms)
            capture_dr = 1'b1;
    `UPDATE_DR:
        update_dr = 1'b1;
    `CAPTURE_IR:
        if (!tms)
            capture_ir = 1'b1;
    `UPDATE_IR:
        update_ir = 1'b1;
    default:
        ;
    endcase
end

assign user_tdi = tdi;

endmodule


module jtag_tap_register
#(
    parameter DR_LENGTH = 1,
    parameter DR_DEFAULT = 0
) (
    input wire clk,
    input wire rst_n,
    input wire tdi,
    output wire tdo,

    input wire capture,
    input wire shift,
    input wire update,

    input  wire [DR_LENGTH - 1:0] data_in,
    output wire [DR_LENGTH - 1:0] data_out,
    output reg data_updated
);

reg [DR_LENGTH - 1:0] data;

assign tdo      = data[0]; // TDO from this block is always the bottom most bit of the shift register to keep things simple
assign data_out = data;

generate
    if (DR_LENGTH == 1) begin : gen_dr_length_1
        always @(posedge clk or negedge rst_n) begin
            if (!rst_n) begin
                data         <= DR_DEFAULT;
                data_updated <= 1'b0;
            end else begin
                data_updated <= 1'b0;
                if (capture)
                    data <= data_in;
                else if (shift) begin
                    data <= tdi;
                end else if (update) begin
                    data_updated <= 1'b1;
                end
            end
        end
    end else begin : gen_dr_length_n
        always @(posedge clk or negedge rst_n) begin
            if (!rst_n) begin
                data         <= DR_DEFAULT;
                data_updated <= 1'b0;
            end else begin
                data_updated <= 1'b0;
                if (capture)
                    data <= data_in;
                else if (shift) begin
                    data <= {tdi, data[DR_LENGTH - 1:1]};
                end else if (update) begin
                    data_updated <= 1'b1;
                end
            end
        end
    end
endgenerate


endmodule
