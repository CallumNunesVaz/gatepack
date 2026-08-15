// CNT4 — 4-bit synchronous binary counter (§9.4).
//
// Hand-written behavioural model.  M-cells are instantiated explicitly by the
// front-end and are NEVER inferred by Yosys (§8, §9.4).  This file is the
// single model used by both exhaustive simulation (appended to cells_sim.v)
// and C4 equivalence checking — the two MUST be the same file (§19 R25).
//
// Physical binding: 74LVC161 (see gatepack/macros/bindings.py).
// Candidate part — unverified, per §9 (datasheet confirmation pending).

`timescale 1ns/1ps

module CNT4 (
  input  wire      CLK,
  input  wire      RST_N,   // asynchronous reset, active low
  input  wire      EN,      // count enable, active high
  output reg [3:0] Q
);
  always @(posedge CLK or negedge RST_N) begin
    if (!RST_N)
      Q <= 4'd0;
    else if (EN)
      Q <= Q + 1'b1;
  end
endmodule
