'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { documentsApi, type UploadDocumentInput } from '@/lib/api/documents';
import { queryKeys } from '@/lib/query-keys';
import type { DocumentItem } from '@/types/document';

const isProcessing = (doc: DocumentItem) => doc.status === 'pending' || doc.status === 'processing';

/** Daftar dokumen; polling tiap 3 detik selama ada yang masih diproses. */
export function useDocuments() {
  return useQuery({
    queryKey: queryKeys.documents,
    queryFn: documentsApi.list,
    refetchInterval: (query) => (query.state.data?.some(isProcessing) ? 3000 : false),
  });
}

export function useDocument(id: string) {
  return useQuery({
    queryKey: queryKeys.document(id),
    queryFn: () => documentsApi.get(id),
    refetchInterval: (query) => (query.state.data && isProcessing(query.state.data) ? 3000 : false),
  });
}

export function useDocumentChunks(id: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.documentChunks(id),
    queryFn: () => documentsApi.chunks(id),
    enabled,
  });
}

export function useUploadDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: UploadDocumentInput) => documentsApi.upload(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.documents }),
  });
}

export function useDeleteDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: documentsApi.remove,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.documents });
      queryClient.invalidateQueries({ queryKey: queryKeys.sessions });
    },
  });
}
