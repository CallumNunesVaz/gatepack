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
  reg [0:0] PI_request;
  reg [0:0] PI_hold;
  wire [0:0] PI_clk = clock;
  reg [0:0] PI_rst_n;
  pelican UUT (
    .request(PI_request),
    .hold(PI_hold),
    .clk(PI_clk),
    .rst_n(PI_rst_n)
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
    // UUT.$formal$properties.\sv:40$5_EN  = 1'b0;
    UUT._witness_.anyinit_procdff_109 = 1'b0;
    UUT._witness_.anyinit_procdff_111 = 1'b0;
    UUT._witness_.anyinit_procdff_113 = 1'b0;
    UUT._witness_.anyinit_procdff_115 = 1'b0;
    UUT._witness_.anyinit_procdff_117 = 1'b0;
    UUT._witness_.anyinit_procdff_119 = 1'b0;
    UUT._witness_.anyinit_procdff_124 = 1'b0;
    UUT._witness_.anyinit_procdff_125 = 1'b0;
    UUT._witness_.anyinit_procdff_126 = 1'b0;
    UUT._witness_.anyinit_procdff_127 = 1'b0;
    UUT._witness_.anyinit_procdff_128 = 1'b0;
    UUT._witness_.anyinit_procdff_129 = 1'b0;
    UUT._witness_.anyinit_procdff_130 = 1'b0;
    UUT._witness_.anyinit_procdff_131 = 1'b0;
    UUT._witness_.anyinit_procdff_132 = 1'b0;
    UUT._witness_.anyinit_procdff_133 = 1'b0;
    UUT._witness_.anyinit_procdff_134 = 1'b0;
    UUT.gp_cycle = 4'b0000;

    // state 0
    PI_request = 1'b0;
    PI_hold = 1'b0;
    PI_rst_n = 1'b0;
  end
  always @(posedge clock) begin
    // state 1
    if (cycle == 0) begin
      PI_request <= 1'b0;
      PI_hold <= 1'b0;
      PI_rst_n <= 1'b0;
    end

    // state 2
    if (cycle == 1) begin
      PI_request <= 1'b0;
      PI_hold <= 1'b0;
      PI_rst_n <= 1'b0;
    end

    // state 3
    if (cycle == 2) begin
      PI_request <= 1'b0;
      PI_hold <= 1'b0;
      PI_rst_n <= 1'b0;
    end

    // state 4
    if (cycle == 3) begin
      PI_request <= 1'b0;
      PI_hold <= 1'b0;
      PI_rst_n <= 1'b1;
    end

    // state 5
    if (cycle == 4) begin
      PI_request <= 1'b0;
      PI_hold <= 1'b1;
      PI_rst_n <= 1'b1;
    end

    // state 6
    if (cycle == 5) begin
      PI_request <= 1'b0;
      PI_hold <= 1'b0;
      PI_rst_n <= 1'b1;
    end

    // state 7
    if (cycle == 6) begin
      PI_request <= 1'b0;
      PI_hold <= 1'b0;
      PI_rst_n <= 1'b1;
    end

    // state 8
    if (cycle == 7) begin
      PI_request <= 1'b0;
      PI_hold <= 1'b0;
      PI_rst_n <= 1'b0;
    end

    genclock <= cycle < 8;
    cycle <= cycle + 1;
  end
endmodule
