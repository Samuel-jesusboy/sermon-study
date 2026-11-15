// Helpers for showing which model does which job, and what things cost.
export function tiersFor(config, provider) {
  const m = (config.models || []).find(x => x.id === provider) || (config.models || [])[0];
  return m ? m.tiers || {} : {};
}

export function money(value) {
  const v = Number(value || 0);
  if (v === 0) return '$0';
  if (v < 0.01) return `$${v.toFixed(4)}`;
  if (v < 1) return `$${v.toFixed(3)}`;
  return `$${v.toFixed(2)}`;
}
