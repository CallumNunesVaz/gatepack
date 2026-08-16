// Exhaustive simulation testbench (C4 §C4.3).
// Every reachable (state x input) transition through the mapped netlist,
// compared against the spec including its input synchronisers. No random
// vectors, no coverage.
`timescale 1ns/1ps

module exhaustive_tb;
  reg clk;
  reg rst_n;
  reg request;
  reg hold;
  wire traffic_red;
  wire traffic_amber;
  wire traffic_green;
  wire walk;
  integer _failures;

  pelican dut (.clk(clk), .rst_n(rst_n), .request(request), .hold(hold), .traffic_red(traffic_red), .traffic_amber(traffic_amber), .traffic_green(traffic_green), .walk(walk));

  initial begin
    _failures = 0;
    clk = 1'b0;
    request = 1'b0;
    hold = 1'b0;

    request = 1'b0;
    hold = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b1) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b1) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b1) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b1) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b1) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b1) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b1) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b1) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b1) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b1) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b1) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b1) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b1) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b1) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b1) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b1) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b1) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b1) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b1) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b1) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b1) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b1) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b1) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b1) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b1) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b1) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b1) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b1) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b1) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    request = 1'b0;
    hold = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b1) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    request = 1'b1;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b1) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    rst_n = 1'b0;
    #10;
    rst_n = 1'b1;
    #10;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    request = 1'b1;
    hold = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b1) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b0;
    hold = 1'b0;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b1) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b0) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end
    request = 1'b1;
    hold = 1'b1;
    #1;
    clk = 1'b1; #1; clk = 1'b0; #1;
    if (traffic_red !== 1'b0) begin
      $display("FAIL: traffic_red at step %0d", traffic_red);
      _failures = _failures + 1;
    end
    if (traffic_amber !== 1'b0) begin
      $display("FAIL: traffic_amber at step %0d", traffic_amber);
      _failures = _failures + 1;
    end
    if (traffic_green !== 1'b1) begin
      $display("FAIL: traffic_green at step %0d", traffic_green);
      _failures = _failures + 1;
    end
    if (walk !== 1'b0) begin
      $display("FAIL: walk at step %0d", walk);
      _failures = _failures + 1;
    end

    if (_failures == 0) $display("EXHAUSTIVE_SIM_PASS");
    else $display("EXHAUSTIVE_SIM_FAIL (%0d)", _failures);
    $finish;
  end
endmodule
