export type ViewMode = 'comparison' | 'extracted';

interface ViewModeToggleProps {
  mode: ViewMode;
  onModeChange: (mode: ViewMode) => void;
}

export default function ViewModeToggle({ mode, onModeChange }: ViewModeToggleProps) {
  return (
    <div
      style={{
        display: 'inline-flex',
        borderRadius: '6px',
        border: '1px solid var(--slate-300)',
        overflow: 'hidden',
        marginBottom: '0.75rem',
      }}
    >
      <button
        onClick={() => onModeChange('comparison')}
        style={{
          padding: '0.4rem 0.9rem',
          fontSize: '0.85rem',
          fontWeight: mode === 'comparison' ? 600 : 400,
          border: 'none',
          cursor: 'pointer',
          backgroundColor: mode === 'comparison' ? 'var(--navy-700)' : 'var(--white)',
          color: mode === 'comparison' ? 'var(--white)' : 'var(--slate-600)',
          transition: 'background-color 0.15s, color 0.15s',
        }}
      >
        Comparison Table
      </button>
      <button
        onClick={() => onModeChange('extracted')}
        style={{
          padding: '0.4rem 0.9rem',
          fontSize: '0.85rem',
          fontWeight: mode === 'extracted' ? 600 : 400,
          border: 'none',
          borderLeft: '1px solid var(--slate-300)',
          cursor: 'pointer',
          backgroundColor: mode === 'extracted' ? 'var(--navy-700)' : 'var(--white)',
          color: mode === 'extracted' ? 'var(--white)' : 'var(--slate-600)',
          transition: 'background-color 0.15s, color 0.15s',
        }}
      >
        Extracted Text
      </button>
    </div>
  );
}
