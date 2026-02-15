interface ExtractionQualityBadgeProps {
  quality: 'high' | 'medium' | 'low' | null;
}

const QUALITY_STYLES: Record<string, { bg: string; color: string; label: string }> = {
  high: { bg: 'var(--emerald-100)', color: 'var(--emerald-700)', label: 'High' },
  medium: { bg: 'var(--yellow-100)', color: 'var(--yellow-700)', label: 'Medium' },
  low: { bg: 'var(--red-100)', color: 'var(--red-700)', label: 'Low' },
};

export default function ExtractionQualityBadge({ quality }: ExtractionQualityBadgeProps) {
  if (!quality) return null;

  const style = QUALITY_STYLES[quality];
  if (!style) return null;

  return (
    <span
      style={{
        display: 'inline-block',
        padding: '0.1rem 0.4rem',
        borderRadius: '4px',
        fontSize: '0.7rem',
        fontWeight: 600,
        backgroundColor: style.bg,
        color: style.color,
      }}
      title={`Extraction quality: ${style.label}`}
    >
      {style.label}
    </span>
  );
}
