import { useState } from 'react';
import type { FieldComparisonResult } from '../../api/types';
import { STATUS_COLORS } from '../../lib/constants';

interface AnnotatedLabelViewerProps {
  imageUrl?: string;
  annotatedImages?: Record<string, string>;
  fields: FieldComparisonResult[];
  highlightedField: string | null;
  onFieldClick: (fieldName: string) => void;
}

export default function AnnotatedLabelViewer({
  imageUrl,
  annotatedImages,
  fields,
  highlightedField,
  onFieldClick,
}: AnnotatedLabelViewerProps) {
  const [zoom, setZoom] = useState(1);
  const panels = annotatedImages ? Object.keys(annotatedImages).sort() : [];
  const [activePanel, setActivePanel] = useState<string>(panels[0] || 'front');

  // Determine which image to show
  const resolvedUrl = annotatedImages?.[activePanel] || imageUrl;
  // Convert relative API paths to full URLs
  const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
  const fullImageUrl = resolvedUrl?.startsWith('/') ? `${apiBase.replace('/api/v1', '')}${resolvedUrl}` : resolvedUrl;

  const handleWheel = (e: React.WheelEvent) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      setZoom((z) => Math.min(Math.max(z + (e.deltaY > 0 ? -0.1 : 0.1), 0.5), 3));
    }
  };

  if (!fullImageUrl) {
    return (
      <div className="label-viewer-empty">
        <p>No annotated image available. Field locations shown below.</p>
      </div>
    );
  }

  return (
    <div>
      {/* Panel tabs for multi-image labels */}
      {panels.length > 1 && (
        <div style={{ display: 'flex', gap: '0.25rem', marginBottom: '0.5rem' }}>
          {panels.map((panel) => (
            <button
              key={panel}
              onClick={() => setActivePanel(panel)}
              style={{
                padding: '0.25rem 0.6rem',
                fontSize: '0.8rem',
                border: '1px solid var(--slate-300)',
                borderRadius: '4px',
                cursor: 'pointer',
                backgroundColor: activePanel === panel ? 'var(--navy-700)' : 'var(--white)',
                color: activePanel === panel ? 'var(--white)' : 'var(--slate-600)',
              }}
            >
              {panel.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
            </button>
          ))}
        </div>
      )}

      {/* Zoom controls */}
      <div style={{ display: 'flex', gap: '0.3rem', marginBottom: '0.5rem', alignItems: 'center' }}>
        <button
          onClick={() => setZoom((z) => Math.max(z - 0.25, 0.5))}
          style={{ padding: '0.2rem 0.5rem', fontSize: '0.85rem', border: '1px solid var(--slate-300)', borderRadius: '4px', cursor: 'pointer', backgroundColor: 'var(--white)' }}
          aria-label="Zoom out"
        >
          -
        </button>
        <span style={{ fontSize: '0.8rem', color: 'var(--slate-600)', minWidth: '3rem', textAlign: 'center' }}>
          {Math.round(zoom * 100)}%
        </span>
        <button
          onClick={() => setZoom((z) => Math.min(z + 0.25, 3))}
          style={{ padding: '0.2rem 0.5rem', fontSize: '0.85rem', border: '1px solid var(--slate-300)', borderRadius: '4px', cursor: 'pointer', backgroundColor: 'var(--white)' }}
          aria-label="Zoom in"
        >
          +
        </button>
        {zoom !== 1 && (
          <button
            onClick={() => setZoom(1)}
            style={{ padding: '0.2rem 0.5rem', fontSize: '0.75rem', border: '1px solid var(--slate-300)', borderRadius: '4px', cursor: 'pointer', backgroundColor: 'var(--white)', color: 'var(--slate-500)' }}
          >
            Reset
          </button>
        )}
      </div>

      <div
        className="label-viewer"
        onWheel={handleWheel}
        style={{ overflow: 'auto', maxHeight: '500px' }}
      >
        <div style={{ transform: `scale(${zoom})`, transformOrigin: 'top left', transition: 'transform 0.15s ease' }}>
          <img src={fullImageUrl} alt="Label" style={{ maxWidth: '100%', display: 'block' }} />
          {fields
            .filter((f) => f.bounding_box && f.bounding_box.panel === activePanel)
            .map((f) => (
              <div
                key={f.field_name}
                className={`label-viewer-overlay${highlightedField === f.field_name ? ' highlighted' : ''}`}
                onClick={() => onFieldClick(f.field_name)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onFieldClick(f.field_name); } }}
                tabIndex={0}
                role="button"
                aria-label={f.field_name.replace('_', ' ')}
                style={{
                  left: `${f.bounding_box!.x}%`,
                  top: `${f.bounding_box!.y}%`,
                  width: `${f.bounding_box!.width}%`,
                  height: `${f.bounding_box!.height}%`,
                  border: `3px solid ${STATUS_COLORS[f.status] || '#eab308'}`,
                }}
              />
            ))}
        </div>
      </div>
    </div>
  );
}
