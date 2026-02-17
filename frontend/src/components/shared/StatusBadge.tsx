import { STATUS_LABELS } from '../../lib/constants';

interface StatusBadgeProps {
  status: string;
  size?: 'sm' | 'md' | 'lg';
}

const BADGE_CLASS: Record<string, string> = {
  match: 'badge-match',
  content_mismatch: 'badge-mismatch',
  field_missing: 'badge-missing',
  extraction_uncertain: 'badge-uncertain',
  pass: 'badge-pass',
  needs_review: 'badge-needs-review',
  fail: 'badge-fail',
  pending: 'badge-pending',
};

export default function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const label = STATUS_LABELS[status] || status;
  const badgeClass = BADGE_CLASS[status] || 'badge-pending';
  const sizeClass = size === 'sm' ? 'badge-sm' : size === 'lg' ? 'badge-lg' : '';

  return (
    <span className={`badge ${badgeClass} ${sizeClass}`}>
      {label}
    </span>
  );
}
