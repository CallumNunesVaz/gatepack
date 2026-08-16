// Exhaustive simulation testbench (C4 §C4.3).
// Every reachable (state x input) transition through the mapped netlist,
// compared against the spec including its input synchronisers. No random
// vectors, no coverage.
`timescale 1ns/1ps

module exhaustive_tb;
  reg clk;
  reg rst_n;
  reg x;
  wire a;
  wire b;
  integer _failures;

  vacuous_mutex dut (.clk(clk), .rst_n(rst_n), .x(x), .a(a), .b(b));

  initial begin
    _failures = 0;
    clk = 1'b0;
    x = 1'b0;

    x = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    x = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (a !== 1'b0) begin
      $display("FAIL: a at step %0d", a);
      _failures = _failures + 1;
    end
    if (b !== 1'b0) begin
      $display("FAIL: b at step %0d", b);
      _failures = _failures + 1;
    end
    x = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    x = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (a !== 1'b1) begin
      $display("FAIL: a at step %0d", a);
      _failures = _failures + 1;
    end
    if (b !== 1'b0) begin
      $display("FAIL: b at step %0d", b);
      _failures = _failures + 1;
    end
    x = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    x = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (a !== 1'b1) begin
      $display("FAIL: a at step %0d", a);
      _failures = _failures + 1;
    end
    if (b !== 1'b0) begin
      $display("FAIL: b at step %0d", b);
      _failures = _failures + 1;
    end
    x = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (a !== 1'b0) begin
      $display("FAIL: a at step %0d", a);
      _failures = _failures + 1;
    end
    if (b !== 1'b0) begin
      $display("FAIL: b at step %0d", b);
      _failures = _failures + 1;
    end
    x = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    x = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (a !== 1'b1) begin
      $display("FAIL: a at step %0d", a);
      _failures = _failures + 1;
    end
    if (b !== 1'b0) begin
      $display("FAIL: b at step %0d", b);
      _failures = _failures + 1;
    end
    x = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (a !== 1'b0) begin
      $display("FAIL: a at step %0d", a);
      _failures = _failures + 1;
    end
    if (b !== 1'b0) begin
      $display("FAIL: b at step %0d", b);
      _failures = _failures + 1;
    end

    if (_failures == 0) $display("EXHAUSTIVE_SIM_PASS");
    else $display("EXHAUSTIVE_SIM_FAIL (%0d)", _failures);
    $finish;
  end
endmodule
