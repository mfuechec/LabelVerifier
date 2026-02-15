import { useState, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import axios from 'axios';
import OverallStatus from '../components/results/OverallStatus';
import ReviewBanner from '../components/results/ReviewBanner';
import ComparisonTable from '../components/results/ComparisonTable';
import ExtractedTextPanel from '../components/results/ExtractedTextPanel';
import ViewModeToggle from '../components/results/ViewModeToggle';
import type { ViewMode } from '../components/results/ViewModeToggle';
import AnnotatedLabelViewer from '../components/results/AnnotatedLabelViewer';
import AgentDecisionBar from '../components/results/AgentDecisionBar';
import OverrideModal from '../components/results/OverrideModal';
import LoadingSpinner from '../components/shared/LoadingSpinner';
import ErrorBanner from '../components/shared/ErrorBanner';
import { getErrorMessage } from '../api/errors';
import {
  useVerification,
  useOverrideField,
  useSubmitDecision,
  useFeedback,
  useReviewField,
} from '../api/verifications';

export default function ResultsPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const { data: result, isLoading, error } = useVerification(sessionId);
  const overrideMutation = useOverrideField();
  const decisionMutation = useSubmitDecision();
  const feedbackMutation = useFeedback();
  const reviewMutation = useReviewField();

  const [highlightedField, setHighlightedField] = useState<string | null>(null);
  const [overrideField, setOverrideField] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('comparison');

  const handleReviewNext = useCallback(() => {
    if (!result?.review_summary) return;
    const unreviewed = result.fields.find(
      (f) => f.status === 'extraction_uncertain' && !f.reviewed
    );
    if (unreviewed) {
      setHighlightedField(unreviewed.field_name);
      // Scroll to the field (the highlight will make it visible)
      const el = document.querySelector(`[data-field="${unreviewed.field_name}"]`);
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [result]);

  const handleConfirmReview = useCallback(
    (fieldName: string) => {
      if (sessionId) {
        reviewMutation.mutate({ sessionId, fieldName });
      }
    },
    [sessionId, reviewMutation]
  );

  if (isLoading) return <LoadingSpinner message="Loading results..." />;
  if (error || !result) {
    const errorMessage = axios.isAxiosError(error) && error.response?.status === 404
      ? 'Verification session not found.'
      : 'Failed to load verification results.';
    return (
      <div style={{ padding: '3rem', textAlign: 'center' }}>
        <p style={{ color: 'var(--red-600)', marginBottom: '1rem' }}>{errorMessage}</p>
        <Link to="/" className="back-link">Back to Home</Link>
      </div>
    );
  }

  const showReviewBanner = result.review_summary && result.review_summary.fields_needing_review > 0;

  return (
    <div className="animate-in">
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.25rem' }}>
        <Link to="/" className="back-link">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
          Back
        </Link>
        <h2 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: '1.7rem' }}>Verification Results</h2>
      </div>

      <div className="section-card" style={{ marginBottom: '1.5rem' }}>
        <OverallStatus
          status={result.status}
          confidence={result.overall_confidence}
          beverageType={result.beverage_type}
          fields={result.fields}
          reviewSummary={result.review_summary}
        />
      </div>

      {showReviewBanner && (
        <ReviewBanner
          reviewSummary={result.review_summary!}
          onReviewNext={handleReviewNext}
        />
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
        <div className="section-card">
          <h3 style={{ fontFamily: 'var(--font-display)', fontSize: '1.3rem', marginBottom: '0.75rem' }}>Label Image</h3>
          <AnnotatedLabelViewer
            annotatedImages={result.annotated_images}
            fields={result.fields}
            highlightedField={highlightedField}
            onFieldClick={(fn) => setHighlightedField(fn === highlightedField ? null : fn)}
          />
        </div>

        <div className="section-card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
            <h3 style={{ fontFamily: 'var(--font-display)', fontSize: '1.3rem', margin: 0 }}>Field Comparison</h3>
            <ViewModeToggle mode={viewMode} onModeChange={setViewMode} />
          </div>

          {viewMode === 'comparison' ? (
            <ComparisonTable
              fields={result.fields}
              highlightedField={highlightedField}
              onFieldHover={setHighlightedField}
              onOverride={setOverrideField}
              onConfirmReview={handleConfirmReview}
            />
          ) : (
            <ExtractedTextPanel
              fields={result.fields}
              highlightedField={highlightedField}
              onFieldClick={(fn) => setHighlightedField(fn === highlightedField ? null : fn)}
            />
          )}

          <AgentDecisionBar
            isSubmitting={decisionMutation.isPending || feedbackMutation.isPending}
            onDecision={(decision, notes) => {
              if (sessionId) {
                decisionMutation.mutate({
                  sessionId,
                  body: { decision, notes },
                });
              }
            }}
            onFeedback={(correct) => {
              if (sessionId) {
                feedbackMutation.mutate({
                  sessionId,
                  body: { ai_correct: correct },
                });
              }
            }}
          />
          {decisionMutation.isError && <ErrorBanner message={getErrorMessage(decisionMutation.error)} />}
          {feedbackMutation.isError && <ErrorBanner message={getErrorMessage(feedbackMutation.error)} />}
        </div>
      </div>

      {overrideField && (
        <OverrideModal
          fieldName={overrideField}
          onClose={() => setOverrideField(null)}
          onSubmit={(req) => {
            if (sessionId) {
              overrideMutation.mutate(
                { sessionId, fieldName: overrideField, body: req },
                { onSuccess: () => setOverrideField(null) }
              );
            }
          }}
        />
      )}
    </div>
  );
}
