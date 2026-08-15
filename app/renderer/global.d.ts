// Ambient module declarations for non-TS imports used by the renderer.

declare module '*.svg?raw' {
  const content: string;
  export default content;
}

declare module '*.css' {
  const content: unknown;
  export default content;
}

declare module 'netlistsvg' {
  export function render(
    skinData: string,
    netlist: unknown,
    done?: (err: Error | null, output: string) => void,
    elkData?: unknown,
  ): Promise<string>;
  export function dumpLayout(
    skinData: string,
    netlist: unknown,
    prelayout: boolean,
    done: (err: Error | null, output: string) => void,
  ): void;
}
