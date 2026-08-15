// latch_inferring.v — §18 golden: build MUST fail (§9.2 latch ban).
//
// A combinational always block with an incomplete assignment infers a
// transparent latch; C3's `select -assert-none t:$_DLATCH_*` must catch it.
// This design intentionally violates the latch ban and is exercised only when
// Yosys is installed (tests/golden/test_golden_designs.py skips it otherwise).
module latch_inferring (
  input  wire en,
  input  wire d,
  output reg  q
);
  always @(*) begin
    if (en)
      q = d;
  end
endmodule
