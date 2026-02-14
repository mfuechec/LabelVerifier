import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import client from './client';
import type {
  ApplicationData,
  VerificationResult,
  HistoryResponse,
  OverrideRequest,
  DecisionRequest,
  FeedbackRequest,
} from './types';

export function useVerify() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      images,
      panels,
      applicationData,
    }: {
      images: File[];
      panels: string[];
      applicationData: ApplicationData;
    }) => {
      const formData = new FormData();
      formData.append('application_data', JSON.stringify(applicationData));
      images.forEach((img) => formData.append('images[]', img));
      panels.forEach((p) => formData.append('panels[]', p));

      const res = await client.post<{ data: VerificationResult }>('/verify', formData);
      return res.data.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['verifications'] });
    },
  });
}

export function useVerification(sessionId: string | undefined) {
  return useQuery({
    queryKey: ['verification', sessionId],
    queryFn: async () => {
      const res = await client.get<{ data: VerificationResult }>(`/verify/${sessionId}`);
      return res.data.data;
    },
    enabled: !!sessionId,
  });
}

export function useVerifications(params?: {
  status?: string;
  beverage_type?: string;
  brand?: string;
  page?: number;
  per_page?: number;
}) {
  return useQuery({
    queryKey: ['verifications', params],
    queryFn: async () => {
      const res = await client.get<{ data: HistoryResponse }>('/verifications', { params });
      return res.data.data;
    },
  });
}

export function useOverrideField() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      sessionId,
      fieldName,
      body,
    }: {
      sessionId: string;
      fieldName: string;
      body: OverrideRequest;
    }) => {
      await client.patch(`/verify/${sessionId}/fields/${fieldName}`, body);
    },
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['verification', vars.sessionId] });
    },
  });
}

export function useSubmitDecision() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      sessionId,
      body,
    }: {
      sessionId: string;
      body: DecisionRequest;
    }) => {
      await client.post(`/verify/${sessionId}/decision`, body);
    },
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['verification', vars.sessionId] });
      queryClient.invalidateQueries({ queryKey: ['verifications'] });
    },
  });
}

export function useFeedback() {
  return useMutation({
    mutationFn: async ({
      sessionId,
      body,
    }: {
      sessionId: string;
      body: FeedbackRequest;
    }) => {
      await client.post(`/verify/${sessionId}/feedback`, body);
    },
  });
}
