import type { FieldComparisonResult } from '../../api/types';
import { STATUS_COLORS } from '../../lib/constants';

interface AnnotatedLabelViewerProps {
  imageUrl?: string;
  fields: FieldComparisonResult[];
  highlightedField: string | null;
  onFieldClick: (fieldName: string) => void;
}

export default function AnnotatedLabelViewer({
  imageUrl,
  fields,
  highlightedField,
  onFieldClick,
}: AnnotatedLabelViewerProps) {
  if (!imageUrl) {
    return (
      <div
        style={{
          height: '400px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: '#f3f4f6',
          borderRadius: '8px',
          color: '#9ca3af',
        }}
      >
        <p>No annotated image available. Field locations shown below.</p>
      </div>
    );
  }

  return (
    <div style={{ position: 'relative', overflow: 'hidden', borderRadius: '8px' }}>
      <img src={imageUrl} alt="Label" style={{ width: '100%', display: 'block' }} />
      {fields
        .filter((f) => f.bounding_box)
        .map((f) => (
          <div
            key={f.field_name}
            onClick={() => onFieldClick(f.field_name)}
            style={{
              position: 'absolute',
              left: `${f.bounding_box!.x}%`,
              top: `${f.bounding_box!.y}%`,
              width: `${f.bounding_box!.width}%`,
              height: `${f.bounding_box!.height}%`,
              border: `3px solid ${STATUS_COLORS[f.status] || '#eab308'}`,
              backgroundColor:
                highlightedField === f.field_name ? 'rgba(59,130,246,0.15)' : 'transparent',
              cursor: 'pointer',
              transition: 'background-color 0.15s',
            }}
          />
        ))}
    </div>
  );
}
