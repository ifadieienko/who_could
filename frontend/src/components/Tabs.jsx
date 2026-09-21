export function Tabs({ value, active, onChange, items }) {
  const selected = value ?? active;
  return <div className="tabs" role="tablist">{items.map((raw) => {
    const item = Array.isArray(raw) ? { value: raw[0], label: raw[1] } : raw;
    return <button className={selected === item.value ? 'tab active' : 'tab'} key={item.value} onClick={() => onChange(item.value)} type="button">{item.label}</button>;
  })}</div>;
}
