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
      <div className="label-viewer-empty">
        <p>No annotated image available. Field locations shown below.</p>
      </div>
    );
  }

  return (
    <div className="label-viewer">
      <img src={imageUrl} alt="Label" />
      {fields
        .filter((f) => f.bounding_box)
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
  );
}
