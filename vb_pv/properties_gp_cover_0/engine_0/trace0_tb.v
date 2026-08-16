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
    // UUT.$formal$properties.\sv:18$2_EN  = 1'b0;
    // UUT.$formal$properties.\sv:20$3_EN  = 1'b0;
    UUT._witness_.anyinit_procdff_63 = 1'b0;
    UUT._witness_.anyinit_procdff_65 = 1'b0;
    UUT._witness_.anyinit_procdff_70 = 1'b0;
    UUT._witness_.anyinit_procdff_71 = 1'b0;
    UUT._witness_.anyinit_procdff_72 = 1'b0;
    UUT._witness_.anyinit_procdff_73 = 1'b0;
    UUT.gp_cycle = 4'b0000;

    // state 0
    PI_x = 1'b0;
    PI_rst_n = 1'b0;
  end
  always @(posedge clock) begin
    // state 1
    if (cycle == 0) begin
      PI_x <= 1'b0;
      PI_rst_n <= 1'b0;
    end

    // state 2
    if (cycle == 1) begin
      PI_x <= 1'b0;
      PI_rst_n <= 1'b0;
    end

    // state 3
    if (cycle == 2) begin
      PI_x <= 1'b0;
      PI_rst_n <= 1'b0;
    end

    // state 4
    if (cycle == 3) begin
      PI_x <= 1'b0;
      PI_rst_n <= 1'b0;
    end

    // state 5
    if (cycle == 4) begin
      PI_x <= 1'b0;
      PI_rst_n <= 1'b0;
    end

    genclock <= cycle < 5;
    cycle <= cycle + 1;
  end
endmodule
