import { STATUS_COLORS, STATUS_BG_COLORS, STATUS_LABELS } from '../../lib/constants';

interface StatusBadgeProps {
  status: string;
  size?: 'sm' | 'md' | 'lg';
}

export default function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const bgColor = STATUS_BG_COLORS[status] || '#f3f4f6';
  const textColor = STATUS_COLORS[status] || '#6b7280';
  const label = STATUS_LABELS[status] || status;

  const sizeStyles = {
    sm: { padding: '2px 8px', fontSize: '0.75rem' },
    md: { padding: '4px 12px', fontSize: '0.875rem' },
    lg: { padding: '6px 16px', fontSize: '1rem' },
  };

  return (
    <span
      style={{
        display: 'inline-block',
        backgroundColor: bgColor,
        color: textColor,
        borderRadius: '9999px',
        fontWeight: 600,
        ...sizeStyles[size],
      }}
    >
      {label}
    </span>
  );
}
