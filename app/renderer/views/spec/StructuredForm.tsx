import { useProject } from '../../state/project';
import {
  applyTopLevelEdit,
  setField,
  type DesignModel,
  type InputPort,
  type OutputPort,
  type PropertySpec,
} from '../../design/model';
import type { YValue } from '../../design/yaml';

/**
 * Structured form for the top-level spec fields: name/timing/encoding/initial,
 * inputs, outputs, properties, constraints. Every edit is a document mutation
 * that rewrites the YAML text (the text stays authoritative); nothing here
 * maintains a second model.
 */
export function StructuredForm() {
  const { specText, model, setSpecText } = useProject();

  if (!model) {
    return <div className="pane__empty">The spec does not parse yet.</div>;
  }

  const edit = (key: string, transform: (cur: YValue) => YValue) => {
    try {
      const { text } = applyTopLevelEdit(specText, key, transform);
      setSpecText(text);
    } catch {
      /* key not present — fall back to upsert below */
    }
  };

  const editField = (key: string, value: YValue) => {
    const { text } = setField(specText, key, value);
    setSpecText(text);
  };

  const setInput = (inputs: InputPort[]) =>
    edit('inputs', () => inputs.map((i) => ({ name: i.name, sync: i.sync })));

  const setOutput = (outputs: OutputPort[]) =>
    edit('outputs', () => outputs.map((o) => ({ name: o.name })));

  const setProperty = (properties: PropertySpec[]) =>
    editField(
      'properties',
      properties.map((p) => {
        const m: Record<string, YValue> = { name: p.name, kind: p.kind };
        if (p.expr !== undefined) m.expr = p.expr;
        if (p.from !== undefined) m.from = p.from;
        if (p.to !== undefined) m.to = p.to;
        return m;
      }),
    );

  const setInputName = (index: number, name: string) => {
    const inputs = model.inputs.map((i, idx) => (idx === index ? { ...i, name } : i));
    setInput(inputs);
  };

  const setInputSync = (index: number, sync: boolean) => {
    const inputs = model.inputs.map((i, idx) => (idx === index ? { ...i, sync } : i));
    setInput(inputs);
  };

  return (
    <div className="form">
      <div className="form-grid">
        <label>
          name
          <input value={model.name} onChange={(e) => editField('name', e.target.value)} />
        </label>
        <label>
          timing_model
          <select
            value={model.timingModel}
            onChange={(e) => editField('timing_model', e.target.value)}
          >
            <option value="synchronous">synchronous</option>
            <option value="asynchronous">asynchronous</option>
          </select>
        </label>
        <label>
          encoding
          <select value={model.encoding} onChange={(e) => editField('encoding', e.target.value)}>
            <option value="one_hot">one_hot</option>
            <option value="binary">binary</option>
            <option value="gray">gray</option>
          </select>
        </label>
        <label>
          initial
          <select value={model.initial} onChange={(e) => editField('initial', e.target.value)}>
            {model.states.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
      </div>

      <h4>Inputs</h4>
      <div className="field-list">
        {model.inputs.map((input, index) => (
          <div className="field-row" key={index}>
            <input
              value={input.name}
              onChange={(e) => setInputName(index, e.target.value)}
              aria-label={`input ${index} name`}
            />
            <label className="inline-label">
              <input
                type="checkbox"
                checked={input.sync}
                onChange={(e) => setInputSync(index, e.target.checked)}
              />
              sync
            </label>
            <button onClick={() => setInput(model.inputs.filter((_, i) => i !== index))}>×</button>
          </div>
        ))}
        <button onClick={() => setInput([...model.inputs, { name: `in${model.inputs.length}`, sync: false }])}>
          + input
        </button>
      </div>

      <h4>Outputs</h4>
      <div className="field-list">
        {model.outputs.map((output, index) => (
          <div className="field-row" key={index}>
            <input
              value={output.name}
              onChange={(e) => setOutput(model.outputs.map((o, i) => (i === index ? { name: e.target.value } : o)))}
              aria-label={`output ${index} name`}
            />
            <button onClick={() => setOutput(model.outputs.filter((_, i) => i !== index))}>×</button>
          </div>
        ))}
        <button onClick={() => setOutput([...model.outputs, { name: `out${model.outputs.length}` }])}>
          + output
        </button>
      </div>

      <h4>States</h4>
      <div className="field-list">
        {model.states.map((state) => (
          <div className="field-row" key={state}>
            <span>{state}</span>
            {state === model.initial ? <span className="muted">(initial)</span> : null}
          </div>
        ))}
      </div>

      <h4>Properties</h4>
      <div className="field-list">
        {model.properties.map((prop, index) => (
          <div className="field-row" key={index}>
            <input
              value={prop.name}
              onChange={(e) =>
                setProperty(model.properties.map((p, i) => (i === index ? { ...p, name: e.target.value } : p)))
              }
              aria-label={`property ${index} name`}
            />
            <select
              value={prop.kind}
              onChange={(e) =>
                setProperty(
                  model.properties.map((p, i) =>
                    i === index ? { ...p, kind: e.target.value as PropertySpec['kind'] } : p,
                  ),
                )
              }
            >
              <option value="invariant">invariant</option>
              <option value="reachability">reachability</option>
              <option value="liveness">liveness</option>
              <option value="mutex">mutex</option>
            </select>
            <input
              value={prop.expr ?? ''}
              placeholder="expr"
              onChange={(e) =>
                setProperty(
                  model.properties.map((p, i) =>
                    i === index ? { ...p, expr: e.target.value || undefined } : p,
                  ),
                )
              }
              aria-label={`property ${index} expr`}
            />
            <button onClick={() => setProperty(model.properties.filter((_, i) => i !== index))}>×</button>
          </div>
        ))}
        <button onClick={() => setProperty([...model.properties, { name: 'prop', kind: 'invariant' }])}>
          + property
        </button>
      </div>

      <h4>Constraints</h4>
      <div className="form-grid">
        <label>
          vcc
          <input
            type="number"
            step="0.1"
            value={model.constraints.vcc}
            onChange={(e) =>
              editField('constraints', { ...constraintsToYaml(model.constraints), vcc: Number(e.target.value) })
            }
          />
        </label>
        <label>
          max_flops
          <input
            type="number"
            value={model.constraints.maxFlops ?? ''}
            placeholder="unset"
            onChange={(e) =>
              editField(
                'constraints',
                { ...constraintsToYaml(model.constraints), max_flops: e.target.value ? Number(e.target.value) : null },
              )
            }
          />
        </label>
        <label>
          max_packages
          <input
            type="number"
            value={model.constraints.maxPackages ?? ''}
            placeholder="unset"
            onChange={(e) =>
              editField(
                'constraints',
                { ...constraintsToYaml(model.constraints), max_packages: e.target.value ? Number(e.target.value) : null },
              )
            }
          />
        </label>
      </div>
    </div>
  );
}

function constraintsToYaml(c: DesignModel['constraints']): Record<string, YValue> {
  const out: Record<string, YValue> = { vcc: c.vcc };
  if (c.maxFlops !== undefined) out.max_flops = c.maxFlops;
  if (c.maxPackages !== undefined) out.max_packages = c.maxPackages;
  if (c.maxStaticUa !== undefined) out.max_static_ua = c.maxStaticUa;
  return out;
}
