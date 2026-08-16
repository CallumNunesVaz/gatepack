// SR4 — 4-bit serial-in parallel-out shift register (§9.4 M8).
//
// Hand-written behavioural model.  M-cells are instantiated explicitly by the
// front-end and are NEVER inferred by Yosys (§8, §9.4).  This file is the
// single model used by both exhaustive simulation (appended to cells_sim.v)
// and C4 equivalence checking — the two MUST be the same file (§19 R25).
//
// Synthetic cell, added to demonstrate the spec/impl independence (M8) more
// than once.  It has NO physical binding: no part number, package or pinout is
// claimed, because inventing one would be exactly the §1.3 defect this project
// exists to prevent.  See gatepack/macros/specs.py for the independent
// specification model.

`timescale 1ns/1ps

module SR4 (
  input  wire      CLK,
  input  wire      RST_N,   // asynchronous reset, active low
  input  wire      EN,      // shift enable, active high
  input  wire      SI,      // serial data in
  output reg [3:0] Q
);
  always @(posedge CLK or negedge RST_N) begin
    if (!RST_N)
      Q <= 4'd0;
    else if (EN)
      Q <= {Q[2:0], SI};
  end
endmodule
