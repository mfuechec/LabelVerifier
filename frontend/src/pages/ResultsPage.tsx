import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import OverallStatus from '../components/results/OverallStatus';
import ComparisonTable from '../components/results/ComparisonTable';
import AnnotatedLabelViewer from '../components/results/AnnotatedLabelViewer';
import AgentDecisionBar from '../components/results/AgentDecisionBar';
import FeedbackWidget from '../components/results/FeedbackWidget';
import OverrideModal from '../components/results/OverrideModal';
import LoadingSpinner from '../components/shared/LoadingSpinner';
import {
  useVerification,
  useOverrideField,
  useSubmitDecision,
  useFeedback,
} from '../api/verifications';

export default function ResultsPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const { data: result, isLoading, error } = useVerification(sessionId);
  const overrideMutation = useOverrideField();
  const decisionMutation = useSubmitDecision();
  const feedbackMutation = useFeedback();

  const [highlightedField, setHighlightedField] = useState<string | null>(null);
  const [overrideField, setOverrideField] = useState<string | null>(null);

  if (isLoading) return <LoadingSpinner message="Loading results..." />;
  if (error || !result) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center' }}>
        <p style={{ color: 'var(--red-600)', marginBottom: '1rem' }}>Failed to load verification results.</p>
        <Link to="/" className="back-link">Back to Home</Link>
      </div>
    );
  }

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
        />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
        <div className="section-card">
          <h3 style={{ fontFamily: 'var(--font-display)', fontSize: '1.3rem', marginBottom: '0.75rem' }}>Label Image</h3>
          <AnnotatedLabelViewer
            fields={result.fields}
            highlightedField={highlightedField}
            onFieldClick={(fn) => setHighlightedField(fn === highlightedField ? null : fn)}
          />
        </div>

        <div className="section-card">
          <h3 style={{ fontFamily: 'var(--font-display)', fontSize: '1.3rem', marginBottom: '0.75rem' }}>Field Comparison</h3>
          <ComparisonTable
            fields={result.fields}
            highlightedField={highlightedField}
            onFieldHover={setHighlightedField}
            onOverride={setOverrideField}
          />

          <AgentDecisionBar
            isSubmitting={decisionMutation.isPending}
            onDecision={(decision, notes) => {
              if (sessionId) {
                decisionMutation.mutate({
                  sessionId,
                  body: { decision, notes },
                });
              }
            }}
          />

          <div style={{ marginTop: '1rem' }}>
            <FeedbackWidget
              isSubmitting={feedbackMutation.isPending}
              onFeedback={(correct) => {
                if (sessionId) {
                  feedbackMutation.mutate({
                    sessionId,
                    body: { ai_correct: correct },
                  });
                }
              }}
            />
          </div>
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
