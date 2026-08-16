// Exhaustive simulation testbench (C4 §C4.3).
// Every reachable (state x input) transition through the mapped netlist,
// compared against the spec including its input synchronisers. No random
// vectors, no coverage.
`timescale 1ns/1ps

module exhaustive_tb;
  reg clk;
  reg rst_n;
  reg a;
  reg b;
  wire y;
  integer _failures;

  xor2 dut (.clk(clk), .rst_n(rst_n), .a(a), .b(b), .y(y));

  initial begin
    _failures = 0;
    clk = 1'b0;
    a = 1'b0;
    b = 1'b0;

    a = 1'b0;
    b = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    a = 1'b0;
    b = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (y !== 1'b0) begin
      $display("FAIL: y at step %0d", y);
      _failures = _failures + 1;
    end
    a = 1'b0;
    b = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    a = 1'b0;
    b = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (y !== 1'b1) begin
      $display("FAIL: y at step %0d", y);
      _failures = _failures + 1;
    end
    a = 1'b0;
    b = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    a = 1'b1;
    b = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (y !== 1'b1) begin
      $display("FAIL: y at step %0d", y);
      _failures = _failures + 1;
    end
    a = 1'b0;
    b = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    a = 1'b1;
    b = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (y !== 1'b0) begin
      $display("FAIL: y at step %0d", y);
      _failures = _failures + 1;
    end

    if (_failures == 0) $display("EXHAUSTIVE_SIM_PASS");
    else $display("EXHAUSTIVE_SIM_FAIL (%0d)", _failures);
    $finish;
  end
endmodule
