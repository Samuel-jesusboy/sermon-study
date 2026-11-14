import React from 'react';
import { useApp } from './AppContext';

const COLORS = { claude: '#4A3B6B', openai: '#10a37f', groq: '#f55036' };
const LABELS = { claude: 'Claude', openai: 'OpenAI', groq: 'Groq' };

// Shows only the AI providers the server has keys for. Hidden when there's just one.
export default function ModelSelector() {
  const { config, model, setModel } = useApp();
  const models = config.models || [];
  if (models.length < 2) return null;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ fontSize: 12, color: 'var(--text-soft)', fontWeight: 500 }}>AI:</span>
      <div className="segmented">
        {models.map(m => (
          <button key={m.id} type="button" title={m.name} onClick={() => setModel(m.id)}
            style={{ background: model === m.id ? COLORS[m.id] : 'transparent', color: model === m.id ? 'white' : 'var(--text-soft)' }}>
            {LABELS[m.id] || m.id}
          </button>
        ))}
      </div>
    </div>
  );
}
