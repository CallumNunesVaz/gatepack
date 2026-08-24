import { useProject } from '../../state/project';
import {
  appendListItem,
  removeListItem,
  setField,
  setInputName,
  setInputSync,
  setOutputName,
  setPropertyExpr,
  setPropertyKind,
  setPropertyName,
  type DesignModel,
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
  const { specText, model, editSpec } = useProject();

  if (!model) {
    return <div className="pane__empty">The spec does not parse yet.</div>;
  }

  const editField = (key: string, value: YValue) => {
    const { text } = setField(specText, key, value);
    editSpec(() => text);
  };

  // The scalar top-level fields use `editField`; the list editors below never
  // re-serialise a whole block, because that deletes every comment in it
  // (measured for `inputs` in setInputSync). Each row operation splices instead
  // — setItemField for a field, appendListItem / removeListItem for add/remove.
  // `setProperty` survives only for the one case a splice cannot do: clearing a
  // property expression removes the key, which a value splice cannot express.
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
              onChange={(e) => editSpec((current) => setInputName(current, index, e.target.value).text)}
              aria-label={`input ${index} name`}
            />
            <label className="inline-label">
              <input
                type="checkbox"
                checked={input.sync}
                onChange={(e) => editSpec((current) => setInputSync(current, input.name, e.target.checked).text)}
              />
              sync
            </label>
            <button onClick={() => editSpec((current) => removeListItem(current, 'inputs', index).text)}>×</button>
          </div>
        ))}
        <button
          onClick={() =>
            editSpec((current) =>
              appendListItem(current, 'inputs', { name: `in${model.inputs.length}`, sync: false }).text,
            )
          }
        >
          + input
        </button>
      </div>

      <h4>Outputs</h4>
      <div className="field-list">
        {model.outputs.map((output, index) => (
          <div className="field-row" key={index}>
            <input
              value={output.name}
              onChange={(e) => editSpec((current) => setOutputName(current, index, e.target.value).text)}
              aria-label={`output ${index} name`}
            />
            <button onClick={() => editSpec((current) => removeListItem(current, 'outputs', index).text)}>×</button>
          </div>
        ))}
        <button
          onClick={() =>
            editSpec((current) => appendListItem(current, 'outputs', { name: `out${model.outputs.length}` }).text)
          }
        >
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
              onChange={(e) => editSpec((current) => setPropertyName(current, index, e.target.value).text)}
              aria-label={`property ${index} name`}
            />
            <select
              value={prop.kind}
              onChange={(e) => editSpec((current) => setPropertyKind(current, index, e.target.value).text)}
            >
              <option value="invariant">invariant</option>
              <option value="reachability">reachability</option>
              <option value="liveness">liveness</option>
              <option value="mutex">mutex</option>
            </select>
            <input
              value={prop.expr ?? ''}
              placeholder="expr"
              onChange={(e) => {
                const expr = e.target.value;
                if (expr === '') {
                  // Clearing removes the key, which a value splice cannot do;
                  // this one case still rewrites the block (see the note above).
                  setProperty(model.properties.map((p, i) => (i === index ? { ...p, expr: undefined } : p)));
                } else {
                  editSpec((current) => setPropertyExpr(current, index, expr).text);
                }
              }}
              aria-label={`property ${index} expr`}
            />
            <button onClick={() => editSpec((current) => removeListItem(current, 'properties', index).text)}>×</button>
          </div>
        ))}
        <button
          onClick={() => editSpec((current) => appendListItem(current, 'properties', { name: 'prop', kind: 'invariant' }).text)}
        >
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
