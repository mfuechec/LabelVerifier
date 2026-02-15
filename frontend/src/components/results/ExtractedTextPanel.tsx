import type { FieldComparisonResult } from '../../api/types';
import ExtractionQualityBadge from '../shared/ExtractionQualityBadge';
import StatusBadge from '../shared/StatusBadge';
import { FIELD_LABELS, CANONICAL_WARNING } from '../../lib/constants';

interface ExtractedTextPanelProps {
  fields: FieldComparisonResult[];
  highlightedField: string | null;
  onFieldClick: (fieldName: string) => void;
}

function WordDiff({ extracted, canonical }: { extracted: string; canonical: string }) {
  const extWords = extracted.split(/\s+/);
  const canWords = canonical.split(/\s+/);

  return (
    <div style={{ fontFamily: 'monospace', fontSize: '0.8rem', lineHeight: 1.6 }}>
      {canWords.map((word, i) => {
        const matches = extWords[i]?.toLowerCase() === word.toLowerCase();
        return (
          <span
            key={i}
            style={{
              backgroundColor: matches ? undefined : 'var(--red-100)',
              color: matches ? 'var(--slate-700)' : 'var(--red-700)',
              fontWeight: matches ? 400 : 600,
              padding: matches ? undefined : '0 2px',
              borderRadius: '2px',
            }}
          >
            {extWords[i] || '___'}{' '}
          </span>
        );
      })}
      {extWords.length > canWords.length && (
        <span style={{ backgroundColor: 'var(--yellow-100)', color: 'var(--yellow-700)', padding: '0 2px' }}>
          {extWords.slice(canWords.length).join(' ')}
        </span>
      )}
    </div>
  );
}

export default function ExtractedTextPanel({ fields, highlightedField, onFieldClick }: ExtractedTextPanelProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {fields.map((field) => (
        <div
          key={field.field_name}
          onClick={() => onFieldClick(field.field_name)}
          style={{
            padding: '0.75rem 1rem',
            borderRadius: '6px',
            border: highlightedField === field.field_name
              ? '2px solid var(--blue-500)'
              : '1px solid var(--slate-200)',
            backgroundColor: highlightedField === field.field_name ? 'var(--blue-50)' : 'var(--white)',
            cursor: 'pointer',
            transition: 'border-color 0.15s, background-color 0.15s',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.4rem' }}>
            <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>
              {FIELD_LABELS[field.field_name] || field.field_name}
            </span>
            <StatusBadge status={field.status} size="sm" />
            <ExtractionQualityBadge quality={field.extraction_confidence} />
          </div>

          {field.extracted_value ? (
            field.field_name === 'government_warning' ? (
              <WordDiff extracted={field.extracted_value} canonical={CANONICAL_WARNING} />
            ) : (
              <div
                style={{
                  fontFamily: 'monospace',
                  fontSize: '0.8rem',
                  padding: '0.4rem 0.6rem',
                  backgroundColor: 'var(--slate-50)',
                  borderRadius: '4px',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {field.extracted_value}
              </div>
            )
          ) : (
            <div style={{ fontSize: '0.8rem', color: 'var(--slate-400)', fontStyle: 'italic' }}>
              Not found on label
            </div>
          )}

          {field.confidence_reason && (
            <div style={{ fontSize: '0.75rem', color: 'var(--slate-500)', marginTop: '0.3rem' }}>
              {field.confidence_reason}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
