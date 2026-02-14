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
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <p style={{ color: '#ef4444' }}>Failed to load verification results.</p>
        <Link to="/" style={{ color: '#2563eb' }}>Back to Upload</Link>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
        <Link to="/" style={{ color: '#6b7280', textDecoration: 'none' }}>Back</Link>
        <h2 style={{ margin: 0 }}>Verification Results</h2>
      </div>

      <OverallStatus
        status={result.status}
        confidence={result.overall_confidence}
        beverageType={result.beverage_type}
      />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
        <div>
          <h3 style={{ marginBottom: '0.5rem' }}>Label Image</h3>
          <AnnotatedLabelViewer
            fields={result.fields}
            highlightedField={highlightedField}
            onFieldClick={(fn) => setHighlightedField(fn === highlightedField ? null : fn)}
          />
        </div>

        <div>
          <h3 style={{ marginBottom: '0.5rem' }}>Field Comparison</h3>
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
