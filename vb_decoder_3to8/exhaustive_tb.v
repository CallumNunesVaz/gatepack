// Exhaustive simulation testbench (C4 §C4.3).
// Every reachable (state x input) transition through the mapped netlist,
// compared against the spec including its input synchronisers. No random
// vectors, no coverage.
`timescale 1ns/1ps

module exhaustive_tb;
  reg clk;
  reg rst_n;
  reg s0;
  reg s1;
  reg s2;
  wire y0;
  wire y1;
  wire y2;
  wire y3;
  wire y4;
  wire y5;
  wire y6;
  wire y7;
  integer _failures;

  decoder_3to8 dut (.clk(clk), .rst_n(rst_n), .s0(s0), .s1(s1), .s2(s2), .y0(y0), .y1(y1), .y2(y2), .y3(y3), .y4(y4), .y5(y5), .y6(y6), .y7(y7));

  initial begin
    _failures = 0;
    clk = 1'b0;
    s0 = 1'b0;
    s1 = 1'b0;
    s2 = 1'b0;

    s0 = 1'b0;
    s1 = 1'b0;
    s2 = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    s0 = 1'b0;
    s1 = 1'b0;
    s2 = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (y0 !== 1'b1) begin
      $display("FAIL: y0 at step %0d", y0);
      _failures = _failures + 1;
    end
    if (y1 !== 1'b0) begin
      $display("FAIL: y1 at step %0d", y1);
      _failures = _failures + 1;
    end
    if (y2 !== 1'b0) begin
      $display("FAIL: y2 at step %0d", y2);
      _failures = _failures + 1;
    end
    if (y3 !== 1'b0) begin
      $display("FAIL: y3 at step %0d", y3);
      _failures = _failures + 1;
    end
    if (y4 !== 1'b0) begin
      $display("FAIL: y4 at step %0d", y4);
      _failures = _failures + 1;
    end
    if (y5 !== 1'b0) begin
      $display("FAIL: y5 at step %0d", y5);
      _failures = _failures + 1;
    end
    if (y6 !== 1'b0) begin
      $display("FAIL: y6 at step %0d", y6);
      _failures = _failures + 1;
    end
    if (y7 !== 1'b0) begin
      $display("FAIL: y7 at step %0d", y7);
      _failures = _failures + 1;
    end
    s0 = 1'b0;
    s1 = 1'b0;
    s2 = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    s0 = 1'b0;
    s1 = 1'b0;
    s2 = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (y0 !== 1'b0) begin
      $display("FAIL: y0 at step %0d", y0);
      _failures = _failures + 1;
    end
    if (y1 !== 1'b0) begin
      $display("FAIL: y1 at step %0d", y1);
      _failures = _failures + 1;
    end
    if (y2 !== 1'b0) begin
      $display("FAIL: y2 at step %0d", y2);
      _failures = _failures + 1;
    end
    if (y3 !== 1'b0) begin
      $display("FAIL: y3 at step %0d", y3);
      _failures = _failures + 1;
    end
    if (y4 !== 1'b1) begin
      $display("FAIL: y4 at step %0d", y4);
      _failures = _failures + 1;
    end
    if (y5 !== 1'b0) begin
      $display("FAIL: y5 at step %0d", y5);
      _failures = _failures + 1;
    end
    if (y6 !== 1'b0) begin
      $display("FAIL: y6 at step %0d", y6);
      _failures = _failures + 1;
    end
    if (y7 !== 1'b0) begin
      $display("FAIL: y7 at step %0d", y7);
      _failures = _failures + 1;
    end
    s0 = 1'b0;
    s1 = 1'b0;
    s2 = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    s0 = 1'b0;
    s1 = 1'b1;
    s2 = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (y0 !== 1'b0) begin
      $display("FAIL: y0 at step %0d", y0);
      _failures = _failures + 1;
    end
    if (y1 !== 1'b0) begin
      $display("FAIL: y1 at step %0d", y1);
      _failures = _failures + 1;
    end
    if (y2 !== 1'b1) begin
      $display("FAIL: y2 at step %0d", y2);
      _failures = _failures + 1;
    end
    if (y3 !== 1'b0) begin
      $display("FAIL: y3 at step %0d", y3);
      _failures = _failures + 1;
    end
    if (y4 !== 1'b0) begin
      $display("FAIL: y4 at step %0d", y4);
      _failures = _failures + 1;
    end
    if (y5 !== 1'b0) begin
      $display("FAIL: y5 at step %0d", y5);
      _failures = _failures + 1;
    end
    if (y6 !== 1'b0) begin
      $display("FAIL: y6 at step %0d", y6);
      _failures = _failures + 1;
    end
    if (y7 !== 1'b0) begin
      $display("FAIL: y7 at step %0d", y7);
      _failures = _failures + 1;
    end
    s0 = 1'b0;
    s1 = 1'b0;
    s2 = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    s0 = 1'b0;
    s1 = 1'b1;
    s2 = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (y0 !== 1'b0) begin
      $display("FAIL: y0 at step %0d", y0);
      _failures = _failures + 1;
    end
    if (y1 !== 1'b0) begin
      $display("FAIL: y1 at step %0d", y1);
      _failures = _failures + 1;
    end
    if (y2 !== 1'b0) begin
      $display("FAIL: y2 at step %0d", y2);
      _failures = _failures + 1;
    end
    if (y3 !== 1'b0) begin
      $display("FAIL: y3 at step %0d", y3);
      _failures = _failures + 1;
    end
    if (y4 !== 1'b0) begin
      $display("FAIL: y4 at step %0d", y4);
      _failures = _failures + 1;
    end
    if (y5 !== 1'b0) begin
      $display("FAIL: y5 at step %0d", y5);
      _failures = _failures + 1;
    end
    if (y6 !== 1'b1) begin
      $display("FAIL: y6 at step %0d", y6);
      _failures = _failures + 1;
    end
    if (y7 !== 1'b0) begin
      $display("FAIL: y7 at step %0d", y7);
      _failures = _failures + 1;
    end
    s0 = 1'b0;
    s1 = 1'b0;
    s2 = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    s0 = 1'b1;
    s1 = 1'b0;
    s2 = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (y0 !== 1'b0) begin
      $display("FAIL: y0 at step %0d", y0);
      _failures = _failures + 1;
    end
    if (y1 !== 1'b1) begin
      $display("FAIL: y1 at step %0d", y1);
      _failures = _failures + 1;
    end
    if (y2 !== 1'b0) begin
      $display("FAIL: y2 at step %0d", y2);
      _failures = _failures + 1;
    end
    if (y3 !== 1'b0) begin
      $display("FAIL: y3 at step %0d", y3);
      _failures = _failures + 1;
    end
    if (y4 !== 1'b0) begin
      $display("FAIL: y4 at step %0d", y4);
      _failures = _failures + 1;
    end
    if (y5 !== 1'b0) begin
      $display("FAIL: y5 at step %0d", y5);
      _failures = _failures + 1;
    end
    if (y6 !== 1'b0) begin
      $display("FAIL: y6 at step %0d", y6);
      _failures = _failures + 1;
    end
    if (y7 !== 1'b0) begin
      $display("FAIL: y7 at step %0d", y7);
      _failures = _failures + 1;
    end
    s0 = 1'b0;
    s1 = 1'b0;
    s2 = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    s0 = 1'b1;
    s1 = 1'b0;
    s2 = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (y0 !== 1'b0) begin
      $display("FAIL: y0 at step %0d", y0);
      _failures = _failures + 1;
    end
    if (y1 !== 1'b0) begin
      $display("FAIL: y1 at step %0d", y1);
      _failures = _failures + 1;
    end
    if (y2 !== 1'b0) begin
      $display("FAIL: y2 at step %0d", y2);
      _failures = _failures + 1;
    end
    if (y3 !== 1'b0) begin
      $display("FAIL: y3 at step %0d", y3);
      _failures = _failures + 1;
    end
    if (y4 !== 1'b0) begin
      $display("FAIL: y4 at step %0d", y4);
      _failures = _failures + 1;
    end
    if (y5 !== 1'b1) begin
      $display("FAIL: y5 at step %0d", y5);
      _failures = _failures + 1;
    end
    if (y6 !== 1'b0) begin
      $display("FAIL: y6 at step %0d", y6);
      _failures = _failures + 1;
    end
    if (y7 !== 1'b0) begin
      $display("FAIL: y7 at step %0d", y7);
      _failures = _failures + 1;
    end
    s0 = 1'b0;
    s1 = 1'b0;
    s2 = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    s0 = 1'b1;
    s1 = 1'b1;
    s2 = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (y0 !== 1'b0) begin
      $display("FAIL: y0 at step %0d", y0);
      _failures = _failures + 1;
    end
    if (y1 !== 1'b0) begin
      $display("FAIL: y1 at step %0d", y1);
      _failures = _failures + 1;
    end
    if (y2 !== 1'b0) begin
      $display("FAIL: y2 at step %0d", y2);
      _failures = _failures + 1;
    end
    if (y3 !== 1'b1) begin
      $display("FAIL: y3 at step %0d", y3);
      _failures = _failures + 1;
    end
    if (y4 !== 1'b0) begin
      $display("FAIL: y4 at step %0d", y4);
      _failures = _failures + 1;
    end
    if (y5 !== 1'b0) begin
      $display("FAIL: y5 at step %0d", y5);
      _failures = _failures + 1;
    end
    if (y6 !== 1'b0) begin
      $display("FAIL: y6 at step %0d", y6);
      _failures = _failures + 1;
    end
    if (y7 !== 1'b0) begin
      $display("FAIL: y7 at step %0d", y7);
      _failures = _failures + 1;
    end
    s0 = 1'b0;
    s1 = 1'b0;
    s2 = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    s0 = 1'b1;
    s1 = 1'b1;
    s2 = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (y0 !== 1'b0) begin
      $display("FAIL: y0 at step %0d", y0);
      _failures = _failures + 1;
    end
    if (y1 !== 1'b0) begin
      $display("FAIL: y1 at step %0d", y1);
      _failures = _failures + 1;
    end
    if (y2 !== 1'b0) begin
      $display("FAIL: y2 at step %0d", y2);
      _failures = _failures + 1;
    end
    if (y3 !== 1'b0) begin
      $display("FAIL: y3 at step %0d", y3);
      _failures = _failures + 1;
    end
    if (y4 !== 1'b0) begin
      $display("FAIL: y4 at step %0d", y4);
      _failures = _failures + 1;
    end
    if (y5 !== 1'b0) begin
      $display("FAIL: y5 at step %0d", y5);
      _failures = _failures + 1;
    end
    if (y6 !== 1'b0) begin
      $display("FAIL: y6 at step %0d", y6);
      _failures = _failures + 1;
    end
    if (y7 !== 1'b1) begin
      $display("FAIL: y7 at step %0d", y7);
      _failures = _failures + 1;
    end

    if (_failures == 0) $display("EXHAUSTIVE_SIM_PASS");
    else $display("EXHAUSTIVE_SIM_FAIL (%0d)", _failures);
    $finish;
  end
endmodule
