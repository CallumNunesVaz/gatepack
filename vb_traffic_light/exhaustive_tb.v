// Exhaustive simulation testbench (C4 §C4.3).
// Every reachable (state x input) transition through the mapped netlist,
// compared against the spec including its input synchronisers. No random
// vectors, no coverage.
`timescale 1ns/1ps

module exhaustive_tb;
  reg clk;
  reg rst_n;
  reg go;
  reg emergency;
  wire red;
  wire green;
  wire amber;
  integer _failures;

  traffic_light dut (.clk(clk), .rst_n(rst_n), .go(go), .emergency(emergency), .red(red), .green(green), .amber(amber));

  initial begin
    _failures = 0;
    clk = 1'b0;
    go = 1'b0;
    emergency = 1'b0;

    go = 1'b0;
    emergency = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    go = 1'b0;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    go = 1'b0;
    emergency = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    go = 1'b1;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b1;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b0) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b1) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    go = 1'b1;
    emergency = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b1;
    emergency = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    go = 1'b1;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b0) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b1) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b0) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b1) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    go = 1'b1;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b0) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b1) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b0) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b1) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    go = 1'b1;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b1;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b0) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b1) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b1;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b0) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b1) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    go = 1'b1;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b1;
    emergency = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b0) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b1) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b1;
    emergency = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b0) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b1) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    go = 1'b1;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b0) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b1) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b0) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b1) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    go = 1'b1;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b0) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b1) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b0) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b1) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    go = 1'b1;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b1;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b0) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b1) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b0) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b1) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b1;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    go = 1'b1;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b1;
    emergency = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b0) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b1) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b0;
    emergency = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b0) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b1) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end
    go = 1'b1;
    emergency = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (red !== 1'b1) begin
      $display("FAIL: red at step %0d", red);
      _failures = _failures + 1;
    end
    if (green !== 1'b0) begin
      $display("FAIL: green at step %0d", green);
      _failures = _failures + 1;
    end
    if (amber !== 1'b0) begin
      $display("FAIL: amber at step %0d", amber);
      _failures = _failures + 1;
    end

    if (_failures == 0) $display("EXHAUSTIVE_SIM_PASS");
    else $display("EXHAUSTIVE_SIM_FAIL (%0d)", _failures);
    $finish;
  end
endmodule
