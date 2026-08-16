`ifndef VERILATOR
module testbench;
  reg [4095:0] vcdfile;
  reg clock;
`else
module testbench(input clock, output reg genclock);
  initial genclock = 1;
`endif
  reg genclock = 1;
  reg [31:0] cycle = 0;
  reg [0:0] PI_x;
  reg [0:0] PI_rst_n;
  wire [0:0] PI_clk = clock;
  property_violating UUT (
    .x(PI_x),
    .rst_n(PI_rst_n),
    .clk(PI_clk)
  );
`ifndef VERILATOR
  initial begin
    if ($value$plusargs("vcd=%s", vcdfile)) begin
      $dumpfile(vcdfile);
      $dumpvars(0, testbench);
    end
    #5 clock = 0;
    while (genclock) begin
      #5 clock = 0;
      #5 clock = 1;
    end
  end
`endif
  initial begin
`ifndef VERILATOR
    #1;
`endif
    // UUT.$formal$properties.\sv:20$2_EN  = 1'b0;
    UUT._witness_.anyinit_procdff_56 = 1'b0;
    UUT._witness_.anyinit_procdff_58 = 1'b0;
    UUT._witness_.anyinit_procdff_63 = 1'b0;
    UUT._witness_.anyinit_procdff_64 = 1'b0;
    UUT._witness_.anyinit_procdff_65 = 1'b1;
    UUT._witness_.anyinit_procdff_66 = 1'b0;
    UUT.gp_cycle = 4'b0000;

    // state 0
    PI_x = 1'b1;
    PI_rst_n = 1'b0;
  end
  always @(posedge clock) begin
    // state 1
    if (cycle == 0) begin
      PI_x <= 1'b1;
      PI_rst_n <= 1'b0;
    end

    // state 2
    if (cycle == 1) begin
      PI_x <= 1'b1;
      PI_rst_n <= 1'b0;
    end

    // state 3
    if (cycle == 2) begin
      PI_x <= 1'b1;
      PI_rst_n <= 1'b0;
    end

    // state 4
    if (cycle == 3) begin
      PI_x <= 1'b1;
      PI_rst_n <= 1'b1;
    end

    // state 5
    if (cycle == 4) begin
      PI_x <= 1'b1;
      PI_rst_n <= 1'b1;
    end

    // state 6
    if (cycle == 5) begin
      PI_x <= 1'b1;
      PI_rst_n <= 1'b1;
    end

    // state 7
    if (cycle == 6) begin
      PI_x <= 1'b1;
      PI_rst_n <= 1'b1;
    end

    // state 8
    if (cycle == 7) begin
      PI_x <= 1'b0;
      PI_rst_n <= 1'b1;
    end

    // state 9
    if (cycle == 8) begin
      PI_x <= 1'b1;
      PI_rst_n <= 1'b1;
    end

    genclock <= cycle < 9;
    cycle <= cycle + 1;
  end
endmodule
