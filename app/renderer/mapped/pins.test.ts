import { describe, expect, it } from 'vitest';
import { cellPinDirections, clockPin, isFlopType, outputPins } from './pins';

describe('cellPinDirections — mirror of gatepack/pins.py', () => {
  it('names G-cell inputs A, B, C… with output Y', () => {
    expect(cellPinDirections('AND2')).toEqual({ A: 'input', B: 'input', Y: 'output' });
    expect(cellPinDirections('NAND3')).toEqual({
      A: 'input',
      B: 'input',
      C: 'input',
      Y: 'output',
    });
    expect(cellPinDirections('INV')).toEqual({ A: 'input', Y: 'output' });
  });

  it('gives MUX2 three inputs — the select is a pin, not a modifier', () => {
    // `libraries/74aup.csv`: MUX2 has function `(A&!C)|(B&C)` and inputs=3.
    expect(cellPinDirections('MUX2')).toEqual({
      A: 'input',
      B: 'input',
      C: 'input',
      Y: 'output',
    });
  });

  it('gives the F-cells the §9.2 [R4-3] layout with active-low async controls', () => {
    expect(cellPinDirections('DFF_R')).toEqual({
      D: 'input',
      CK: 'input',
      RST_N: 'input',
      Q: 'output',
    });
    expect(cellPinDirections('DFF_SR')).toEqual({
      D: 'input',
      CK: 'input',
      SET_N: 'input',
      RST_N: 'input',
      Q: 'output',
    });
  });

  it('returns null for a type it does not know, rather than guessing', () => {
    // An M-cell pinout lives in gatepack/macros, not here. Inventing a
    // direction would route a wire to the wrong pin and still look like a
    // schematic, which is the failure mode worth being strict about.
    expect(cellPinDirections('CNT4')).toBeNull();
    expect(cellPinDirections('')).toBeNull();
    expect(outputPins('CNT4')).toEqual([]);
  });

  it('identifies the clockable flops and their clock pin', () => {
    expect(isFlopType('DFF_R')).toBe(true);
    expect(isFlopType('AND2')).toBe(false);
    expect(clockPin('DFF_SR')).toBe('CK');
    expect(clockPin('$_DFF_P_')).toBe('C');
    expect(clockPin('AND2')).toBeNull();
  });
});
