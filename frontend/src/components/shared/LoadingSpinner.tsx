interface LoadingSpinnerProps {
  message?: string;
}

export default function LoadingSpinner({ message = 'Processing...' }: LoadingSpinnerProps) {
  return (
    <div className="loading-container">
      <div className="spinner" />
      <p className="loading-message">{message}</p>
    </div>
  );
}
