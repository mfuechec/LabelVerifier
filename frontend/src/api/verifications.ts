import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import client from './client';
import type {
  VerificationResult,
  HistoryResponse,
  OverrideRequest,
  DecisionRequest,
  FeedbackRequest,
  BatchResponse,
} from './types';

export function useVerify() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ colaPdf }: { colaPdf: File }) => {
      const formData = new FormData();
      formData.append('cola_pdf', colaPdf);

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

export function useReviewField() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      sessionId,
      fieldName,
    }: {
      sessionId: string;
      fieldName: string;
    }) => {
      await client.post(`/verify/${sessionId}/fields/${fieldName}/review`);
    },
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['verification', vars.sessionId] });
    },
  });
}

export function useBatchUpload() {
  return useMutation({
    mutationFn: async ({ colaPdfs }: { colaPdfs: File[] }) => {
      const formData = new FormData();
      colaPdfs.forEach((pdf) => formData.append('cola_pdfs[]', pdf));

      const res = await client.post<{ data: { batch_id: string; total_items: number; skipped_count: number } }>(
        '/batch',
        formData
      );
      return res.data.data;
    },
  });
}

export function useBatchStatus(batchId: string | undefined) {
  return useQuery({
    queryKey: ['batch', batchId],
    queryFn: async () => {
      const res = await client.get<{ data: BatchResponse }>(`/batch/${batchId}`);
      return res.data.data;
    },
    enabled: !!batchId,
    refetchInterval: (query) => {
      const status = query.state.data?.batch?.status;
      if (status === 'completed' || status === 'failed') return false;
      return 3000;
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
