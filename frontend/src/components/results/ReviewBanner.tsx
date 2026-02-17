import type { ReviewSummary } from '../../api/types';

interface ReviewBannerProps {
  reviewSummary: ReviewSummary;
  onReviewNext: () => void;
}

export default function ReviewBanner({ reviewSummary, onReviewNext }: ReviewBannerProps) {
  const { fields_needing_review, fields_reviewed } = reviewSummary;

  if (fields_needing_review === 0) return null;

  const allReviewed = fields_reviewed >= fields_needing_review;
  const remaining = fields_needing_review - fields_reviewed;

  return (
    <div
      className="section-card"
      style={{
        marginBottom: '1.5rem',
        padding: '1rem 1.5rem',
        backgroundColor: allReviewed ? 'var(--emerald-50)' : 'var(--yellow-50)',
        border: `1px solid ${allReviewed ? 'var(--emerald-300)' : 'var(--yellow-300)'}`,
        borderRadius: '8px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem' }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, fontSize: '1rem', marginBottom: '0.25rem', color: allReviewed ? 'var(--emerald-800)' : 'var(--yellow-800)' }}>
            {allReviewed
              ? 'All fields reviewed. Submit your decision below.'
              : `This label requires review. ${remaining} of ${fields_needing_review} flagged field${fields_needing_review > 1 ? 's' : ''} need${remaining === 1 ? 's' : ''} attention.`}
          </div>

          {/* Progress bar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginTop: '0.5rem' }}>
            <div style={{ flex: 1, height: '6px', backgroundColor: 'var(--slate-200)', borderRadius: '3px', overflow: 'hidden' }}>
              <div
                style={{
                  width: `${fields_needing_review > 0 ? (fields_reviewed / fields_needing_review) * 100 : 0}%`,
                  height: '100%',
                  backgroundColor: allReviewed ? 'var(--emerald-500)' : 'var(--yellow-500)',
                  borderRadius: '3px',
                  transition: 'width 0.3s ease',
                }}
              />
            </div>
            <span style={{ fontSize: '0.8rem', color: 'var(--slate-600)', whiteSpace: 'nowrap' }}>
              {fields_reviewed}/{fields_needing_review} reviewed
            </span>
          </div>
        </div>

        {!allReviewed && (
          <button
            onClick={onReviewNext}
            className="btn-primary"
            style={{ whiteSpace: 'nowrap', padding: '0.5rem 1rem' }}
          >
            Review Next
          </button>
        )}
      </div>
    </div>
  );
}
